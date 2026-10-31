import { useOutletContext } from 'react-router-dom'
import type { CaseDetail } from '@/types'

/** Outlet context provided by CaseWorkspace to every case tab page. */
export interface CaseCtx { detail: CaseDetail }

export function useCaseCtx(): CaseCtx {
  return useOutletContext<CaseCtx>()
}
