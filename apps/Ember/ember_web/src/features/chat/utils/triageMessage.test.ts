import { describe, expect, it } from "vitest";
import type { TriageForm } from "../api/TriageClient";
import { triageAnswerText, triageQuestionText } from "./triageMessage";

const CHOICE: TriageForm = {
  kind: "choice",
  text: "SQLite database is locked",
  question: "Which area?",
  options: [
    { title: "database", description: "SQL and storage" },
    { title: "network", description: "Connections" },
  ],
};

describe("the saved question", () => {
  it("lists the options of a multiple choice question", () => {
    expect(triageQuestionText(CHOICE)).toBe(
      "Triage question: Which area?\n\nSQLite database is locked\n\nOptions:\n- database: SQL and storage\n- network: Connections",
    );
  });

  it("asks for a yes or no", () => {
    const text = triageQuestionText({ kind: "yes_no", text: "It is down", question: "Is there a problem?", options: [] });

    expect(text).toBe("Triage question: Is there a problem?\n\nIt is down\n\nAnswer yes or no.");
  });

  it("numbers the levels of a score question from 1", () => {
    const text = triageQuestionText({
      kind: "score", text: "It is down", question: "How urgent?", options: [], levels: ["Can wait", "Right now"],
    });

    expect(text).toBe("Triage question: How urgent?\n\nIt is down\n\nRate from 1 to 2:\n- 1: Can wait\n- 2: Right now");
  });
});

describe("the saved answer", () => {
  it("names a yes with its confidence and odds", () => {
    const text = triageAnswerText({ kind: "yes_no", answer: "yes", yes: 0.82, confidence: 0.82, uncertain: false });

    expect(text).toBe("**Yes**, 82% sure.\n\nProbability of yes: 82%.");
  });

  it("marks an uncertain answer as provisional", () => {
    const text = triageAnswerText({ kind: "yes_no", answer: "no", yes: 0.4, confidence: 0.6, uncertain: true });

    expect(text).toContain("**No**, 60% sure (uncertain: treat it as provisional).");
  });

  it("ranks the options of a choice and lists what else to check", () => {
    const text = triageAnswerText({
      kind: "choice", choice: "database", confidence: 0.9, uncertain: false,
      probabilities: { network: 0.1, database: 0.9 }, also_check: ["network"],
    });

    expect(text).toBe(
      "**database**, 90% sure.\n\n| Option | Probability |\n| --- | --- |\n| database | 90% |\n| network | 10% |\n\nAlso check: network.",
    );
  });

  it("names the nearest level of a score and shows the score on a 1-based scale", () => {
    const text = triageAnswerText({
      kind: "score", score: 1.2346, levels: ["Can wait", "Soon", "Right now"], confidence: 0.7, uncertain: false,
    });

    expect(text).toBe("**Soon**, 70% sure.\n\nScore: 2.2 of 3 (1 = Can wait, 3 = Right now).");
  });

  it("adds who answered and every model call when the question asked for a trace", () => {
    const text = triageAnswerText({
      kind: "choice", choice: "b", confidence: 0.72, uncertain: false, probabilities: { b: 0.72, d: 0.28 },
      answered_by: "laya-english+laya-typed", resolved_by: "local",
      rounds: [
        { step: "laya-english", choice: "b", confidence: 0.6, threshold: 0.75, probabilities: { d: 0.4, b: 0.6 } },
        { step: "laya-typed", choice: "b", confidence: 0.72, threshold: 0.55, probabilities: { b: 0.72, d: 0.28 } },
        { step: "jev", failed: "could not answer" },
      ],
    });

    expect(text).toContain("\n\n**Details**\nAnswered by laya-english and laya-typed (local).\n\n");
    expect(text).toContain("- **laya-english**: picked b; 60% sure (needed 75%); b 60%, d 40%");
    expect(text).toContain("- **laya-typed**: picked b; 72% sure (needed 55%); b 72%, d 28%");
    expect(text).toContain("- **jev**: could not answer");
  });

  it("shows no details without a trace", () => {
    const text = triageAnswerText({ kind: "yes_no", answer: "yes", yes: 0.82, confidence: 0.82, uncertain: false });

    expect(text).not.toContain("Details");
  });

  it("says unknown with the candidates it could not tell apart", () => {
    const text = triageAnswerText({
      kind: "choice", choice: "database", confidence: 0.5, uncertain: true, unknown: true,
      candidates: ["database", "network"], probabilities: { database: 0.5, network: 0.5 },
    });

    expect(text).toContain("**Unknown**, it could be database or network; check both.");
    expect(text).not.toContain("Also check");
  });
});
