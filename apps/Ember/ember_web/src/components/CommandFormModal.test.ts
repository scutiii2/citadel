import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "../stores/auth";
import { buildArguments, parseCommand } from "../services/slashCommands";
import type { JsonSchema } from "../api/types";
import CommandFormModal from "./CommandFormModal.vue";

const command = { capability: "ticket", name: "create", tool_name: "tool_ticket_createTicket", description: "File a ticket" };
const schema: JsonSchema = {
  type: "object",
  properties: {
    title: { type: "string" },
    source: { type: "string", enum: ["user", "ai_user_request", "ai_auto"], default: "user" },
    chat_id: { type: "string", default: "" },
    agent: { type: "string" },
    tool_name: { type: "string" },
    error_text: { type: "string" },
    tags: { type: ["array", "null"], items: { type: "string", enum: ["ui", "chat"] }, input: "tags", maxItems: 5, default: null },
  },
  required: ["title"],
};

beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().hasPermission = () => true;
});

describe("manual ticket command form", () => {
  it("adds the source and current chat automatically while retaining editable failure details", async () => {
    const wrapper = mount(CommandFormModal, { props: { command, schema, chatId: "chat-123" } });
    expect(wrapper.find("#field-source").exists()).toBe(false);
    expect(wrapper.find("#field-chat_id").exists()).toBe(false);
    await wrapper.get("#field-title").setValue("Report a bug");
    await wrapper.get("#field-agent").setValue("Ember");
    await wrapper.get("#field-tool_name").setValue("tool_example");
    await wrapper.get("#field-error_text").setValue("Exact error text");
    await wrapper.get("form").trigger("submit");
    const params = parseCommand(wrapper.emitted("submit")![0]![0] as string).params;
    expect(params).toEqual({ title: "Report a bug", source: "user", chat_id: "chat-123", agent: "Ember", tool_name: "tool_example", error_text: "Exact error text" });
    expect(schema.properties!.chat_id!.default).toBe("");
  });

  it("serializes tag selections as the array the ticket tool expects", async () => {
    const wrapper = mount(CommandFormModal, { props: { command, schema, chatId: "chat-123" } });
    await wrapper.get("#field-title").setValue("Table layout");
    await wrapper.get("#field-tags").setValue("ui");
    await wrapper.get("#field-tags").setValue("chat");
    await wrapper.get("form").trigger("submit");
    const parsed = parseCommand(wrapper.emitted("submit")![0]![0] as string);
    expect(buildArguments(parsed, schema)).toEqual({ title: "Table layout", tags: ["ui", "chat"], source: "user", chat_id: "chat-123" });
  });

  it("omits the chat id when no chat exists yet", async () => {
    const wrapper = mount(CommandFormModal, { props: { command, schema } });
    await wrapper.get("#field-title").setValue("Feature request");
    await wrapper.get("form").trigger("submit");
    expect(parseCommand(wrapper.emitted("submit")![0]![0] as string).params).toEqual({ title: "Feature request", source: "user" });
  });

  it("leaves the same fields on other tools editable", () => {
    const wrapper = mount(CommandFormModal, { props: { command: { ...command, tool_name: "extension__create" }, schema, chatId: "chat-123" } });
    expect(wrapper.find("#field-source").exists()).toBe(true);
    expect((wrapper.get("#field-chat_id").element as HTMLInputElement).value).toBe("");
  });
});
