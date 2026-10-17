/**
 * Minimal X-Ray subsegment emitter for Lambda functions in `Active` tracing
 * mode, with no dependency.
 *
 * Lambda creates the function's segment itself and passes its id in
 * `_X_AMZN_TRACE_ID` (`Root=…;Parent=…;Sampled=1`). Anything the function wants
 * to show *inside* that segment — one subsegment per tool call, and nested
 * under it one per DynamoDB, Secrets Manager or HTTP call — is sent as JSON over
 * UDP to the daemon address Lambda provides in `AWS_XRAY_DAEMON_ADDRESS`. That
 * is the whole contract `aws-xray-sdk-core` implements; this file implements
 * only the part this service needs:
 *
 * - `subsegment(name, fn)` times `fn`, nests by async context, records
 *   errors (`fault` for 5xx/unknown, `error` for 4xx/VaultError) and annotations;
 * - `instrumentAwsClient(client, service)` adds an AWS SDK v3 middleware so every
 *   command becomes an `aws` namespace subsegment (`DynamoDB`, `SQS`, `S3`) with
 *   the operation, request id and HTTP status — the X-Ray service map then shows
 *   those services as nodes;
 * - `flush()` awaits the UDP sends before the invocation returns (a frozen
 *   Lambda drops unsent datagrams).
 *
 * Why not the SDK: `aws-xray-sdk-core` is in maintenance (end of support
 * 2027-02-25), and the ADOT Node.js layer auto-instruments by patching modules
 * at `require` time, which an esbuild bundle (this repository ships one ESM
 * file per Lambda) defeats. Swapping this class for Powertools Tracer later is
 * local to the two call sites in `apps/mcp-server/src/handler.ts`.
 */
import { AsyncLocalStorage } from "node:async_hooks";
import { randomBytes } from "node:crypto";
import { createSocket, type Socket } from "node:dgram";

export interface TraceHeader {
  root: string;
  parent?: string;
  sampled: boolean;
}

/** Parse `Root=1-…;Parent=…;Sampled=1` (Lambda env or `X-Amzn-Trace-Id`). */
export function parseTraceHeader(value: string | undefined): TraceHeader | undefined {
  if (!value) return undefined;
  const parts = Object.fromEntries(
    value.split(";").map((part) => {
      const [key, ...rest] = part.trim().split("=");
      return [key ?? "", rest.join("=")];
    })
  );
  const root = parts.Root;
  if (!root) return undefined;
  return {
    root,
    ...(parts.Parent ? { parent: parts.Parent } : {}),
    sampled: parts.Sampled === "1"
  };
}

export interface SubsegmentDocument {
  id: string;
  trace_id: string;
  parent_id: string;
  name: string;
  start_time: number;
  end_time?: number;
  type: "subsegment";
  namespace?: "aws" | "remote";
  error?: boolean;
  fault?: boolean;
  throttle?: boolean;
  cause?: { exceptions: { id: string; message: string; type: string }[] };
  annotations?: Record<string, string | number | boolean>;
  metadata?: Record<string, Record<string, unknown>>;
  aws?: Record<string, unknown>;
  http?: { request?: { method?: string; url?: string }; response?: { status?: number } };
}

export interface Subsegment {
  readonly document: SubsegmentDocument;
  annotate(key: string, value: string | number | boolean): void;
  addMetadata(key: string, value: unknown): void;
  setAws(fields: Record<string, unknown>): void;
  setHttpStatus(status: number): void;
}

export type Sender = (payload: string) => Promise<void>;

export interface XRayRecorderOptions {
  /** `host:port`; defaults to `AWS_XRAY_DAEMON_ADDRESS`. Absent → disabled. */
  daemonAddress?: string;
  /** Source of the current trace header; defaults to `_X_AMZN_TRACE_ID`. */
  traceHeader?: () => string | undefined;
  /** Replace the UDP sender (tests). */
  send?: Sender;
  /** Classify an error: `error` (client side, 4xx) or `fault` (server side). */
  classify?: (error: unknown) => "error" | "fault";
}

const HEADER = '{"format": "json", "version": 1}\n';

function newId(): string {
  return randomBytes(8).toString("hex");
}

function udpSender(address: string): Sender {
  const [host, portText] = address.includes(":") ? address.split(":") : ["127.0.0.1", address];
  const port = Number(portText);
  let socket: Socket | undefined;
  return (payload) =>
    new Promise((resolve) => {
      socket ??= createSocket("udp4");
      socket.unref();
      // Telemetry must never fail a request: errors are swallowed.
      socket.send(payload, port, host ?? "127.0.0.1", () => resolve());
    });
}

export class XRayRecorder {
  private readonly storage = new AsyncLocalStorage<SubsegmentDocument>();
  private readonly pending = new Set<Promise<void>>();
  private readonly send: Sender | undefined;
  private readonly traceHeader: () => string | undefined;
  private readonly classify: (error: unknown) => "error" | "fault";

  constructor(options: XRayRecorderOptions = {}) {
    const address = options.daemonAddress ?? process.env.AWS_XRAY_DAEMON_ADDRESS;
    this.send = options.send ?? (address ? udpSender(address) : undefined);
    this.traceHeader = options.traceHeader ?? (() => process.env._X_AMZN_TRACE_ID);
    this.classify = options.classify ?? (() => "fault");
  }

