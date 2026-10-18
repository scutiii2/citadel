import { beforeEach, describe, expect, it } from "vitest";
import { DEFAULT_SHELL, pairCommand, readShell, writeShell } from "./forgeShells";

beforeEach(() => localStorage.clear());

describe("forgeShells", () => {
  it("writes the launcher the way each shell needs it", () => {
    expect(pairCommand("powershell", "http://127.0.0.1:8030", "ft_x", "claude")).toBe(
      ".\run.bat pair http://127.0.0.1:8030 ft_x --provider claude",
    );
    expect(pairCommand("cmd", "http://h", "ft_x", "codex")).toBe("run.bat pair http://h ft_x --provider codex");
    expect(pairCommand("gitbash", "http://h", "ft_x", "claude")).toBe("./run.bat pair http://h ft_x --provider claude");
  });

  it("remembers the choice and ignores damaged values", () => {
    expect(readShell()).toBe(DEFAULT_SHELL);
    writeShell("gitbash");
    expect(readShell()).toBe("gitbash");
    localStorage.setItem("ember_web.forgeShell", "zsh");
    expect(readShell()).toBe(DEFAULT_SHELL);
  });
});
