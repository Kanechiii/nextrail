import { useEffect, useState } from 'react'
import { Moon, Sun, Monitor } from 'lucide-react'
import { applyTheme, readTheme, type ThemePreference } from './theme'

const preferences: ThemePreference[] = ['system', 'light', 'dark']
const icons = { system: Monitor, light: Sun, dark: Moon }
export default function ThemeSwitch() {
  const [selected, setSelected] = useState<ThemePreference>(readTheme)
  useEffect(() => {
    applyTheme(selected)
    if (selected !== 'system') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => applyTheme('system')
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [selected])
  const Icon = icons[selected]
  const chooseNext = () => setSelected(current => preferences[(preferences.indexOf(current) + 1) % preferences.length])
  return <button type="button" className="theme-switch" onClick={chooseNext} aria-label={`Appearance: ${selected}. Change theme`} title={`Appearance: ${selected} (click to cycle)`}><Icon size={17} aria-hidden="true" /><span className="theme-switch-label">{selected}</span></button>
}
