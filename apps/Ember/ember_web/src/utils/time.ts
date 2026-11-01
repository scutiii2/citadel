/** An ISO time from the server as a timestamp; one without a zone is naive UTC (ember_api). */
export function parseServerTime(value: string | undefined): number {
  if (!value) return NaN;
  return Date.parse(/(Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
}

/** A server time in the viewer's local date and time; takes zoned and naive-UTC strings. */
export function formatUtc(iso: string): string {
  return new Date(parseServerTime(iso)).toLocaleString();
}
