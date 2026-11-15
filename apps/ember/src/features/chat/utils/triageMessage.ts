import type { TriageAnswer, TriageForm, TriageRound } from "../api/TriageClient";

const percent = (value: number): string => `${Math.round(value * 100)}%`;

/** The user's side of a saved triage exchange: what was asked, as plain readable text. */
export function triageQuestionText(form: TriageForm): string {
  const lines = [`Triage question: ${form.question}`, "", form.text];
  if (form.kind === "choice") {
    lines.push("", "Options:", ...form.options.map((o) => `- ${o.title}: ${o.description}`));
  } else if (form.kind === "score") {
    const levels = form.levels ?? [];
    lines.push("", `Rate from 1 to ${levels.length}:`, ...levels.map((d, i) => `- ${i + 1}: ${d}`));
  } else {
    lines.push("", "Answer yes or no.");
  }
  return lines.join("\n");
}

const odds = (probabilities: Record<string, number>): string =>
  Object.entries(probabilities)
    .sort((a, b) => b[1] - a[1])
    .map(([name, p]) => `${name} ${percent(p)}`)
    .join(", ");

function roundLine(round: TriageRound): string {
  if (round.failed) return `- **${round.step}**: ${round.failed}`;
  const parts: string[] = [];
  if (round.choice) parts.push(`picked ${round.choice}`);
  if (round.confidence !== undefined) {
    parts.push(`${percent(round.confidence)} sure${round.threshold !== undefined ? ` (needed ${percent(round.threshold)})` : ""}`);
  }
  if (round.eliminated?.length) parts.push(`dropped ${round.eliminated.join(", ")}`);
  if (round.probabilities) parts.push(odds(round.probabilities));
  return `- **${round.step}**: ${parts.join("; ")}`;
}

/** The "show details" part: who answered, and every model call in order. Empty without a trace. */
function detailsText(answer: TriageAnswer): string {
  if (!answer.rounds?.length && !answer.answered_by) return "";
  const lines = ["**Details**"];
  if (answer.answered_by) lines.push(`Answered by ${answer.answered_by.split("+").join(" and ")}${answer.resolved_by ? ` (${answer.resolved_by})` : ""}.`);
  if (answer.rounds?.length) lines.push("", ...answer.rounds.map(roundLine));
  return `\n\n${lines.join("\n")}`;
}

/** The assistant's side, as markdown: the pick, how sure it is, and the odds per option. */
export function triageAnswerText(answer: TriageAnswer): string {
  return `${answerBody(answer)}${detailsText(answer)}`;
}

function answerBody(answer: TriageAnswer): string {
  const sure = `${percent(answer.confidence)} sure${answer.uncertain ? " (uncertain: treat it as provisional)" : ""}`;
  if (answer.kind === "yes_no") {
    return `**${answer.answer === "yes" ? "Yes" : "No"}**, ${sure}.\n\nProbability of yes: ${percent(answer.yes)}.`;
  }
  if (answer.kind === "score") {
    const top = answer.levels.length - 1;
    const nearest = Math.min(top, Math.max(0, Math.round(answer.score)));
    return `**${answer.levels[nearest]}**, ${sure}.\n\nScore: ${(answer.score + 1).toFixed(1)} of ${answer.levels.length} (1 = ${answer.levels[0]}, ${answer.levels.length} = ${answer.levels[top]}).`;
  }
  const ranked = Object.entries(answer.probabilities).sort((a, b) => b[1] - a[1]);
  const table = ["| Option | Probability |", "| --- | --- |", ...ranked.map(([name, p]) => `| ${name} | ${percent(p)} |`)];
  const head = answer.unknown
    ? `**Unknown**, it could be ${(answer.candidates ?? []).join(" or ")}; check both. ${sure}.`
    : `**${answer.choice}**, ${sure}.`;
  const also = !answer.unknown && answer.also_check?.length ? `\n\nAlso check: ${answer.also_check.join(", ")}.` : "";
  return `${head}\n\n${table.join("\n")}${also}`;
}
