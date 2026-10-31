import { Cpu, CloudOff, TriangleAlert } from 'lucide-react'
import { useHealth } from '@/lib/api'
import { Chip } from '@/components/ui/Chip'
import { Tooltip } from '@/components/ui/Tooltip'

export type AiState = 'ok' | 'degraded' | 'unconfigured' | 'unreachable' | 'loading'

export function useAiState(): { state: AiState; message: string; model?: string } {
  const { data, isError, isLoading } = useHealth()
  if (isLoading) return { state: 'loading', message: 'Checking AI provider…' }
  if (isError || !data) return { state: 'unreachable', message: 'Cannot reach the Verity API.' }
  const ai = data.ai
  if (!ai.configured) return { state: 'unconfigured', message: ai.message || 'AI is not configured. Uploads, hashing, receipts, arithmetic, review and export still work.' }
  const healthy = ai.providers.filter((p) => p.healthy)
  if (healthy.length === 0) return { state: 'degraded', message: ai.message || 'All AI providers are failing right now. Deterministic checks still run; AI sections say "unavailable".' }
  return { state: 'ok', message: ai.message, model: healthy[0].model }
}

export function HealthChip() {
  const { state, message, model } = useAiState()
  const chip =
    state === 'ok' ? <Chip tone="observed" icon={<Cpu size={11} />}>AI · {model}</Chip>
    : state === 'loading' ? <Chip tone="ink-3" icon={<Cpu size={11} />}>AI · checking</Chip>
    : state === 'degraded' ? <Chip tone="inferred" dashed icon={<TriangleAlert size={11} />}>AI degraded</Chip>
    : <Chip tone="stale" hatch icon={<CloudOff size={11} />}>{state === 'unconfigured' ? 'AI not configured' : 'API unreachable'}</Chip>
  return <Tooltip text={message || 'AI provider status'}>{chip}</Tooltip>
}

export function AiBanner() {
  const { state, message } = useAiState()
  if (state === 'ok' || state === 'loading') return null
  const title = state === 'degraded' ? 'AI degraded' : state === 'unconfigured' ? 'AI not configured' : 'API unreachable'
  return (
    <div role="status" className="hatch flex items-start gap-2 border-b border-dashed border-stale px-4 py-2 text-xs text-ink-2">
      <TriangleAlert size={14} className="mt-px shrink-0 text-inferred" />
      <div><strong className="text-ink">{title}.</strong> {message.trim().replace(/[.;:,]?$/, '.')} Nothing is fabricated: model-dependent sections will show as unavailable.</div>
    </div>
  )
}
