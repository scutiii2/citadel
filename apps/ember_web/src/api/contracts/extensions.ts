/** Another MCP server mcp_server re-exposes; its tools are named
 * "<id>__<tool>". */
export interface ExtensionInfo {
  id: string;
  label: string;
  description: string;
  status: "connected" | "error" | string;
  error: string | null;
  tools: string[];
  /** The extension's own web app (an http(s) address from mcp_server's config). */
  web_url?: string | null;
}

/** Separates an extension tool's id from its own name. */
export const EXTENSION_SEPARATOR = "__";
