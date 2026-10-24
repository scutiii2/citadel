import { apiRequest } from "../../../api/http";
import type { ExtensionInfo } from "../../../api/contracts/extensions";

/** ember_api's pass-through to mcp_server's extensions: listing needs
 * chat.use or tools.view. Management lives in ember_admin. */
export const extensionsClient = {
  list: () => apiRequest<ExtensionInfo[]>("GET", "/api/extensions"),
};
