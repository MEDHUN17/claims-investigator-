import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { AppShell } from '@/components/shell/AppShell'
import { CaseWorkspace } from '@/components/shell/CaseWorkspace'
import Queue from '@/pages/Queue'
import Evidence from '@/pages/Evidence'
import Review from '@/pages/Review'

// FRONT-B pages (default exports), loaded lazily.
const Investigation = lazy(() => import('@/pages/Investigation'))
const Delta = lazy(() => import('@/pages/Delta'))
const Lab = lazy(() => import('@/pages/Lab'))

function Loading() {
  return <div className="flex items-center gap-2 p-8 text-sm text-ink-3"><Loader2 size={16} className="animate-spin" /> Loading…</div>
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Queue />} />
          <Route path="case/:id" element={<CaseWorkspace />}>
            <Route index element={<Navigate to="evidence" replace />} />
            <Route path="evidence" element={<Evidence />} />
            <Route path="evidence/:evidenceId" element={<Evidence />} />
            <Route path="investigation" element={<Investigation />} />
            <Route path="changes" element={<Delta />} />
            <Route path="review" element={<Review />} />
          </Route>
          <Route path="lab" element={<Lab />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
