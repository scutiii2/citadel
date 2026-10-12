import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { Profile } from "../src/api/AscensionClient.ts";
import { CATALOG, ENCOUNTER, PROFILE, ownedAscended, shopWindow } from "../src/api/AscensionClient.fixtures.ts";

export class FakeGameApi {
  readonly ascension = { profile: null as Record<string, unknown> | null, keys: [] as string[] };
  readonly unexpected: string[] = [];
  private readonly page: Page;
  constructor(page: Page) { this.page = page; }
  async install(): Promise<void> {
    await this.page.route("**/ascended/*/sprite_*.webp", route => {
      const match = /^\/ascended\/([a-z0-9_-]+)\/(sprite_(?:main_card|preview_card|battle)\.webp)$/.exec(new URL(route.request().url()).pathname);
      if (!match) return route.fallback();
      try {
        const body = readFileSync(new URL(`../../ascended/${match[1]}/${match[2]}`, import.meta.url));
        return route.fulfill({ contentType: "image/webp", body });
      } catch {
        return route.fulfill({ status: 404 });
      }
    });
    await this.page.route("**/session/redeem", route => route.fulfill({ status: 200, json: { token: "e2e-session", expires_in: 28800 } }));
    await this.page.route("**/ascension/**", async route => {
      const req = route.request(); const path = new URL(req.url()).pathname; const method = req.method();
      if (!path.startsWith("/ascension/")) return route.fallback();
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
        this.ascension.profile = { ...PROFILE, squad: [starter_ascended_id], ascendeds: [ownedAscended(starter_ascended_id, { in_squad: true })] };
        return route.fulfill({ status: 201, json: this.ascension.profile });
      }
      const profile = this.ascension.profile as unknown as Profile | null;
      if (path === "/ascension/squad" && (method === "GET" || method === "PUT")) {
        if (!profile) return route.fulfill({ status: 404, json: { error: "Choose a starter first" } });
        if (method === "PUT") {
          const { ascended_ids: ids } = req.postDataJSON() as { ascended_ids: string[] };
          if (!Array.isArray(ids) || ids.length < 1 || ids.length > profile.squad_size || new Set(ids).size !== ids.length)
            return route.fulfill({ status: 400, json: { error: `Choose 1 to ${profile.squad_size} different Ascended` } });
          if (ids.some(id => !profile.ascendeds.some(member => member.ascended_id === id)))
            return route.fulfill({ status: 404, json: { error: "you do not own that Ascended" } });
          if (profile.active_battle) return route.fulfill({ status: 409, json: { error: "Finish your battle first." } });
          this.ascension.keys.push(req.headers()["idempotency-key"] ?? "");
          profile.squad = [...ids];
          profile.ascendeds = profile.ascendeds.map(member => ({ ...member, in_squad: ids.includes(member.ascended_id) }));
        }
        return route.fulfill({ json: { ascended_ids: profile.squad, size: profile.squad_size } });
      }
      if (method === "POST" && path === "/ascension/encounters" && profile) {
        profile.pending_encounter = ENCOUNTER.id;
        return route.fulfill({ status: 201, json: ENCOUNTER });
      }
      if (method === "GET" && path === `/ascension/encounters/${ENCOUNTER.id}`)
        return route.fulfill({ json: ENCOUNTER });
      if (method === "POST" && path === `/ascension/encounters/${ENCOUNTER.id}/decline` && profile) {
        profile.pending_encounter = null;
        return route.fulfill({ json: { ...ENCOUNTER, status: "declined" } });
      }
      if (method === "POST" && path === "/ascension/shop/purchases" && profile) {
        const purchase = req.postDataJSON() as { kind: string; slot: number; rotation: number; tier: string; quantity: number };
        if (purchase.kind === "copies") {
          const window = shopWindow();
          const offer = window.offers.find(item => item.slot === purchase.slot);
          if (!offer) return route.fulfill({ status: 404, json: { error: "No such offer" } });
          let member = profile.ascendeds.find(item => item.ascended_id === offer.ascended_id);
          if (!member) {
            const inSquad = profile.squad.length < profile.squad_size;
            member = ownedAscended(offer.ascended_id, { in_squad: inSquad, copies: offer.copies_granted, tier_id: offer.tier_id });
            profile.ascendeds.push(member);
            if (inSquad) profile.squad.push(offer.ascended_id);
          } else member.copies += offer.copies_granted;
          profile.insignia -= offer.price;
          return route.fulfill({ json: { kind: "copies", ascended_id: offer.ascended_id, tier_id: offer.tier_id, copies_granted: offer.copies_granted, price: offer.price, slot: offer.slot, rotation: window.rotation, left: offer.left - 1 } });
        }
      }
      this.unexpected.push(`${method} ${path}`);
      return route.fulfill({ status: 500, json: { error: "Unexpected test request" } });
    });
  }
}
export async function installFakeApi(page: Page): Promise<FakeGameApi> {
  const api = new FakeGameApi(page); await api.install(); return api;
}
