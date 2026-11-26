import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { PendingElicitation } from "../../../api/types";
import ElicitationCard from "./ElicitationCard.vue";

const FORM: PendingElicitation = {
  id: "e1", server: "Notes", tool: "save", mode: "form", message: "<b>Which folder?</b>", agent_label: "Writer",
  fields: [
    { name: "folder", label: "Folder", kind: "text", required: true, max_length: 20 },
    { name: "count", label: "Count", kind: "integer", required: false, min: 1 },
    { name: "tags", label: "Tags", kind: "multi_choice", required: false, options: [{ value: "a", label: "A" }] },
    { name: "pin", label: "Pin", kind: "boolean", required: false },
  ],
};
const LINK: PendingElicitation = {
  id: "e2", server: "Notes", tool: "login", mode: "url", message: "Sign in", url: "https://bücher.example/login",
};

function mountCard(pending: PendingElicitation = FORM, props: Record<string, unknown> = {}) {
  return mount(ElicitationCard, { props: { pending, answering: false, ...props } });
}

describe("ElicitationCard", () => {
  it("names the asker, shows the message as plain text and warns about secrets", () => {
    const w = mountCard();

    expect(w.text()).toContain("Notes asks");
    expect(w.text()).toContain("Writer · save");
    expect(w.get(".message").text()).toBe("<b>Which folder?</b>");
    expect(w.find(".message b").exists()).toBe(false);
    expect(w.text()).toContain("Do not enter passwords or keys here.");
  });

  it("puts an error beside the field and keeps what was typed", async () => {
    const w = mountCard();
    const inputs = w.findAll('input[type="text"]');
    await inputs[1]!.setValue("many");

    await w.get("form").trigger("submit");

    expect(w.findAll(".field")[0]!.get(".error").text()).toBe("This field is required.");
    expect(w.findAll(".field")[1]!.get(".error").text()).toBe("Enter a whole number.");
    expect((inputs[1]!.element as HTMLInputElement).value).toBe("many");
    expect(w.emitted("answer")).toBeUndefined();
  });

  it("sends typed values", async () => {
    const w = mountCard();
    const inputs = w.findAll('input[type="text"]');
    await inputs[0]!.setValue("Work");
    await inputs[1]!.setValue("2");
    await w.get(".tick input").setValue(true);
    await w.findAll('input[role="switch"]')[1]!.setValue(true);

    await w.get("form").trigger("submit");

    expect(w.emitted("answer")).toEqual([["e1", "accept", { folder: "Work", count: 2, tags: ["a"], pin: true }]]);
  });

  it("sends long text from a text area", async () => {
    const w = mountCard({ ...FORM, fields: [{ name: "note", label: "Note", kind: "text", required: true, max_length: 500 }] });
    await w.get("textarea").setValue("two\nlines");

    await w.get("form").trigger("submit");

    expect(w.emitted("answer")).toEqual([["e1", "accept", { note: "two\nlines" }]]);
  });

  it("shows the server's refusal beside the field it names", () => {
    const w = mountCard(FORM, { problem: "Folder: use at most 20 characters." });

    expect(w.findAll(".field")[0]!.get(".error").text()).toBe("use at most 20 characters.");
  });

  it("declines and cancels without values", async () => {
    const w = mountCard();

    await w.get("button.decline").trigger("click");
    await w.get("button.cancel").trigger("click");

    expect(w.emitted("answer")).toEqual([["e1", "decline", undefined], ["e1", "cancel", undefined]]);
  });

  it("offers a link safely and continues only after it was opened", async () => {
    const w = mountCard(LINK);
    const anchor = w.get("a.open");

    expect(w.get(".site").text()).toContain("xn--bcher-kva.example");
    expect(anchor.attributes("rel")).toBe("noopener noreferrer");
    expect(anchor.attributes("target")).toBe("_blank");
    expect((w.get("button.submit").element as HTMLButtonElement).disabled).toBe(true);
    await anchor.trigger("click");
    expect(w.emitted("answer")).toBeUndefined();
    await w.get("button.submit").trigger("click");

    expect(w.emitted("answer")).toEqual([["e2", "accept", undefined]]);
  });

  it("offers no link that is not https", () => {
    const w = mountCard({ ...LINK, url: "javascript:alert(1)" });

    expect(w.find("a.open").exists()).toBe(false);
  });
});
