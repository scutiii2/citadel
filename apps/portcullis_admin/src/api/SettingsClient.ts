import { apiRequest } from "./http";

/** Pages hidden from every account's sidebar (route paths such as "/usage"). Nav only. */
export interface HiddenPages {
  hidden: string[];
}

export const settingsClient = {
  /** Any logged-in account may read the hidden pages. */
  pages: () => apiRequest<HiddenPages>("GET", "/api/settings/pages"),
  /** settings.manage only. Replaces the list; portcullis refuses "/" and "/settings". */
  setPages: (hidden: string[]) => apiRequest<HiddenPages>("PUT", "/api/admin/settings/pages", { hidden }),
};
