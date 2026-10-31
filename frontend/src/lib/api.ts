import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { CaseDetail, CaseSummary, EvidenceOut, Health, JobOut } from '@/types'

const BASE = '/api'

export class ApiError extends Error {
  status: number
  body: any
  constructor(status: number, message: string, body?: any) {
    super(message)
    this.status = status
    this.body = body
  }
}

/** Dev-only mock mode: localStorage 'verity-mock'=1 AND vite dev. Compiled out of production builds. */
function mockEnabled(): boolean {
  if (!import.meta.env.DEV) return false
  try { return localStorage.getItem('verity-mock') === '1' } catch { return false }
}
export const isMock = mockEnabled

async function request<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  if (import.meta.env.DEV && mockEnabled()) {
    const m = await import('./mock')
    return m.mockHandle(method, path, body, form) as T
  }
  const init: RequestInit = { method, headers: {} }
  if (form) init.body = form
  else if (body !== undefined) {
    ;(init.headers as Record<string, string>)['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  let res: Response
  try {
    res = await fetch(BASE + path, init)
  } catch (e) {
    throw new ApiError(0, 'Cannot reach the Verity API. Is the backend running on port 8000?', e)
  }
  const text = await res.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const detail = typeof data === 'object' && data ? (data.detail ?? data.message ?? JSON.stringify(data)) : String(data ?? res.statusText)
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail), data)
  }
  return data as T
}

export const api = {
  get: <T,>(path: string) => request<T>('GET', path),
  post: <T,>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  patch: <T,>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {}),
  upload: <T,>(path: string, file: File | Blob, filename?: string, extra?: Record<string, string>) => {
    const fd = new FormData()
    fd.append('file', file, filename ?? (file instanceof File ? file.name : 'upload.bin'))
    for (const [k, v] of Object.entries(extra ?? {})) fd.append(k, v)
    return request<T>('POST', path, undefined, fd)
  },
  fileUrl: (evidenceId: string) => `${BASE}/evidence/${evidenceId}/file`,
  reportUrl: (caseId: string, rev?: number) => `${BASE}/cases/${caseId}/report.pdf${rev != null ? `?rev=${rev}` : ''}`,
}

export const qk = {
  cases: ['cases'] as const,
  case: (id: string) => ['case', id] as const,
  health: ['health'] as const,
  passages: (eid: string) => ['passages', eid] as const,
  fixtures: ['demo-fixtures'] as const,
}

export function useCases() {
  return useQuery({ queryKey: qk.cases, queryFn: () => api.get<CaseSummary[]>('/cases'), refetchInterval: 4000 })
}

export function jobsActive(d?: CaseDetail): boolean {
  return !!d?.jobs?.some((j) => j.status === 'queued' || j.status === 'running')
}

/** Polls every 1.5 s while any job is queued/running, else every 8 s. */
export function useCaseDetail(id: string | undefined) {
  return useQuery({
    queryKey: qk.case(id ?? ''),
    enabled: !!id,
    queryFn: () => api.get<CaseDetail>(`/cases/${id}`),
    refetchInterval: (q) => (jobsActive(q.state.data) ? 1500 : 8000),
  })
}

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: () => api.get<Health>('/health'), refetchInterval: 20000, retry: 0 })
}

export function usePassages(evidenceId: string | undefined) {
  return useQuery({
    queryKey: qk.passages(evidenceId ?? ''),
    enabled: !!evidenceId,
    queryFn: () => api.get<{ page: number; text: string }[]>(`/evidence/${evidenceId}/passages`),
  })
}

export function useCreateCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (title: string) => api.post<CaseSummary>('/cases', { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.cases }),
  })
}

export function useUploadEvidence(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, filename }: { file: File | Blob; filename?: string }) =>
      api.upload<{ evidence: EvidenceOut; job: JobOut }>(`/cases/${caseId}/evidence`, file, filename),
    onSettled: () => qc.invalidateQueries({ queryKey: qk.case(caseId) }),
  })
}

export function useInvalidateCase(caseId: string) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: qk.case(caseId) })
    qc.invalidateQueries({ queryKey: qk.cases })
  }
}
