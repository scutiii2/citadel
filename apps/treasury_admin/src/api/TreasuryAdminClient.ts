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

export const treasuryAdminClient = {
  get: () => apiRequest<TreasuryView>("GET", "/api/admin/treasury"),
};
