import { ADMIN_SECTIONS, CONFIG_ISSUES_ICON } from "../router/pages";

export const pages = [
  ...ADMIN_SECTIONS,
  { to: "/config-issues", label: "Config issues", icon: CONFIG_ISSUES_ICON },
];

export type Section = "accounts" | "roles" | "invites" | "issues";
export type PreviewRecord = {
  id: string;
  name: string;
  subtitle: string;
  status: string;
  note: string;
  tone: "positive" | "neutral" | "warning" | "danger";
  protected?: boolean;
} & ({ roleIds: string[]; group?: never } | { group: string; roleIds?: never });

export const panels = {
  accounts: { heading: "Account roster", name: "Account", group: "Roles", count: "accounts", search: "Search accounts" },
  roles: { heading: "Workspace roles", name: "Role", group: "Permissions", count: "roles", search: "Search roles" },
  invites: { heading: "Open invites", name: "Invite", group: "Role", count: "invites", search: "Search invites" },
  issues: { heading: "Configuration checks", name: "Check", group: "Scope", count: "checks", search: "Search config issues" },
};

export const sectionsByPath: Partial<Record<string, Section>> = {
  "/admin/accounts": "accounts",
  "/admin/roles": "roles",
  "/admin/invites": "invites",
  "/config-issues": "issues",
};

export const samples: Record<Section, PreviewRecord[]> = {
  accounts: [
    { id: "admin", name: "admin", subtitle: "admin@example.invalid", roleIds: ["administrator"], status: "Active", note: "Protected account with full workspace access.", tone: "positive", protected: true },
    { id: "maya", name: "Maya Chen", subtitle: "maya.chen@example.invalid", roleIds: ["operator", "member"], status: "Active", note: "Manages operational access.", tone: "positive" },
    { id: "eli", name: "Eli Navarro", subtitle: "eli.navarro@example.invalid", roleIds: ["member"], status: "Active", note: "", tone: "positive" },
    { id: "nia", name: "Nia Brooks", subtitle: "nia.brooks@example.invalid", roleIds: [], status: "Active", note: "", tone: "positive" },
    { id: "sam", name: "Sam Rivera", subtitle: "sam.rivera@example.invalid", roleIds: ["member"], status: "Disabled", note: "", tone: "neutral" },
  ],
  roles: [
    { id: "administrator", name: "Administrator", subtitle: "Built-in role", group: "All permissions", status: "Protected", note: "Full access to workspace administration.", tone: "neutral", protected: true },
    { id: "operator", name: "Operator", subtitle: "Custom role", group: "4 permissions", status: "Custom", note: "View accounts and roles, manage invites, and view configuration issues.", tone: "positive" },
    { id: "member", name: "Member", subtitle: "Custom role", group: "1 permission", status: "Custom", note: "View workspace accounts.", tone: "positive" },
  ],
  invites: [
    { id: "taylor", name: "taylor@example.invalid", subtitle: "Invited by admin", group: "Member", status: "Pending", note: "Awaiting acceptance.", tone: "warning" },
    { id: "jules", name: "jules@example.invalid", subtitle: "Invited by admin", group: "Operator", status: "Pending", note: "Awaiting acceptance.", tone: "warning" },
  ],
  issues: [
    { id: "email", name: "Invite email delivery", subtitle: "Portcullis", group: "Invites", status: "Warning", note: "Mail delivery is unavailable in this sample. An administrator can share the invite link directly.", tone: "warning" },
    { id: "registration", name: "Public registration disabled", subtitle: "Portcullis", group: "Accounts", status: "Info", note: "New members join using a workspace invitation.", tone: "neutral" },
  ],
};
