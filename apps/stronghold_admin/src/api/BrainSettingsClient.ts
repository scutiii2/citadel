import { apiRequest } from "./http";

export type Part = "stack" | "long_term" | "sharing";

/** Short-term memory, per chat. */
export interface StackLimits {
  max_items: number;
  max_item_chars: number;
  compact_item_chars: number;
  warn_ratio: number;
}

/** Long-term memory files, per account. */
export interface LongTermLimits {
  max_record_chars: number;
  max_files: number;
  max_total_bytes: number;
  search_limit: number;
}

/** Sharing between accounts and to the global brain. */
export interface SharingLimits {
  max_share_chars: number;
  max_pending_sent: number;
  max_inbox: number;
  max_global_queue: number;
}

/** [lowest, highest] allowed value of each setting, as Stronghold checks it. */
export type Ranges = Record<Part, Record<string, [number, number]>>;

export interface BrainSettings {
  stack: StackLimits;
  long_term: LongTermLimits;
  /** Present only when Stronghold's sharing is on. */
  sharing?: SharingLimits;
  ranges: Ranges;
  /** Where the account folders live. Set by STRONGHOLD_BRAIN_ROOT or the `brain/root` setting; read-only here. */
  root: string;
  /** Which part was changed from the built-in defaults. */
  stored: { stack: boolean; long_term: boolean; sharing?: boolean };
}

/** Only the settings that changed, grouped by part. */
export interface BrainSettingsChanges {
  stack?: Partial<StackLimits>;
  long_term?: Partial<LongTermLimits>;
  sharing?: Partial<SharingLimits>;
}

/** Portcullis's /api/admin/stronghold-brain-settings (needs settings.manage), passed on to Stronghold, which checks
 * every value and uses a change at once. */
export const brainSettingsClient = {
  get: () => apiRequest<BrainSettings>("GET", "/api/admin/stronghold-brain-settings"),
  save: (changes: BrainSettingsChanges) => apiRequest<BrainSettings>("PUT", "/api/admin/stronghold-brain-settings", changes),
};
