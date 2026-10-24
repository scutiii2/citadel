import { describe, expect, it } from "vitest";
import { findTeamsLink, isTeamsMeeting, linkify, readableUrl, splitDescription } from "./eventDetails";

describe("readableUrl", () => {
  it("accepts http(s) and unwraps Outlook safelinks", () => {
    expect(readableUrl("https://example.com/a")?.href).toBe("https://example.com/a");
    const safe = "https://eur01.safelinks.protection.outlook.com/?url=" + encodeURIComponent("https://example.com/b") + "&data=x";
    expect(readableUrl(safe)?.href).toBe("https://example.com/b");
  });
  it("refuses other schemes and junk", () => {
    expect(readableUrl("javascript:alert(1)")).toBeNull();
    expect(readableUrl("not a url")).toBeNull();
  });
});

describe("Teams links", () => {
  it("recognises meetup-join and meet links only on teams.microsoft.com", () => {
    expect(isTeamsMeeting(new URL("https://teams.microsoft.com/l/meetup-join/abc"))).toBe(true);
    expect(isTeamsMeeting(new URL("https://teams.microsoft.com/meet/123"))).toBe(true);
    expect(isTeamsMeeting(new URL("https://evil.example/teams.microsoft.com/l/meetup-join/abc"))).toBe(false);
    expect(isTeamsMeeting(null)).toBe(false);
  });
  it("finds the first meeting link across texts", () => {
    expect(findTeamsLink("see https://example.com", "join https://teams.microsoft.com/l/meetup-join/abc now")).toBe(
      "https://teams.microsoft.com/l/meetup-join/abc",
    );
    expect(findTeamsLink("nothing here")).toBeNull();
  });
});

describe("splitDescription", () => {
  it("moves the Teams footer out of the description", () => {
    const text = "Agenda\n\nMicrosoft Teams meeting\nJoin: https://teams.microsoft.com/l/meetup-join/x";
    expect(splitDescription(text)).toEqual({
      description: "Agenda",
      footer: "Microsoft Teams meeting\nJoin: https://teams.microsoft.com/l/meetup-join/x",
    });
  });
  it("keeps plain text whole", () => {
    expect(splitDescription("Just words")).toEqual({ description: "Just words", footer: "" });
  });
});

describe("linkify", () => {
  it("splits text into plain and link parts and labels Teams links", () => {
    expect(linkify("a https://teams.microsoft.com/l/meetup-join/x b")).toEqual([
      { text: "a " },
      { href: "https://teams.microsoft.com/l/meetup-join/x", label: "Join Teams meeting" },
      { text: " b" },
    ]);
  });
  it("never produces a link for a blocked scheme", () => {
    expect(linkify("go to ftp://x")).toEqual([{ text: "go to ftp://x" }]);
  });
});
