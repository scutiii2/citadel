/// <reference types="node" />
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const source = dirname(fileURLToPath(import.meta.url));
const themes = [resolve(source, "style.css"), resolve(source, "../../ember_admin/src/style.css")];

function luminance(hex: string): number {
  const rgb = hex.match(/[a-f\d]{2}/gi)!.map((channel) => {
    const value = parseInt(channel, 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * rgb[0]! + 0.7152 * rgb[1]! + 0.0722 * rgb[2]!;
}

function contrast(a: string, b: string): number {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0]! + 0.05) / (values[1]! + 0.05);
}

function tint(accent: string, surface: string, amount: number): string {
  const channels = (hex: string) => hex.match(/[a-f\d]{2}/gi)!.map(value => parseInt(value, 16));
  const background = channels(surface);
  return "#" + channels(accent).map((value, index) =>
    Math.round(value * amount + background[index]! * (1 - amount)).toString(16).padStart(2, "0"),
  ).join("");
}

function pair(css: string, token: string): string[] {
  const declaration = css.match(new RegExp(`--${token}:\\s*light-dark\\((#[a-f\\d]{6}),\\s*(#[a-f\\d]{6})\\)`, "i"));
  if (!declaration) throw new Error(`Missing themed token: ${token}`);
  return declaration.slice(1);
}

describe("ordinary accent text contrast", () => {
  for (const url of themes) {
    const css = readFileSync(url, "utf8");
    for (const [index, theme] of ["light", "dark"].entries()) {
      it(`${url.includes("ember_admin") ? "Admin" : "Web"} ${theme}: primary labels and links meet 4.5:1`, () => {
        const accent = pair(css, "accent")[index]!;
        expect(contrast(pair(css, "accent-contrast")[index]!, accent)).toBeGreaterThanOrEqual(4.5);
        for (const surface of ["bg", "surface"]) {
          expect(contrast(accent, pair(css, surface)[index]!)).toBeGreaterThanOrEqual(4.5);
          // Selected segmented labels and command badges sit on tinted surfaces.
          expect(contrast(accent, tint(accent, pair(css, surface)[index]!, 0.12))).toBeGreaterThanOrEqual(4.5);
        }
      });
    }
  }
});
