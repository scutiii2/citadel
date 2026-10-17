import type { TriageAnswer, TriageForm } from "../api/TriageClient";

const percent = (value: number): string => `${Math.round(value * 100)}%`;

/** The user's side of a saved triage exchange: what was asked, as plain readable text. */
export function triageQuestionText(form: TriageForm): string {
  const lines = [`Triage question: ${form.question}`, "", form.text];
  if (form.kind === "choice") {
    lines.push("", "Options:", ...form.options.map((o) => `- ${o.title}: ${o.description}`));
  } else {
    lines.push("", "Answer yes or no.");
  }
  return lines.join("\n");
}

/** The assistant's side, as markdown: the pick, how sure it is, and the odds per option. */
export function triageAnswerText(answer: TriageAnswer): string {
  const sure = `${percent(answer.confidence)} sure${answer.uncertain ? " (uncertain: treat it as provisional)" : ""}`;
  if (answer.kind === "yes_no") {
    return `**${answer.answer === "yes" ? "Yes" : "No"}**, ${sure}.\n\nProbability of yes: ${percent(answer.yes)}.`;
  }
  const ranked = Object.entries(answer.probabilities).sort((a, b) => b[1] - a[1]);
  const table = ["| Option | Probability |", "| --- | --- |", ...ranked.map(([name, p]) => `| ${name} | ${percent(p)} |`)];
  const head = answer.unknown
    ? `**Unknown**, it could be ${(answer.candidates ?? []).join(" or ")}; check both. ${sure}.`
    : `**${answer.choice}**, ${sure}.`;
  const also = !answer.unknown && answer.also_check?.length ? `\n\nAlso check: ${answer.also_check.join(", ")}.` : "";
  return `${head}\n\n${table.join("\n")}${also}`;
}
