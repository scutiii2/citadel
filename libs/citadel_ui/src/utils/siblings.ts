/** The admin apps, each on its own port of the same host. The session cookie is host-wide, so a login in one
 * is a login in all. shortcut: ports are fixed (docker-compose publishes them); add a per-app URL setting
 * when an app is hosted elsewhere. */
export interface AdminApp {
  name: string;
  letter: string;
  port: number;
}

export const ADMIN_APPS: AdminApp[] = [
  { name: "Legion Admin", letter: "L", port: 26500 },
  { name: "Portcullis Admin", letter: "P", port: 26501 },
  { name: "Armory Admin", letter: "A", port: 26503 },
  { name: "Stronghold Admin", letter: "S", port: 26504 },
  { name: "Treasury Admin", letter: "T", port: 26505 },
];

export function adminAppUrl(port: number, current = window.location.href): string {
  const url = new URL(current);
  url.port = String(port);
  url.pathname = "/";
  url.search = url.hash = "";
  return url.href;
}
