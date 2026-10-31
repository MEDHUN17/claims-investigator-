import { Component, type ReactNode } from 'react'

/** Quiet error boundary for decorative WebGL: on failure, render the static fallback and log once. */
export class FxBoundary extends Component<{ children: ReactNode; fallback: ReactNode; label?: string }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(err: Error) { console.warn(`[fx] ${this.props.label ?? 'effect'} disabled:`, err.message) }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}
