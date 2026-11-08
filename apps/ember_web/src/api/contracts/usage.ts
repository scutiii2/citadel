/** A rolling limit window. limit 0 = unlimited; times are naive UTC. */
export interface UsageWindow {
  used: number;
  limit: number;
  reset_at: string | null;
}
