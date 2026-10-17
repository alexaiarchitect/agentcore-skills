import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { createServer } from "./server.js";

export async function handler(event: { rawPath: string; body?: string }) {
  if (event.rawPath === "/health") return { statusCode: 200, body: "ok" };
  if (event.rawPath !== "/mcp") return { statusCode: 404, body: "" };
  const server = createServer();
  const transport = new WebStandardStreamableHTTPServerTransport({ enableJsonResponse: true });
  await server.connect(transport);
  return { statusCode: 200, body: "" };
}
