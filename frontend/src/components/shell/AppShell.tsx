import { NavLink, Link, Outlet } from 'react-router-dom'
import { FlaskConical, FolderSearch } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ThemeToggle } from './ThemeToggle'
import { HealthChip, AiBanner } from './HealthChip'
import { isMock } from '@/lib/api'
import { VerityLogo } from '@/components/fx/VerityLogo'

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2 rounded-md" aria-label="Verity home">
      <VerityLogo size={28} speed={0.2} />
      <span className="text-[0.95rem] font-semibold tracking-tight">Verity</span>
      <span className="label-caps hidden sm:inline">Claims investigator</span>
    </Link>
  )
}

const navCls = ({ isActive }: { isActive: boolean }) =>
  cn('flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium', isActive ? 'bg-surface-2 text-ink' : 'text-ink-3 hover:text-ink')

export function AppShell() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 flex h-12 items-center gap-2 overflow-hidden sm:gap-3 border-b border-line bg-bg/92 px-4 backdrop-blur" style={{ background: 'color-mix(in srgb, var(--bg) 92%, transparent)' }}>
        <Logo />
        <nav className="ml-1 flex sm:ml-3 items-center gap-1" aria-label="Main">
          <NavLink to="/" end aria-label="Queue" className={navCls}><FolderSearch size={14} /> <span className="hidden sm:inline">Queue</span></NavLink>
          <NavLink to="/lab" aria-label="Proof Lab" className={navCls}><FlaskConical size={14} /> <span className="hidden sm:inline">Proof Lab</span></NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          {isMock() && <span className="tag hidden rounded border border-dashed border-inferred px-1.5 py-0.5 text-inferred sm:inline">DEV MOCK DATA</span>}
          <HealthChip />
          <ThemeToggle />
        </div>
      </header>
      <AiBanner />
      <main className="flex min-h-0 flex-1 flex-col"><Outlet /></main>
    </div>
  )
}
