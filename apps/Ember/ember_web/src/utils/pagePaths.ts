import type { NavPrefs } from '../api/NavPreferencesClient'

/** Keep saved sidebar choices attached to pages whose public URL changed. */
export function canonicalPagePath(path: string): string {
  return path === '/capabilities/video_downloader' ? '/capabilities/media_downloader' : path
}

export function canonicalNavPrefs(prefs: NavPrefs): NavPrefs {
  const paths = (values: string[]) => [...new Set(values.map(canonicalPagePath))]
  return { order: paths(prefs.order), pinned: paths(prefs.pinned), hidden: paths(prefs.hidden) }
}
