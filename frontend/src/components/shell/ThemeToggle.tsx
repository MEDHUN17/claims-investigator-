import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

type Theme = 'dark' | 'light'

function readTheme(): Theme {
  try { return localStorage.getItem('verity-theme') === 'light' ? 'light' : 'dark' } catch { return 'dark' }
}

export function applyStoredTheme() {
  document.documentElement.dataset.theme = readTheme()
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('verity-theme', theme) } catch { /* ignore */ }
  }, [theme])
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} (paper) theme`}
      title={theme === 'dark' ? 'Paper theme (better on projectors)' : 'Graphite theme'}
      className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-md border border-line bg-surface-2 text-ink-2 hover:text-ink"
    >
      {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
    </button>
  )
}
