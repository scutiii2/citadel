import type { Conversation } from "../../../api/types";

/** Same shape as chat_app's export (chats_store.export_messages): a title
 * heading, the export time, then each message under a speaker heading. */
export function conversationToMarkdown(conversation: Conversation, agentLabel: string | null): string {
  const lines = [`# ${conversation.title}`, "", `Exported: ${new Date().toISOString()}`];
  if (agentLabel) lines.push(`Agent: ${agentLabel}`);
  lines.push("");
  for (const message of conversation.messages) {
    if (message.kind === "log_attachment") {
      lines.push("## Earlier messages (raw log)", "", fence(message.content), "");
    } else if (message.kind === "summary") {
      lines.push("## Summary of the earlier conversation", "", message.content.trim(), "");
    } else if (message.kind === "command") {
      lines.push(`## ${message.role === "user" ? "Command" : "Command result"}`, "", message.content.trim(), "");
    } else {
      lines.push(`## ${message.role === "user" ? "You" : "Assistant"}`, "", message.content.trim(), "");
    }
  }
  return lines.join("\n");
}

/** A code fence longer than any backtick run inside `text`. */
function fence(text: string): string {
  const longest = Math.max(0, ...(text.match(/`+/g) ?? []).map((run) => run.length));
  const ticks = "`".repeat(Math.max(3, longest + 1));
  return `${ticks}text\n${text.trimEnd()}\n${ticks}`;
}
