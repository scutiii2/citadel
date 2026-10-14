import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { ActivityDefinitions, ExpeditionView, BattleView, Catalog, Profile } from "../src/api/AscensionClient.ts";
import { CATALOG, ENCOUNTER, PROFILE, battleView, fighter, ownedAscended, shopWindow } from "../src/api/AscensionClient.fixtures.ts";

const rawActivities = JSON.parse(readFileSync(new URL('../../configs/ascension_catalog.json', import.meta.url), 'utf8')).activities;
const activityDefinitions: ActivityDefinitions = { ...rawActivities, trial_types: ['pure','abyss','divine','crimson','enchant','synthetic'], max_hunt_penalty:.75, trial_first_clear_multiplier:2 };

export class FakeGameApi {
  readonly ascension = { profile: null as Record<string, unknown> | null, keys: [] as string[] };
  readonly unexpected: string[] = [];
  readonly trades: { kind: string; quantity?: number }[] = [];
  readonly artRequests: string[] = [];
  battle: BattleView | null = null;
  catalog: Catalog = { ...structuredClone(CATALOG), activities: structuredClone(activityDefinitions) };
  expedition: ExpeditionView | null = null;
  encounter = { ...ENCOUNTER };
  shop = shopWindow();
  private readonly page: Page;
  constructor(page: Page) { this.page = page; }
  async install(): Promise<void> {
    await this.page.route("**/ascended/*/sprite_*.webp", route => {
      this.artRequests.push(new URL(route.request().url()).pathname);
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
      if (method === "GET" && path === "/ascension/catalog") return route.fulfill({ json: this.catalog });
      if (method === "GET" && path === "/ascension/shop") return route.fulfill({ json: this.shop });
      if (method === "POST" && path === "/ascension/profile/reset") {
        this.ascension.profile = null;
        return route.fulfill({ json: { reset: true } });
      }
      if (method === "GET" && path === "/ascension/profile") {
        if (this.ascension.profile) {
          const saved = this.ascension.profile as unknown as Profile;
          saved.server_now = Date.now()/1000; saved.expedition = this.expedition;
          saved.ascendeds = saved.ascendeds.map(member => ({ ...member, sale_value: member.sale_value ?? 25 }));
        }
        return route.fulfill({ status: this.ascension.profile ? 200 : 404, json: this.ascension.profile ?? { error: "Choose a starter first" } });
      }
      if (method === "POST" && path === "/ascension/profile") {
        this.ascension.keys.push(req.headers()["idempotency-key"] ?? "");
        const { starter_ascended_id } = req.postDataJSON() as { starter_ascended_id: string };
        this.ascension.profile = { ...PROFILE, squad: [starter_ascended_id], ascendeds: [ownedAscended(starter_ascended_id, { in_squad: true })] };
        return route.fulfill({ status: 201, json: this.ascension.profile });
      }
      const profile = this.ascension.profile as unknown as Profile | null;
      if (method === 'GET' && path === '/ascension/activities') return route.fulfill({ json: activityDefinitions });
      if (method === 'GET' && path.startsWith('/ascension/activities/hunts/') && profile) {
        const difficulty = path.split('/')[4]; const hunt = activityDefinitions.hunts.find(h => h.id === difficulty)!;
        const id = new URL(req.url()).searchParams.get('ascended_id'); const owned = profile.ascendeds.find(a => a.ascended_id === id)!;
        const overall = owned.overall ?? 185; const multiplier = 1-Math.min(.75, Math.max(0,(overall-hunt.recommended_max)/hunt.recommended_max));
        return route.fulfill({ json: { overall, recommended_min:hunt.recommended_min, recommended_max:hunt.recommended_max, reward_multiplier:multiplier, penalty_percent:Math.round((1-multiplier)*100), below_range:overall<hunt.recommended_min } });
      }
      if (method === 'GET' && path === '/ascension/trials') return route.fulfill({ json:{trials:activityDefinitions.trial_types.map(type_id => ({type_id, stages:activityDefinitions.trial_stages.map(s => ({...s, cleared:false, unlocked:s.stage===1, first_clear:true}))}))} });
      const trial = /^\/ascension\/trials\/(\w+)\/stages\/(\d+)\/(prepare|battles)$/.exec(path);
      if (trial && profile) {
        const type_id=trial[1]!; const stage=Number(trial[2]); const spec=activityDefinitions.trial_stages[stage-1]!;
        const eligible = profile.ascendeds.filter(a => profile.squad.includes(a.ascended_id) && a.ascension_types.includes(type_id) && !a.fainted && !a.on_expedition).map(a => a.ascended_id);
        if (method==='GET') return route.fulfill({json:{type_id,stage,unlocked:stage===1,first_clear:true,eligible_ascended_ids:eligible,reason:eligible.length?null:'No eligible Ascended',opponent:{...spec,name:spec.ascended_id.charAt(0).toUpperCase()+spec.ascended_id.slice(1),overall:222}}});
        const input=req.postDataJSON(); this.battle=battleView({mode:input.mode,player:fighter(input.ascended_id),wild:fighter(spec.ascended_id),activity:{kind:'trial',difficulty_id:null,trial_type:type_id,trial_stage:stage,overall:null,reward_multiplier:1,recommended_min:null,recommended_max:null}});
        this.battle.actions=this.battle.actions.filter(a=>a.kind!=='catch'); profile.active_battle=this.battle.id;
        return route.fulfill({status:201,json:this.battle});
      }
      if (path === '/ascension/expeditions' && profile) {
        if (method==='POST') {
          const input=req.postDataJSON(); const now=Date.now()/1000;
          this.expedition={id:'expedition-1',ascended_id:input.ascended_id,started_at:now,ends_at:now+input.duration_hours*3600,duration_hours:input.duration_hours,xp_reward:input.duration_hours*100,insignia_reward:input.duration_hours*25,state:'on_expedition',can_claim:false,seconds_remaining:input.duration_hours*3600};
          profile.squad=profile.squad.filter(id=>id!==input.ascended_id); profile.ascendeds=profile.ascendeds.map(a=>a.ascended_id===input.ascended_id?{...a,in_squad:false,on_expedition:true,can_star_up:false,can_tier_up:false}:a);
        }
        if (this.expedition) { this.expedition.can_claim=this.expedition.ends_at<=Date.now()/1000; this.expedition.state=this.expedition.can_claim?'ready_to_claim':'on_expedition'; }
        return route.fulfill({status:method==='POST'?201:200,json:{server_now:Date.now()/1000,expedition:this.expedition}});
      }
      if (method==='POST' && path.endsWith('/claim') && path.startsWith('/ascension/expeditions/') && profile && this.expedition) {
        const expedition=this.expedition;
        if (expedition.ends_at>Date.now()/1000) return route.fulfill({status:409,json:{error:'The expedition has not finished yet'}});
        profile.insignia+=expedition.insignia_reward; profile.ascendeds=profile.ascendeds.map(a=>a.ascended_id===expedition.ascended_id?{...a,on_expedition:false,xp:a.xp+expedition.xp_reward}:a); this.expedition=null;
        return route.fulfill({json:{id:expedition.id,ascended_id:expedition.ascended_id,xp:expedition.xp_reward,insignia:expedition.insignia_reward,level_before:3,level_after:3,claimed_at:Date.now()/1000}});
      }
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
        const input = req.postDataJSON() ?? {};
        this.encounter = { ...this.encounter, activity:{kind:input.difficulty_id?"hunt":"legacy",difficulty_id:input.difficulty_id??null,trial_type:null,trial_stage:null,overall:null,reward_multiplier:1,recommended_min:null,recommended_max:null},overall:185 };
        profile.pending_encounter = this.encounter.id;
        return route.fulfill({ status: 201, json: this.encounter });
      }
      if (method === "GET" && path === `/ascension/encounters/${this.encounter.id}`)
        return route.fulfill({ json: this.encounter });
      if (method === "POST" && path === `/ascension/encounters/${this.encounter.id}/decline` && profile) {
        profile.pending_encounter = null;
        return route.fulfill({ json: { ...this.encounter, status: "declined" } });
      }
      if (method === "POST" && path === "/ascension/battles" && profile) {
        const input = req.postDataJSON() as { ascended_id: string; mode: "manual" | "autonomous"; emblem_limit: string | null };
        this.battle = battleView({ round: 3, revision: 3, history: [
          { round: 1, actions: { player: ["attack", "ATTACK"], wild: ["attack", "ATTACK"] }, events: [{ type: "attack", side: "player", damage: 10, protected: false, target_hp: 90 }, { type: "attack", side: "wild", damage: 10, protected: false, target_hp: 90 }] },
          { round: 2, actions: { player: ["ability:guardian_strike", "ATTACK"], wild: ["attack", "ATTACK"] }, events: [{ type: "attack", side: "player", damage: 10, protected: false, target_hp: 80 }, { type: "attack", side: "wild", damage: 10, protected: false, target_hp: 80 }] },
        ], mode: input.mode, emblem_limit: input.emblem_limit, activity:this.encounter.activity,
        player: fighter(input.ascended_id, { passives: [{ kind: 'defense_rating_bonus', params: { power_fraction: 0.4 } }] }),
        wild: fighter(this.encounter.ascended_id, { name: this.encounter.name, tier_id: this.encounter.tier_id, level: this.encounter.level,
          passives: [{ kind: 'low_hp_attack_bonus', params: { hp_below: 0.5, power_fraction: 0.2 } }] }) });
        profile.active_battle = this.battle.id;
        profile.pending_encounter = null;
        return route.fulfill({ status: 201, json: this.battle });
      }
      if (method === "GET" && path === "/ascension/battles/b1" && this.battle) return route.fulfill({ json: this.battle });
      if (method === "POST" && path === "/ascension/battles/b1/forfeit" && profile && this.battle) {
        this.battle = { ...this.battle, status: "terminal", phase: "terminal", result: { kind: "forfeited" } };
        profile.active_battle = null;
        return route.fulfill({ json: this.battle });
      }
      if (method === "GET" && /^\/ascension\/ascendeds\/[a-z0-9_-]+\/personalities$/.test(path)) return route.fulfill({ json: { items: [], next_cursor: null } });
      const tree = /^\/ascension\/ascendeds\/([a-z0-9_-]+)\/tree$/.exec(path);
      if (method === "GET" && tree) return route.fulfill({ json: { ascended_id: tree[1], level: 3, essences: {}, slots: [], loadout: {}, nodes: [] } });
      const preset = /^\/ascension\/ascendeds\/([a-z0-9_-]+)\/presets\/(\d+)$/.exec(path);
      if (method === "GET" && preset) return route.fulfill({ json: { ascended_id: preset[1], slot: Number(preset[2]), instance_ids: [] } });
      const sale = /^\/ascension\/ascendeds\/([a-z0-9_-]+)\/sales$/.exec(path);
      if (method === "POST" && sale && profile) {
        const member = profile.ascendeds.find(item => item.ascended_id === sale[1]);
        if (!member || member.copies < 1) return route.fulfill({ status: 400, json: { error: "No spare copies" } });
        const value = member.sale_value ?? 25;
        member.copies -= 1;
        profile.insignia += value;
        this.trades.push({ kind: "sale" });
        return route.fulfill({ json: { kind: "sale", ascended_id: member.ascended_id, tier_id: member.tier_id, copies: member.copies, value } });
      }
      if (method === "POST" && path === "/ascension/shop/purchases" && profile) {
        const purchase = req.postDataJSON() as { kind: string; slot: number; rotation: number; tier: string; quantity: number };
        if (purchase.kind === "copies") {
          const window = this.shop;
          const offer = window.offers.find(item => item.slot === purchase.slot);
          if (!offer) return route.fulfill({ status: 404, json: { error: "No such offer" } });
          if (purchase.rotation !== window.rotation || offer.left < 1 || profile.insignia < offer.price) return route.fulfill({ status: 409, json: { error: "Offer unavailable" } });
          offer.left -= 1;
          this.trades.push({ kind: "copies" });
          let member = profile.ascendeds.find(item => item.ascended_id === offer.ascended_id);
          if (!member) {
            const inSquad = profile.squad.length < profile.squad_size;
            member = ownedAscended(offer.ascended_id, { in_squad: inSquad, copies: offer.copies_granted, tier_id: offer.tier_id });
            profile.ascendeds.push(member);
            if (inSquad) profile.squad.push(offer.ascended_id);
          } else member.copies += offer.copies_granted;
          profile.insignia -= offer.price;
          return route.fulfill({ json: { kind: "copies", ascended_id: offer.ascended_id, tier_id: offer.tier_id, copies_granted: offer.copies_granted, price: offer.price, slot: offer.slot, rotation: window.rotation, left: offer.left } });
        }
      }
      if (method === "POST" && path === "/ascension/shop/purchases" && profile) {
        const purchase = req.postDataJSON() as { kind: string; tier: string; quantity: number };
        if (purchase.kind === "emblem") {
          const tier = this.catalog.tiers.find(t => t.id === purchase.tier);
          if (!tier || purchase.quantity < 1 || profile.insignia < tier.emblem_price * purchase.quantity) return route.fulfill({ status: 400, json: { error: "Cannot afford EMBLEMs" } });
          const price = tier.emblem_price * purchase.quantity;
          profile.emblems[purchase.tier] = (profile.emblems[purchase.tier] ?? 0) + purchase.quantity;
          profile.insignia -= price;
          this.trades.push({ kind: "emblems", quantity: purchase.quantity });
          return route.fulfill({ json: { kind: "emblems", tier_id: purchase.tier, quantity: purchase.quantity, price } });
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
