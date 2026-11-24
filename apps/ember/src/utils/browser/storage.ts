/** Per-browser conveniences (a theme, a folded sidebar): blocked or full storage just means the default,
 * so a failed read gives null and a failed write is ignored. */
export function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore - see readStored
  }
}
