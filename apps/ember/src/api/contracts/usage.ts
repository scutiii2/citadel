export type WindowName = "six_hour" | "weekly";
export type ResetKind = WindowName | "both";

/** A rolling limit window. limit 0 = unlimited; times are naive UTC. */
export interface UsageWindow {
  /** Tokens as the limit counts them. */
  used: number;
  /** With any boost applied. */
  limit: number;
  reset_at: string | null;
  /** Absent from a server without boosts. */
  boost?: { percent: number; ends_at: string } | null;
}

/** An unused free reset. Times are naive UTC. */
export interface FreeReset {
  id: string;
  kind: ResetKind;
  granted_at: string;
  expires_at: string | null;
}

/** An account's limits, free resets and automatic switch. The reset fields are absent from an older server. */
export interface UsageOverview {
  six_hour: UsageWindow;
  weekly: UsageWindow;
  /** Soonest expiry first. */
  resets?: FreeReset[];
  auto_use?: boolean;
  /** How much of cached input counts toward the limits, 0 to 1. */
  cached_token_weight?: number;
}
