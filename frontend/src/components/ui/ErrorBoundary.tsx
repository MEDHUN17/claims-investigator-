import { Component, type ReactNode } from 'react'

/** Keeps one broken panel from blanking the whole workspace. */
export class ErrorBoundary extends Component<{ children: ReactNode; label?: string }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="m-4 rounded-lg border border-dashed border-discrepancy/60 p-4 text-sm">
          <strong>{this.props.label ?? 'This panel'} failed to render.</strong>
          <div className="mono mt-1 break-words text-xs text-ink-2">{this.state.error.message}</div>
          <button className="mt-2 cursor-pointer text-xs text-accent underline" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      )
    }
    return this.props.children
  }
}
