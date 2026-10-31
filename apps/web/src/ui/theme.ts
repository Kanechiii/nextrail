export type ThemePreference = 'system' | 'light' | 'dark'
export const THEME_KEY = 'nextrail.theme'
export function isTheme(value: unknown): value is ThemePreference {
  return value === 'system' || value === 'light' || value === 'dark'
}
export function readTheme(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_KEY)
    return isTheme(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}
export function applyTheme(value: ThemePreference): void {
  const systemDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true
  const active = value === 'system' ? (systemDark ? 'dark' : 'light') : value
  document.documentElement.dataset.theme = active
  document.documentElement.style.colorScheme = active
  try { window.localStorage.setItem(THEME_KEY, value) } catch { /* Preferences remain in memory. */ }
}
