const MB = 1024 * 1024

/** m:ss, or h:mm:ss from one hour up. Empty when unknown. */
export function formatMediaLength(seconds: number | null): string {
  if (seconds === null) return ''
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number): string => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export function formatSpeed(bytesPerSecond: number | null): string {
  return bytesPerSecond === null ? '' : `${(bytesPerSecond / MB).toFixed(1)} MB/s`
}

export function formatEta(seconds: number | null): string {
  if (seconds === null) return ''
  const total = Math.round(seconds)
  if (total < 60) return `${total} s`
  if (total < 3600) return `${Math.floor(total / 60)} min ${total % 60} s`
  const minutes = Math.round(total / 60)
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

/** Time left until a unix-seconds expiry, e.g. "5 h 12 min". Both arguments are unix seconds. */
export function formatExpiry(expiresAt: number, now: number): string {
  const left = Math.floor(expiresAt - now)
  if (left <= 0) return 'expired'
  const hours = Math.floor(left / 3600)
  const minutes = Math.floor((left % 3600) / 60)
  return hours > 0 ? `${hours} h ${minutes} min` : `${Math.max(1, minutes)} min`
}
