/** Reading an event's free text safely: links, the Teams join link, and the boilerplate footer Outlook adds. */

export type TextPart = { text: string } | { href: string; label: string };

const WEB = ["https:", "http:"];
const URL_PATTERN = /https?:\/\/[^\s<>"']+/gi;
const FOOTER = /^\s*(?:Microsoft Teams(?: meeting)?\s*$|Join (?:the )?meeting(?: now)?\s*$|_{5,}|-{10,})/im;

/** An http(s) URL; an Outlook safelink is replaced by the address it protects. */
export function readableUrl(raw: string): URL | null {
  try {
    const url = new URL(raw);
    if (!WEB.includes(url.protocol)) return null;
    if (url.hostname.endsWith(".safelinks.protection.outlook.com")) {
      const target = url.searchParams.get("url");
      if (target) {
        const inner = new URL(target);
        if (WEB.includes(inner.protocol)) return inner;
      }
    }
    return url;
  } catch {
    return null;
  }
}

export function isTeamsMeeting(url: URL | null): boolean {
  return url !== null && url.hostname === "teams.microsoft.com" && /^\/(?:l\/meetup-join\/|meet\/)/i.test(url.pathname);
}

export function findTeamsLink(...texts: string[]): string | null {
  for (const match of texts.filter(Boolean).join(" ").matchAll(URL_PATTERN)) {
    const url = readableUrl(match[0]);
    if (isTeamsMeeting(url)) return url!.href;
  }
  return null;
}

export function splitDescription(text: string): { description: string; footer: string } {
  const value = (text || "").replace(/\r\n/g, "\n");
  const footer = FOOTER.exec(value);
  if (!footer) return { description: value.trim(), footer: "" };
  return {
    description: value.slice(0, footer.index).trim(),
    footer: value.slice(footer.index).replace(/^\s*[_-]{5,}\s*/g, "").trim(),
  };
}

/** Text as parts a template can render without v-html: plain text, or a safe link. */
export function linkify(text: string): TextPart[] {
  const value = text || "";
  const parts: TextPart[] = [];
  let offset = 0;
  for (const match of value.matchAll(URL_PATTERN)) {
    const url = readableUrl(match[0]);
    if (!url) continue;
    if (match.index! > offset) parts.push({ text: value.slice(offset, match.index) });
    parts.push({ href: url.href, label: isTeamsMeeting(url) ? "Join Teams meeting" : "Open link" });
    offset = match.index! + match[0].length;
  }
  if (offset < value.length) parts.push({ text: value.slice(offset) });
  return parts;
}
