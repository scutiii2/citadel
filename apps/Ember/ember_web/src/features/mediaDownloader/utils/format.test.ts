import { describe, expect, it } from 'vitest'
import { formatDuration, formatEta, formatExpiry, formatSpeed } from './format'

describe('format', () => {
  it('formats durations', () => {
    expect(formatDuration(null)).toBe('')
    expect(formatDuration(65)).toBe('1:05')
    expect(formatDuration(3725)).toBe('1:02:05')
  })

  it('formats speed and eta', () => {
    expect(formatSpeed(null)).toBe('')
    expect(formatSpeed(1_500_000)).toBe('1.4 MB/s')
    expect(formatEta(null)).toBe('')
    expect(formatEta(12)).toBe('12 s')
    expect(formatEta(75)).toBe('1 min 15 s')
    expect(formatEta(3700)).toBe('1 h 2 min')
  })

  it('formats time left until expiry', () => {
    expect(formatExpiry(1000, 1000)).toBe('expired')
    expect(formatExpiry(1000 + 90, 1000)).toBe('1 min')
    expect(formatExpiry(1000 + 5 * 3600 + 12 * 60, 1000)).toBe('5 h 12 min')
  })

})
