import { apiRequest } from "./http";

/** Whether every tool run needs a person's approval. Armory keeps the rule. */
export interface ToolApproval {
  force_tool_approval: boolean;
}

/** portcullis's /api/armory-tool-approval (needs settings.manage), passed on to Armory. */
export const toolApprovalClient = {
  get: () => apiRequest<ToolApproval>("GET", "/api/armory-tool-approval"),
  set: (value: boolean) => apiRequest<ToolApproval>("PUT", "/api/armory-tool-approval", { value }),
};
