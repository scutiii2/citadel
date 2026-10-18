import { apiRequest } from "./http";

// The limits ember_api enforces (services/triage_questions.py, routes/triage.py).
export const TRIAGE_TEXT_MAX = 4000;
export const TRIAGE_QUESTION_MAX = 300;
export const TRIAGE_DESCRIPTION_MAX = 300;
export const TRIAGE_TITLE_MAX = 30;
export const TRIAGE_MIN_OPTIONS = 2;
export const TRIAGE_MAX_OPTIONS = 10;

export type TriageKind = "choice" | "yes_no" | "score";

export interface TriageOption {
  /** One word; the answer names it. */
  title: string;
  description: string;
}

/** What the question form holds. */
export interface TriageForm {
  kind: TriageKind;
  text: string;
  question: string;
  /** Multiple choice only. */
  options: TriageOption[];
  /** Score only: what each level means, lowest first. */
  levels?: string[];
}

interface Common {
  /** How sure the model is, 0-1. */
  confidence: number;
  /** Provisional: the model was not sure enough to stand behind it. */
  uncertain: boolean;
}

export interface YesNoAnswer extends Common {
  kind: "yes_no";
  answer: "yes" | "no";
  /** Probability of yes. */
  yes: number;
}

export interface ChoiceAnswer extends Common {
  kind: "choice";
  choice: string;
  probabilities: Record<string, number>;
  also_check?: string[];
  /** Set with `unknown`: the options it could not tell apart. */
  candidates?: string[];
  unknown?: true;
  answered_by?: string;
}

export interface ScoreAnswer extends Common {
  kind: "score";
  /** 0 is the lowest level, `levels.length - 1` the highest; anything in between is a blend. */
  score: number;
  /** What each level means, lowest first. */
  levels: string[];
}

export type TriageAnswer = YesNoAnswer | ChoiceAnswer | ScoreAnswer;

/** ember_api's /api/triage routes (chat.use). */
export const triageClient = {
  /** A one-word title for each description, in order. */
  titles: (descriptions: string[]) =>
    apiRequest<{ titles: string[] }>("POST", "/api/triage/titles", { descriptions }).then((r) => r.titles),
  /** Asks the Triage Assistant directly, without the orchestrator. */
  ask: (form: TriageForm) =>
    apiRequest<TriageAnswer>("POST", "/api/triage/ask", {
      kind: form.kind,
      text: form.text,
      question: form.question,
      options: form.kind === "choice" ? form.options : [],
      levels: form.kind === "score" ? (form.levels ?? []) : [],
    }),
};
