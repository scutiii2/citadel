import { apiRequest } from "../../../api/http";

export type SkillStatus = "proposed" | "active" | "retired";

/** A how-to the assistant proposed. Only `active` skills are ever used; the user approves them. */
export interface Skill {
  id: number;
  title: string;
  when_to_use: string;
  steps: string;
  tools: string;
  status: SkillStatus;
  successes: number;
  failures: number;
  created_at: string;
  /** It failed often and more often than it worked, so Ember is no longer offered it. Editing resets the counts. */
  failing: boolean;
}

export type SkillText = Pick<Skill, "title" | "when_to_use" | "steps" | "tools">;

/** The limits the server enforces. */
export const SKILL_LIMITS = { title: 80, when_to_use: 300, steps: 1200, tools: 200 } as const;

export const skillsClient = {
  list: () => apiRequest<Skill[]>("GET", "/api/skills"),
  setStatus: (id: number, status: SkillStatus) => apiRequest<Skill>("PUT", `/api/skills/${id}/status`, { status }),
  update: (id: number, text: SkillText) => apiRequest<Skill>("PUT", `/api/skills/${id}`, text),
  remove: (id: number) => apiRequest<void>("DELETE", `/api/skills/${id}`),
};
