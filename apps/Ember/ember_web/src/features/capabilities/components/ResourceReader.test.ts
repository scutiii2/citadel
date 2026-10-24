import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import ResourceReader from "./ResourceReader.vue";
it("keeps the URI form visibly pending and ignores repeated reads", async () => {
 const w = mount(ResourceReader, { props: { pending: true, reading: "test://uri", uri: "test://uri", readResult: null, readError: "", text: "" } });
 expect(w.get("button").text()).toBe("Reading…");
 expect(w.get("button").attributes("aria-busy")).toBe("true");
 expect(w.get("input").attributes("disabled")).toBeDefined();
 await w.get("form").trigger("submit");
 expect(w.emitted("read")).toBeUndefined();
 await w.setProps({ pending: false });
 await w.get("form").trigger("submit");
 expect(w.emitted("read")).toEqual([["test://uri"]]);
 w.unmount();
});
