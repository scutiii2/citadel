import type { RouterPolicy } from "../api/AgentsAdminClient";

export function routerPolicyDefaults(value: Partial<RouterPolicy> = {}): RouterPolicy {
  return JSON.parse(JSON.stringify({
    choose_agent: true, choose_tier: true, english: true, typed: true, fallback: true, trace: false,
    thresholds: { "2": { "laya-english": .9, "laya-typed": .8, jev: .9 },
      "3+": { "laya-english": .75, "laya-typed": .55, jev: .9 } },
    prune_ratio: .25, pair_ratio: .5, deadline_seconds: 10, remote_timeout_seconds: 3,
    size_tiers: { tiny: "light", everyday: "light", large: "standard", hardest: "heavy" }, ...value,
  }));
}

export function validateRouterPolicy(value: RouterPolicy): string {
  if (!Number.isFinite(value.deadline_seconds) || value.deadline_seconds < 1 || value.deadline_seconds > 30)
    return "The routing deadline must be from 1 to 30 seconds.";
  if (!Number.isFinite(value.remote_timeout_seconds) || value.remote_timeout_seconds <= 0 || value.remote_timeout_seconds > 30)
    return "The remote timeout must be above 0 and at most 30 seconds.";
  if (!value.english && !value.typed && !value.fallback) return "Enable at least one local voter or Jev fallback.";
  if (Object.values(value.thresholds).some(row => Object.values(row).some(n => !Number.isFinite(n) || n < 0 || n > 1)))
    return "Each confidence threshold must be from 0 to 1.";
  if (!Number.isFinite(value.prune_ratio) || value.prune_ratio < 0 || value.prune_ratio >= 1
    || !Number.isFinite(value.pair_ratio) || value.pair_ratio <= 0 || value.pair_ratio > 1)
    return "Narrowing ratios must be in their displayed ranges.";
  if (Object.values(value.size_tiers).some(tier => !["light", "standard", "heavy", "extreme"].includes(tier)))
    return "Choose an available model tier for each request size.";
  return "";
}
