import type { Page } from "@playwright/test";
import { CATALOG, PROFILE, ownedAscended, shopWindow } from "../src/api/AscensionClient.fixtures.ts";

export class FakeGameApi {
  readonly ascension = { profile: null as Record<string, unknown> | null, keys: [] as string[] };
  readonly unexpected: string[] = [];
  private readonly page: Page;
  constructor(page: Page) { this.page = page; }
  async install(): Promise<void> {
    await this.page.route("**/session/redeem", route => route.fulfill({ status: 200, json: { token: "e2e-session", expires_in: 28800 } }));
    await this.page.route("**/ascension/**", async route => {
      const req = route.request(); const path = new URL(req.url()).pathname; const method = req.method();
      if (req.headers().authorization !== "Bearer e2e-session") return route.fulfill({ status: 401, json: { error: "Not signed in" } });
      if (method === "GET" && path === "/ascension/catalog") return route.fulfill({ json: CATALOG });
      if (method === "GET" && path === "/ascension/shop") return route.fulfill({ json: shopWindow() });
      if (method === "POST" && path === "/ascension/profile/reset") {
        this.ascension.profile = null;
        return route.fulfill({ json: { reset: true } });
      }
      if (method === "GET" && path === "/ascension/profile") return route.fulfill({ status: this.ascension.profile ? 200 : 404, json: this.ascension.profile ?? { error: "Choose a starter first" } });
      if (method === "POST" && path === "/ascension/profile") {
        this.ascension.keys.push(req.headers()["idempotency-key"] ?? "");
        const { starter_ascended_id } = req.postDataJSON() as { starter_ascended_id: string };
        this.ascension.profile = { ...PROFILE, ascendeds: [ownedAscended(starter_ascended_id)] };
        return route.fulfill({ status: 201, json: this.ascension.profile });
      }
      this.unexpected.push(`${method} ${path}`);
      return route.fulfill({ status: 500, json: { error: "Unexpected test request" } });
    });
  }
}
export async function installFakeApi(page: Page): Promise<FakeGameApi> {
  const api = new FakeGameApi(page); await api.install(); return api;
}
