import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { usePolling } from "./usePolling";

function setHidden(hidden: boolean): void {
  Object.defineProperty(document, "hidden", { configurable: true, value: hidden });
  document.dispatchEvent(new Event("visibilitychange"));
}

function mountPolling(fn: () => void) {
  return mount(defineComponent({ setup() { usePolling(fn, 1000); return () => h("span"); } }));
}

beforeEach(() => {
  vi.useFakeTimers();
  setHidden(false);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("usePolling", () => {
  it("calls on every interval, not on mount", () => {
    const fn = vi.fn();
    mountPolling(fn);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(3000);
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("pauses while hidden and calls once on return", () => {
    const fn = vi.fn();
    mountPolling(fn);
    setHidden(true);
    vi.advanceTimersByTime(5000);
    expect(fn).not.toHaveBeenCalled();
    setHidden(false);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("stops after unmount", () => {
    const fn = vi.fn();
    const wrapper = mountPolling(fn);
    wrapper.unmount();
    vi.advanceTimersByTime(5000);
    setHidden(false);
    expect(fn).not.toHaveBeenCalled();
  });
});
