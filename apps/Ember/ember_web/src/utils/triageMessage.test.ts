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

  it("says unknown with the candidates it could not tell apart", () => {
    const text = triageAnswerText({
      kind: "choice", choice: "database", confidence: 0.5, uncertain: true, unknown: true,
      candidates: ["database", "network"], probabilities: { database: 0.5, network: 0.5 },
    });

    expect(text).toContain("**Unknown**, it could be database or network; check both.");
    expect(text).not.toContain("Also check");
  });
});
