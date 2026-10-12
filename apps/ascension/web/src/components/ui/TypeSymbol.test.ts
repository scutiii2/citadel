import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { typeSymbolUrl } from "../../utils/ascensionTypes";
import TypeSymbol from "./TypeSymbol.vue";

describe("typeSymbolUrl", () => {
  it("names the detailed and the flat file of a known type", () => {
    expect(typeSymbolUrl("abyss", false)).toBe("/assets/types/abyss.webp");
    expect(typeSymbolUrl("abyss", true)).toBe("/assets/types/abyss_flat.webp");
  });
  it("has no symbol for an unknown type", () => {
    expect(typeSymbolUrl("plasma", false)).toBeNull();
  });
});

describe("TypeSymbol", () => {
  it("uses the flat symbol when small and the detailed one when large", () => {
    expect(mount(TypeSymbol, { props: { typeId: "divine", size: 20 } }).find("img").attributes("src")).toBe("/assets/types/divine_flat.webp");
    expect(mount(TypeSymbol, { props: { typeId: "divine", size: 40 } }).find("img").attributes("src")).toBe("/assets/types/divine.webp");
  });
  it("lets a caller force the flat symbol and takes any CSS length as size", () => {
    const img = mount(TypeSymbol, { props: { typeId: "pure", size: "8cqw", flat: true } }).find("img");
    expect(img.attributes("src")).toBe("/assets/types/pure_flat.webp");
    expect(img.attributes("style")).toContain("8cqw");
  });
  it("is named for screen readers unless decorative", () => {
    expect(mount(TypeSymbol, { props: { typeId: "crimson" } }).find("img").attributes("alt")).toBe("Crimson type");
    expect(mount(TypeSymbol, { props: { typeId: "crimson", decorative: true } }).find("img").attributes("alt")).toBe("");
  });
  it("renders nothing for a type without a symbol", () => {
    expect(mount(TypeSymbol, { props: { typeId: "plasma" } }).find("img").exists()).toBe(false);
  });
});
