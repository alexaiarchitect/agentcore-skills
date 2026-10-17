import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export function createServer(): McpServer {
  const server = new McpServer({ name: "Example Vault", version: "0.1.0" });
  server.registerTool("list_categories", { description: "List the owner's categories.", inputSchema: {} }, async () => ({
    content: [{ type: "text", text: "[]" }]
  }));
  server.registerTool("get_record", { description: "Read one record.", inputSchema: { ref: z.string() } }, async () => ({
    content: [{ type: "text", text: "{}" }]
  }));
  server.registerTool("query_records", { description: "Page through records.", inputSchema: {} }, async () => ({
    content: [{ type: "text", text: "[]" }]
  }));
  return server;
}
