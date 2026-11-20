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

export interface ServiceRow {
  name: string;
  url: string;
  source: "pinned" | "registered" | "default";
  registered: string | null;
  pinned: string | null;
}

export interface ServicesView { services: ServiceRow[]; }

export interface OutsideOrigin { origin_id: string; origin: string; }

/** An outside service: its id never changes, the name is only a label. Addresses only, never a token. */
export interface OutsideGroup {
  service_id: string;
  name: string;
  origins: OutsideOrigin[];
  /** The Citadel services that use it. */
  used_by: string[];
}

export interface OutsideView { groups: OutsideGroup[]; }

export const treasuryAdminClient = {
  getOutside: () => apiRequest<OutsideView>("GET", "/api/admin/treasury/outside"),
  renameOutside: (serviceId: string, name: string) =>
    apiRequest<OutsideGroup>("PATCH", `/api/admin/treasury/outside/${encodeURIComponent(serviceId)}`, { name }),
  /** The page asks the user first, so these always confirm. */
  deleteOutsideOrigin: (originId: string) =>
    apiRequest<OutsideView>("DELETE", `/api/admin/treasury/outside/origins/${encodeURIComponent(originId)}?confirm=true`),
  deleteOutsideGroup: (serviceId: string) =>
    apiRequest<OutsideView>("DELETE", `/api/admin/treasury/outside/${encodeURIComponent(serviceId)}?confirm=true`),
  getServices: () => apiRequest<ServicesView>("GET", "/api/admin/treasury/services"),
  putService: (name: string, url: string) => apiRequest<ServicesView>("PUT", `/api/admin/treasury/services/${encodeURIComponent(name)}`, { url }),
  deleteService: (name: string) => apiRequest<ServicesView>("DELETE", `/api/admin/treasury/services/${encodeURIComponent(name)}`),
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
