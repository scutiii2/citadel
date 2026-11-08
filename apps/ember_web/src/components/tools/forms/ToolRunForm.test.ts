import { useAuthStore } from "../../../stores/auth";
import { createPinia, setActivePinia } from "pinia";
import { commandsClient } from "../../../api/tools/CommandsClient";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { JsonSchema } from "../../../api/types";
import ToolRunForm from "./ToolRunForm.vue";

vi.mock("../../../api/tools/CommandsClient", () => ({ commandsClient: { options: vi.fn(), upload: vi.fn() } }));

const SCHEMA: JsonSchema = {
  type: "object",
  properties: {
    length: { type: "integer", minimum: 8, maximum: 128, default: 20, input: "range" },
    use_upper: { type: "boolean", default: true },
  },
};

const mountForm = (props: Record<string, unknown> = {}) =>
  mount(ToolRunForm, { props: { schema: SCHEMA, running: false, ...props } });

describe("ToolRunForm live mode", () => {
  it("runs once on mount with the defaults", () => {
    const w = mountForm({ live: true });
    expect(w.emitted("run")).toEqual([[{ length: 20, use_upper: true }]]);
  });

  it("does not run on mount when not live", () => {
    expect(mountForm().emitted("run")).toBeUndefined();
  });

  it("runs when a control is committed, not while a slider is still moving", async () => {
    const w = mountForm({ live: true });
    const slider = w.get("input[type=range]");
    (slider.element as HTMLInputElement).value = "64";
    await slider.trigger("input"); // dragging fires only `input` (VTU's setValue would also fire `change`)
    expect(w.emitted("run")).toHaveLength(1);
    await slider.trigger("change"); // the release
    expect(w.emitted("run")).toHaveLength(2);
    expect(w.emitted("run")![1]).toEqual([{ length: 64, use_upper: true }]);
  });

  it("runs when a toggle chip changes", async () => {
    const w = mountForm({ live: true });
    await w.get("input[type=checkbox]").setValue(false);
    await w.get("input[type=checkbox]").trigger("change");
    expect(w.emitted("run")!.at(-1)).toEqual([{ length: 20, use_upper: false }]);
  });

  it("does not run for values that do not validate", async () => {
    const schema: JsonSchema = { type: "object", properties: { secret: { type: "string" } }, required: ["secret"] };
    const w = mountForm({ live: true, schema });
    expect(w.emitted("run")).toBeUndefined();
    (w.get("input").element as HTMLInputElement).value = "abc";
    await w.get("input").trigger("input");
    await w.get("input").trigger("change");
    expect(w.emitted("run")).toEqual([[{ secret: "abc" }]]);
  });

  it("hides the Run button when live and shows the slider's value either way", () => {
    const live = mountForm({ live: true });
    expect(live.find("button.run").exists()).toBe(false);
    expect(live.get("output").text()).toBe("20");
    expect(mountForm().find("button.run").exists()).toBe(true);
    // A form that is not live shows the value too, and keeps its Run button.
    const plain = mountForm();
    expect(plain.get("output").text()).toBe("20");
    expect(plain.find("button.run").exists()).toBe(true);
  });

  it("a number range field without a step takes any value, an integer one whole steps", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        ratio: { type: "number", minimum: 0, maximum: 1, default: 0.5, input: "range" },
        count: { type: "integer", minimum: 1, maximum: 9, default: 3, input: "range" },
      },
    };
    const w = mountForm({ schema });
    expect(w.get('[id$="-ratio"]').attributes("step")).toBe("any");
    expect(w.get('[id$="-count"]').attributes("step")).toBe("1");
  });

  it("a normal form ignores change events", async () => {
    const w = mountForm();
    await w.get("input[type=range]").trigger("change");
    expect(w.emitted("run")).toBeUndefined();
  });
});


beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "admin", email: "a@example.com", email_verified: true, roles: [], permissions: ["tools.execute", "files.upload"] };
});

it("does not run a live form without tools.execute", () => {
  useAuthStore().account!.permissions = [];
  expect(mountForm({ live: true }).emitted("run")).toBeUndefined();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
it.each(["success", "failure"])("ignores old dependent choices %s after replacement and clearing", async (outcome) => {
  const first = deferred<never[]>(); const second = deferred<never[]>();
  vi.mocked(commandsClient.options).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const w = mountForm({ schema: { type: "object", properties: {
    parent: { type: "string" }, child: { type: "string", options_url: "/choices", depends_on: "parent" },
  } } });
  await w.get('[id$="-parent"]').setValue("A");
  await w.get('[id$="-parent"]').setValue("B");
  if (outcome === "failure") first.reject(new Error("old failure")); else first.resolve([]);
  await flushPromises();
  expect(w.get('[id$="-child"]').element.tagName).toBe("SELECT");
  expect(w.get('[id$="-child"]').attributes("disabled")).toBeDefined();
  await w.get('[id$="-parent"]').setValue("");
  second.resolve([]); await flushPromises();
  expect(w.get('[id$="-child"]').text()).toContain("choose parent first");
  w.unmount();
});
it.each(["success", "failure"])("keeps a newer upload busy after older same-name upload %s", async (outcome) => {
  const first = deferred<string>(); const second = deferred<string>();
  vi.mocked(commandsClient.upload).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const w = mountForm({ schema: { type: "object", properties: { file: { type: "string", input: "file" } } } });
  const input = w.get('input[type="file"]');
  Object.defineProperty(input.element, "files", { configurable: true, value: [new File(["a"], "same.txt")] });
  await input.trigger("change");
  Object.defineProperty(input.element, "files", { configurable: true, value: [new File(["b"], "same.txt")] });
  await input.trigger("change");
  if (outcome === "failure") first.reject(new Error("old failure")); else first.resolve("/old/path");
  await flushPromises();
  expect(w.get('button.run').attributes("disabled")).toBeDefined();
  second.resolve("/new/path"); await flushPromises();
  await w.get("form").trigger("submit");
  expect(w.emitted("run")!.at(-1)).toEqual([{ file: "/new/path" }]);
  w.unmount();
});
