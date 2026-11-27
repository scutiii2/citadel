import { afterEach, describe, expect, it } from "vitest";
import { installFileDropGuard } from "./fileDrop";

let remove: (() => void) | undefined;
afterEach(() => {
  remove?.();
  document.body.innerHTML = "";
});

function drag(type: "dragover" | "drop", types: string[], target: EventTarget = document.body) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  const dataTransfer = { types, dropEffect: "copy" };
  Object.assign(event, { dataTransfer });
  target.dispatchEvent(event);
  return { event, dataTransfer };
}

describe("installFileDropGuard", () => {
  it("refuses files dragged or dropped outside any drop zone, so the page is not replaced", () => {
    remove = installFileDropGuard();

    const over = drag("dragover", ["Files"]);
    const drop = drag("drop", ["Files"]);

    expect(over.event.defaultPrevented).toBe(true);
    expect(over.dataTransfer.dropEffect).toBe("none");
    expect(drop.event.defaultPrevented).toBe(true);
  });

  it("leaves dragged text, drop zones and file fields alone", () => {
    document.body.innerHTML = '<div id="zone"></div><input type="file" />';
    const zone = document.getElementById("zone")!;
    zone.addEventListener("dragover", (event) => event.preventDefault());
    remove = installFileDropGuard();

    expect(drag("dragover", ["text/plain"]).event.defaultPrevented).toBe(false);
    expect(drag("dragover", ["Files"], zone).dataTransfer.dropEffect).toBe("copy");
    expect(drag("dragover", ["Files"], document.querySelector("input")!).event.defaultPrevented).toBe(false);
  });

  it("can be removed", () => {
    installFileDropGuard()();

    expect(drag("dragover", ["Files"]).event.defaultPrevented).toBe(false);
  });
});
