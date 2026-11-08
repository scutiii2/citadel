/** How wide one bucket of a time chart is. */
export type BucketSize = "hour" | "day";

/** 1,284 / 12.9K / 1.2M. */
export function formatCount(n: number): string {
  if (n < 10_000) return n.toLocaleString("en-US");
  const compact = (value: number, unit: string) => `${value.toFixed(1).replace(/\.0$/, "")}${unit}`;
  return n < 1_000_000 ? compact(n / 1000, "K") : compact(n / 1_000_000, "M");
}

const NICE_STEPS = [1, 2, 4, 6, 8, 10];

/** The axis top for a count: a clean number whose half is whole too (2, 4, 10, 60, 200 ...). */
export function niceCeil(max: number): number {
  if (max <= 2) return 2;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  return NICE_STEPS.map((step) => step * magnitude).find((value) => value >= max)!;
}

const utcDate = (bucket: string) => new Date(`${bucket}Z`);
const SHORT_DATE: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", timeZone: "UTC" };

/** A bucket's tick on the time axis (UTC, like the buckets themselves). */
export function axisLabel(bucket: string, size: BucketSize): string {
  return size === "hour" ? bucket.slice(11, 16) : utcDate(bucket).toLocaleDateString("en-US", SHORT_DATE);
}

/** A bucket named in full, for the tooltip and the table. */
export function bucketTitle(bucket: string, size: BucketSize): string {
  const day = utcDate(bucket).toLocaleDateString("en-US", { ...SHORT_DATE, weekday: "short" });
  return size === "hour" ? `${day}, ${bucket.slice(11, 16)} UTC` : day;
}
