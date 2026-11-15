/** An ISO time from the server as a timestamp; one without a zone is naive UTC (ember_api). */
export function parseServerTime(value: string | undefined): number {
  if (!value) return NaN;
  return Date.parse(/(Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
}

/** A server time in the viewer's local date and time; takes zoned and naive-UTC strings. */
export function formatUtc(iso: string): string {
  return new Date(parseServerTime(iso)).toLocaleString();
}

/** A server time as a short local date, e.g. "Nov 1, 2026". */
export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
