import { apiRequest } from "../../../api/http";
import type { BrainFile, BrainList, BrainSummary, SearchHit } from "../../notes/api/BrainClient";
import type { Landing, Share, ShareDetail } from "../../sharing/api/SharingClient";
import type { Skill, SkillStatus, SkillText } from "../../skills/api/SkillsClient";

/** Shown on the page and by the server: the global brain is read by everyone and every agent. */
export const GLOBAL_NOTICE = "Everyone on this instance, and every agent, can read this. Do not put private data here.";

export interface GlobalFileDraft {
  title: string;
  body: string;
  folder: string;
}
export type GlobalFileChanges = Partial<GlobalFileDraft>;
export type GlobalSummary = BrainSummary & { notice: string };

const base = "/api/brain/global";
const file = (id: string) => `${base}/files/${encodeURIComponent(id)}`;
const skill = (id: number) => `${base}/skills/${id}`;
const share = (id: string) => `${base}/shares/${encodeURIComponent(id)}`;

/** Portcullis' /api/brain/global routes, passed on to Stronghold. Anyone signed in reads; `brain.global.write`
 * writes, lists every skill and reads the queue. */
export const globalClient = {
  list: (folder?: string) => apiRequest<BrainList>("GET", folder ? `${base}/files?folder=${encodeURIComponent(folder)}` : `${base}/files`),
  get: (id: string) => apiRequest<BrainFile>("GET", file(id)),
  search: async (q: string) => (await apiRequest<{ results: SearchHit[] }>("GET", `${base}/search?q=${encodeURIComponent(q)}`)).results,
  summary: () => apiRequest<GlobalSummary>("GET", `${base}/summary`),
  create: (draft: GlobalFileDraft) => apiRequest<BrainFile>("POST", `${base}/files`, draft),
  /** With the revision the server refuses (412) when the file was saved since it was opened. */
  update: (id: string, changes: GlobalFileChanges, expectedRevision: number) =>
    apiRequest<BrainFile>("PUT", file(id), { ...changes, expected_revision: expectedRevision }),
  remove: (id: string) => apiRequest<void>("DELETE", file(id)),
  /** The skills agents are offered: active and not failing. */
  skills: () => apiRequest<Skill[]>("GET", `${base}/skills`),
  /** Every skill with its status (writer). */
  allSkills: () => apiRequest<Skill[]>("GET", `${base}/skills/all`),
  setSkillStatus: (id: number, status: SkillStatus) => apiRequest<Skill>("PUT", `${skill(id)}/status`, { status }),
  updateSkill: (id: number, text: SkillText) => apiRequest<Skill>("PUT", skill(id), text),
  removeSkill: (id: number) => apiRequest<void>("DELETE", skill(id)),
  /** Shares sent to the global brain that wait for a reviewer, newest first (writer). */
  queue: async () => (await apiRequest<{ shares: Share[] }>("GET", `${base}/shares`)).shares,
  share: (id: string) => apiRequest<ShareDetail>("GET", share(id)),
  approve: (id: string, landing: Landing = {}) => apiRequest<Share>("POST", `${share(id)}/approve`, landing),
  reject: (id: string) => apiRequest<Share>("POST", `${share(id)}/reject`),
};
