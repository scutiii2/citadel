import { apiRequest } from "./http";

export interface TreasuryInstance {
  name: string;
  /** The connections this instance may use. */
  connections: string[];
}

export interface TreasuryView {
  /** False when Treasury did not answer. */
  reachable: boolean;
  instances: TreasuryInstance[];
  /** The instance and connection Portcullis itself stores its data in. */
  portcullis: { instance: string; connection: string };
}

/** What a connection holds. A Postgres `dsn` is a ${NAME} placeholder: its value is in Treasury's .env, never here. */
export interface ConnectionSpec {
  type: "sqlite" | "postgres" | "firestore";
  path?: string;
  dsn?: string;
  max_pool_size?: number;
  project?: string;
  credentials_file?: string;
  database?: string;
  allow_raw_sql?: boolean;
  cache?: { ttl_seconds?: number; max_entries?: number; negative_ttl_seconds?: number };
}

export interface ConnectionRow {
  name: string;
  spec: ConnectionSpec;
  /** `built-in`, `changed` (a saved one replaces the built-in) or `saved` (added here). */
  source: "built-in" | "changed" | "saved";
  /** The instances that use it. */
  used_by: string[];
}

export interface CacheDefaults {
  ttl_seconds: number;
  max_entries: number;
  negative_ttl_seconds: number;
}

export interface ConnectionsView {
  connections: ConnectionRow[];
  default_cache: CacheDefaults;
  default_cache_stored: boolean;
  /** `now` (a new connection is already offered to the instances) or `next start`. */
  applies?: string;
}

export const treasuryAdminClient = {
  get: () => apiRequest<TreasuryView>("GET", "/api/admin/treasury"),
  connections: () => apiRequest<ConnectionsView>("GET", "/api/admin/treasury/connections"),
  saveConnection: (name: string, spec: ConnectionSpec) =>
    apiRequest<ConnectionsView>("PUT", `/api/admin/treasury/connections/${encodeURIComponent(name)}`, spec),
  /** A built-in connection comes back; refused while an instance uses a saved one. */
  removeConnection: (name: string) => apiRequest<ConnectionsView>("DELETE", `/api/admin/treasury/connections/${encodeURIComponent(name)}`),
  /** Changes are merged into the saved defaults; `null` puts the built-in defaults back. Used from Treasury's next start. */
  saveDefaultCache: (changes: Partial<CacheDefaults> | null) =>
    apiRequest<ConnectionsView>("PUT", "/api/admin/treasury/default-cache", changes ?? undefined),
};
