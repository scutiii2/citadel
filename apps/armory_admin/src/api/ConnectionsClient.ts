import { apiRequest } from "./http";

export type Transport = "mcp" | "rest";
export type AuthKind = "token" | "headers" | "internal" | "none";
export type Service = "portcullis" | "stronghold" | "legion" | "armory" | "treasury";

export interface AuthView {
  kind: AuthKind;
  configured: boolean;
  audience?: Service;
}

export interface ConnectionInfo {
  name: string;
  class: "required" | "server";
  label: string;
  description: string;
  enabled: boolean;
  web_url: string | null;
  ready: boolean;
  reason: string | null;
  mcp: { url: string | null; auth: AuthView; forward_requester?: boolean; local?: boolean; status?: string; tools?: string[]; error?: string | null } | null;
  rest: { base_url: string; auth: AuthView } | null;
}

export interface TestResult {
  ok: boolean;
  message: string;
  tools?: string[];
}

const root = "/api/admin/connections";
const recordPath = (name: string): string => root + "/" + encodeURIComponent(name);

export const connectionsClient = {
  list: () => apiRequest<ConnectionInfo[]>("GET", root),
  create: (body: object) => apiRequest<ConnectionInfo>("POST", root, body),
  update: (name: string, body: object) => apiRequest<ConnectionInfo>("PATCH", recordPath(name), body),
  remove: (name: string) => apiRequest<void>("DELETE", recordPath(name)),
  test: (name: string, transport: Transport) =>
    apiRequest<TestResult>("POST", recordPath(name) + "/test/" + transport),
  async personalCount(): Promise<number> {
    return (await apiRequest<unknown[]>("GET", "/api/user-extensions")).length;
  },
};
