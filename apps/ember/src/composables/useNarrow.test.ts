import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { useNarrow } from "./useNarrow";

function fakeQuery(matches: boolean) {
  let listener: ((event: MediaQueryListEvent) => void) | undefined;
  const query = {
    matches,
    addEventListener: vi.fn((_: string, fn: typeof listener) => { listener = fn; }),
    removeEventListener: vi.fn(),
  };
  vi.stubGlobal("matchMedia", () => query);
  return { query, fire: (next: boolean) => listener?.({ matches: next } as MediaQueryListEvent) };
}

const Probe = defineComponent({ setup() { const narrow = useNarrow(); return () => h("p", String(narrow.value)); } });

describe("useNarrow", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("starts from the media query and follows changes until unmounted", async () => {
    const { query, fire } = fakeQuery(true);
    const w = mount(Probe);
    expect(w.text()).toBe("true");
    fire(false);
    await w.vm.$nextTick();
    expect(w.text()).toBe("false");
    w.unmount();
    expect(query.removeEventListener).toHaveBeenCalled();
  });

  it("is false when matchMedia is missing", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(mount(Probe).text()).toBe("false");
  });
});