  /** True when this invocation is sampled and a daemon is reachable. */
  get active(): boolean {
    return Boolean(this.send && parseTraceHeader(this.traceHeader())?.sampled);
  }

  /** The trace header to forward downstream (`X-Amzn-Trace-Id`), if any. */
  downstreamHeader(): string | undefined {
    const header = parseTraceHeader(this.traceHeader());
    if (!header) return undefined;
    const parent = this.storage.getStore()?.id ?? header.parent;
    return `Root=${header.root}${parent ? `;Parent=${parent}` : ""};Sampled=${header.sampled ? "1" : "0"}`;
  }

  async subsegment<T>(
    name: string,
    fn: (segment: Subsegment) => Promise<T>,
    options: {
      namespace?: "aws" | "remote";
      annotations?: Record<string, string | number | boolean>;
    } = {}
  ): Promise<T> {
    const header = parseTraceHeader(this.traceHeader());
    const parentId = this.storage.getStore()?.id ?? header?.parent;
    if (!this.send || !header?.sampled || !parentId) {
      return fn(inertSubsegment(name));
    }
    const document: SubsegmentDocument = {
      id: newId(),
      trace_id: header.root,
      parent_id: parentId,
      name: name.replace(/[^\p{L}\p{N}\s_.:/%&#=+\\@-]/gu, "_").slice(0, 200),
      start_time: Date.now() / 1000,
      type: "subsegment",
      ...(options.namespace ? { namespace: options.namespace } : {}),
      ...(options.annotations ? { annotations: { ...options.annotations } } : {})
    };
    const handle = liveSubsegment(document);
    try {
      return await this.storage.run(document, () => fn(handle));
    } catch (error) {
      const kind = this.classify(error);
      document[kind] = true;
      document.cause = {
        exceptions: [
          {
            id: newId(),
            type: error instanceof Error ? error.name : "Error",
            // Never the message of a domain error body: names only, as in the logs.
            message: error instanceof Error ? error.name : "Error"
          }
        ]
      };
      throw error;
    } finally {
      document.end_time = Date.now() / 1000;
      this.emit(document);
    }
  }

  /**
   * Add an AWS SDK v3 middleware that wraps every command in a subsegment.
   * Typed structurally so this package does not depend on `@smithy/types`.
   */
  instrumentAwsClient<C extends { middlewareStack: { add: (...args: never[]) => unknown } }>(
    client: C,
    service: string
  ): C {
    const add = client.middlewareStack.add as unknown as (
      middleware: AwsMiddleware,
      options: { step: string; name: string; priority?: string }
    ) => void;
    add.call(
      client.middlewareStack,
      (next, context) => async (args) =>
        this.subsegment(
          service,
          async (segment) => {
            const operation = (context.commandName ?? "").replace(/Command$/u, "");
            segment.setAws({ operation, ...(context.region ? { region: context.region } : {}) });
            try {
              const output = await next(args);
              const meta = (
                output.output as
                  | { $metadata?: { requestId?: string; httpStatusCode?: number } }
                  | undefined
              )?.$metadata;
              segment.setAws({ operation, request_id: meta?.requestId });
              if (meta?.httpStatusCode) segment.setHttpStatus(meta.httpStatusCode);
              return output;
            } catch (error) {
              const meta = (
                error as { $metadata?: { requestId?: string; httpStatusCode?: number } }
              ).$metadata;
              if (meta?.httpStatusCode) segment.setHttpStatus(meta.httpStatusCode);
              if (meta?.requestId) segment.setAws({ operation, request_id: meta.requestId });
              throw error;
            }
          },
          { namespace: "aws" }
        ),
      { step: "initialize", name: "xraySubsegment", priority: "high" }
    );
    return client;
  }

  /** Wait for every datagram of this invocation to leave the process. */
  async flush(): Promise<void> {
    await Promise.all([...this.pending]);
  }

  private emit(document: SubsegmentDocument): void {
    if (!this.send) return;
    const sent = this.send(HEADER + JSON.stringify(document)).catch(() => undefined);
    this.pending.add(sent);
    void sent.finally(() => this.pending.delete(sent));
  }
}

type AwsMiddleware = (
  next: (args: unknown) => Promise<{ output?: unknown; response?: unknown }>,
  context: { commandName?: string; region?: string }
) => (args: unknown) => Promise<{ output?: unknown; response?: unknown }>;

function liveSubsegment(document: SubsegmentDocument): Subsegment {
  return {
    document,
    annotate(key, value) {
      document.annotations = {
        ...document.annotations,
        [key.replace(/[^A-Za-z0-9_]/gu, "_")]: value
      };
    },
    addMetadata(key, value) {
      document.metadata = {
        ...document.metadata,
        default: { ...document.metadata?.default, [key]: value }
      };
    },
    setAws(fields) {
      document.aws = {
        ...document.aws,
        ...Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined))
      };
    },
    setHttpStatus(status) {
      document.http = { ...document.http, response: { status } };
      if (status === 429) document.throttle = true;
      if (status >= 400 && status < 500) document.error = true;
      if (status >= 500) document.fault = true;
    }
  };
}

function inertSubsegment(name: string): Subsegment {
  return liveSubsegment({
    id: "",
    trace_id: "",
    parent_id: "",
    name,
    start_time: 0,
    type: "subsegment"
  });
}
