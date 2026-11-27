import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

function render(text: string): HTMLElement {
  const host = document.createElement("div");
  host.innerHTML = renderMarkdown(text);
  return host;
}

describe("renderMarkdown math", () => {
  it.each([
    "\\[\n\\boxed{\\lim_{x\\to0}\\frac{\\tan(\\sin x)}{x^7}=\\frac1{30}}\n\\]",
    "$$\na_1 * b_2 * |x|\n$$",
    "so \\[ a_{1} \\] holds",
  ])("typesets display math: %s", (source) => {
    const host = render(source);

    expect(host.querySelector(".math-block .katex-display")).not.toBeNull();
    expect(host.querySelector("em, table, .katex-error")).toBeNull();
    expect(host.querySelector("math semantics annotation")).not.toBeNull();
  });

  it("typesets inline math, in text and in a table", () => {
    const host = render("at \\(x_1\\) and *then*\n\n| \\(x\\) |\n| --- |\n| \\(0.1\\) |");

    expect(host.querySelectorAll(".katex")).toHaveLength(3);
    expect(host.querySelector(".katex-display")).toBeNull();
    expect(host.querySelector("em")?.textContent).toBe("then");
  });

  it.each(["costs $5 and $10", "`\\(x\\)`", "```\n\\[ x \\]\n```", "unfinished \\[ x + 1", "$$\nstill streaming"])(
    "leaves this as text: %s", (source) => {
      expect(render(source).querySelector(".katex")).toBeNull();
    });

  it("does not let a formula add links, images or oversized boxes", () => {
    const host = render("\\(\\href{javascript:alert(1)}{x}\\) \\(\\includegraphics{https://example.com/a.png}\\) \\(\\rule{900em}{900em}\\)");

    expect(host.querySelector("a, img")).toBeNull();
    expect(host.innerHTML).not.toContain("900em;");
  });

  it("shows a broken formula instead of failing the reply", () => {
    expect(render("before \\(\\frac{1}\\) after").textContent).toContain("after");
  });
});

describe("renderMarkdown code blocks", () => {
  it("wraps each fenced block with a Copy button that survives sanitizing", () => {
    const host = render("```js\nconst a = 1;\n```\n\ntext\n\n```\nsecond\n```");

    const blocks = host.querySelectorAll(".code-block");
    expect(blocks).toHaveLength(2);
    for (const block of blocks) {
      const button = block.querySelector("button.code-copy");
      expect(button?.textContent).toBe("Copy");
      expect(button?.getAttribute("type")).toBe("button");
      expect(block.querySelector("pre code")).not.toBeNull();
    }
    expect(blocks[0]!.querySelector("pre code")!.textContent).toBe("const a = 1;\n");
  });

  it("gives inline code and indented code no button of their own", () => {
    expect(render("use `x` here").querySelector("button")).toBeNull();
  });

  it("does not let a model reply smuggle in its own button or handler", () => {
    const host = render('<button class="code-copy" onclick="alert(1)">x</button> <img src=x onerror="alert(1)">');

    // Raw HTML is shown as text, never parsed into elements or attributes.
    expect(host.querySelector("button, img, [onclick], [onerror]")).toBeNull();
    expect(host.textContent).toContain('<button class="code-copy"');
  });

  it("opens links in a new tab without a back reference", () => {
    const link = render("[a](https://example.com)").querySelector("a")!;

    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });
});
