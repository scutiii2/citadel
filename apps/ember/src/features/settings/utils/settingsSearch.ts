import { matchesWords } from "../../../utils/search";

/** What the settings search looks at: the words a person might type for a setting. */
export interface SearchableSetting {
  label: string;
  description: string;
  /** Extra words that should find the setting ("dark mode" for the theme). */
  keywords?: readonly string[];
}

/** Whether every word in `query` appears in the setting's label, description or
 * keywords, in any order and any case. An empty query matches everything. */
export function matchesQuery(setting: SearchableSetting, query: string): boolean {
  return matchesWords(query, setting.label, setting.description, ...(setting.keywords ?? []));
}

/** The settings that match `query`, in their original order. */
export function filterSettings<T extends SearchableSetting>(settings: readonly T[], query: string): T[] {
  return settings.filter((s) => matchesQuery(s, query));
}
