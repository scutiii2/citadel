/** Override for hosted deployments; otherwise use the ember_web port on this host. */
export function emberWebUrl(current = window.location.href, configured = import.meta.env.VITE_EMBER_WEB_URL): string {
  if (configured) {
    try {
      const url = new URL(configured, current);
      if (["http:", "https:"].includes(url.protocol)) return url.href;
    } catch { /* Invalid deployment URL: use the default below. */ }
  }
  const url = new URL(current);
  url.port = "5173";
  url.pathname = "/overview";
  url.search = url.hash = "";
  return url.href;
}
