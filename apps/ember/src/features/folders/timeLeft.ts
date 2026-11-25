/** How long until `expiresMs`, as "12 min left", "45 s left" or "expired". */
export function timeLeft(expiresMs: number, nowMs: number): string {
  const seconds = Math.ceil((expiresMs - nowMs) / 1000);
  if (seconds <= 0) return "expired";
  return seconds < 60 ? `${seconds} s left` : `${Math.ceil(seconds / 60)} min left`;
}
