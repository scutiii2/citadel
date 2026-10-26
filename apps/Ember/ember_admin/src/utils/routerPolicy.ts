import type { RouterPolicy } from "../api/AgentsAdminClient";

export function routerPolicyDefaults(value: Partial<RouterPolicy> = {}): RouterPolicy {
  return JSON.parse(JSON.stringify({
    choose_agent: true, choose_tier: true, strategy: "both", min_confidence: .9, trace: false,
    deadline_seconds: 10, remote_timeout_seconds: 3,
    size_tiers: { tiny: "light", everyday: "light", large: "standard", hardest: "heavy" }, ...value,
  }));
}

export function validateRouterPolicy(value: RouterPolicy): string {
  if (!Number.isFinite(value.deadline_seconds) || value.deadline_seconds < 1 || value.deadline_seconds > 30)
    return "The routing deadline must be from 1 to 30 seconds.";
  if (!Number.isFinite(value.remote_timeout_seconds) || value.remote_timeout_seconds <= 0 || value.remote_timeout_seconds > 30)
    return "The remote timeout must be above 0 and at most 30 seconds.";
  if (!["laya-only", "jev-only", "both"].includes(value.strategy)) return "Choose an available decision strategy.";
  if (!Number.isFinite(value.min_confidence) || value.min_confidence <= 0 || value.min_confidence > 1)
    return "Minimum confidence must be above 0 and at most 1.";
  if (Object.values(value.size_tiers).some(tier => !["light", "standard", "heavy", "extreme"].includes(tier)))
    return "Choose an available model tier for each request size.";
  return "";
}
