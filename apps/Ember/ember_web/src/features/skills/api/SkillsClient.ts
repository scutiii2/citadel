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
}

export const skillsClient = {
  list: () => apiRequest<Skill[]>("GET", "/api/skills"),
  setStatus: (id: number, status: SkillStatus) => apiRequest<Skill>("PUT", `/api/skills/${id}/status`, { status }),
  remove: (id: number) => apiRequest<void>("DELETE", `/api/skills/${id}`),
};
