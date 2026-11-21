import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../stores/auth";
import { makeAccount } from "../../testing/account";
import GlobalView from "./GlobalView.vue";

vi.mock("./components/GlobalFiles.vue", () => ({
  default: { props: ["canWrite"], template: '<div data-test="files">files {{ canWrite }}</div>' },
}));
vi.mock("./components/GlobalSkills.vue", () => ({
  default: { props: ["canWrite"], template: '<div data-test="skills">skills {{ canWrite }}</div>' },
}));
vi.mock("./components/GlobalQueue.vue", () => ({
  default: {
    emits: ["added"],
    template: '<button type="button" data-test="queue" @click="$emit(\'added\', \'notes\')">queue</button>',
  },
}));

let wrapper: VueWrapper | null = null;
function mountIt(permissions: string[]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.account = makeAccount({ permissions });
  wrapper = mount(GlobalView, { attachTo: document.body, global: { plugins: [pinia] } });
  return { w: wrapper, auth };
}
const tab = (w: VueWrapper, name: string) => w.findAll("[role='tab']").find((t) => t.text() === name);
afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
});

describe("GlobalView", () => {
  it("always shows the notice, and a reader gets the notes and skills tabs only", async () => {
    const { w } = mountIt(["chat.use"]);
    await flushPromises();
    expect(w.text()).toContain("Everyone on this instance, and every agent, can read this. Do not put private data here.");
    expect(w.findAll("[role='tab']").map((t) => t.text())).toEqual(["Notes", "Skills"]);
    expect(w.get("[data-test='files']").text()).toBe("files false");
    await tab(w, "Skills")!.trigger("click");
    expect(w.get("#global-panel-skills").attributes("aria-labelledby")).toBe(tab(w, "Skills")!.attributes("id"));
    expect(tab(w, "Skills")!.attributes("aria-controls")).toBe("global-panel-skills");
    expect(w.get("[data-test='skills']").text()).toBe("skills false");
  });

  it("shows the review queue tab to a writer and switches sections", async () => {
    const { w } = mountIt(["chat.use", "brain.global.write"]);
    await flushPromises();
    expect(w.findAll("[role='tab']").map((t) => t.text())).toEqual(["Notes", "Skills", "Review queue"]);
    expect(w.get("[data-test='files']").text()).toBe("files true");
    await tab(w, "Review queue")!.trigger("click");
    expect(w.find("[data-test='queue']").exists()).toBe(true);
    await tab(w, "Skills")!.trigger("click");
    expect(w.get("[data-test='skills']").text()).toBe("skills true");
  });

  it("refreshes the file list after approving a file and preserves the skills section", async () => {
    const { w } = mountIt(["chat.use", "brain.global.write"]);
    const files = w.get("[data-test='files']").element;
    await tab(w, "Skills")!.trigger("click");
    const skills = w.get("[data-test='skills']").element;
    await tab(w, "Review queue")!.trigger("click");
    await w.get("[data-test='queue']").trigger("click");
    expect(w.get("[data-test='files']").element).not.toBe(files);
    expect(w.get("[data-test='skills']").element).toBe(skills);
  });

  it("falls back to the notes tab when the writer permission is lost", async () => {
    const { w, auth } = mountIt(["chat.use", "brain.global.write"]);
    await flushPromises();
    await tab(w, "Review queue")!.trigger("click");
    auth.account = makeAccount({ permissions: ["chat.use"] });
    await flushPromises();
    expect(w.find("[data-test='queue']").exists()).toBe(false);
    expect(w.find("[data-test='files']").exists()).toBe(true);
    expect(tab(w, "Review queue")).toBeUndefined();
  });
});
