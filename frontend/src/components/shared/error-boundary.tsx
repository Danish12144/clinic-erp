import { AlertTriangle } from 'lucide-react'
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

// React error boundaries must be class components — there is no hook
// equivalent (no `useErrorBoundary` in React itself). Catches any render
// exception below it, including one thrown by a React.lazy() chunk that
// fails to load (a stale deploy, a flaky network), and shows a recovery UI
// instead of a white screen. This intentionally wraps the whole app in
// main.tsx rather than one boundary per route — a crash anywhere still
// needs the same "reload" recovery, and per-route boundaries would need
// their own reset-on-navigation wiring for no real benefit at this scale.
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-6 text-center dark:bg-slate-900">
          <div className="flex size-12 items-center justify-center rounded-full bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400">
            <AlertTriangle className="size-6" />
          </div>
          <div className="flex flex-col gap-1">
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-50">Something went wrong</h1>
            <p className="max-w-sm text-sm text-slate-500 dark:text-slate-400">
              An unexpected error occurred. Reloading the page usually fixes this.
            </p>
          </div>
          <Button onClick={() => window.location.reload()}>Reload page</Button>
        </div>
      )
    }
    return this.props.children
  }
}
