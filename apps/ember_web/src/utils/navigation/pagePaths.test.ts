import { expect, it } from 'vitest'
import { canonicalNavPrefs, canonicalPagePath } from './pagePaths'

it('preserves ordering, pinning and hiding for old downloader paths without duplicates', () => {
  const old = '/capabilities/video_downloader'
  const current = '/capabilities/media_downloader'
  expect(canonicalNavPrefs({ order: [old, '/', current], pinned: [old, current], hidden: [old] }))
    .toEqual({ order: [current, '/'], pinned: [current], hidden: [current] })
  expect(canonicalPagePath('/notes')).toBe('/notes')
})
