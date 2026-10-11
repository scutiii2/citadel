/** A deployment-controlled CSP origin list; URL syntax cannot inject directives. */
export class GameOrigins {
  private readonly origins: readonly string[];
  constructor(raw = "http://127.0.0.1:* http://localhost:*") {
    this.origins = raw.trim().split(/\s+/).filter(Boolean).map(value => {
      const wildcardPort = value.endsWith(":*");
      const candidate = wildcardPort ? value.slice(0, -1) + "1" : value;
      const url = new URL(candidate);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.hostname.includes("*") || url.search || url.hash || url.pathname !== "/" || candidate !== url.origin || /[;,]/.test(candidate)) throw new Error("EMBER_GAME_ORIGINS must contain HTTP(S) origins only");
      return wildcardPort ? value : url.origin;
    });
  }
  frameSource(): string { return this.origins.join(" ") || "'none'"; }
}
