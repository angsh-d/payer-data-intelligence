import { Component, type ReactNode, type ErrorInfo } from 'react'
import { motion } from 'framer-motion'
import { AlertCircle, RotateCcw } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (!this.state.hasError) return this.props.children

    if (this.props.fallback) return this.props.fallback

    return (
      <div className="flex items-center justify-center h-full w-full bg-surface-secondary">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          className="flex flex-col items-center gap-4 max-w-md p-8 rounded-2xl bg-surface-elevated border border-border-primary shadow-lg"
        >
          <div className="flex items-center justify-center w-12 h-12 rounded-full bg-accent-red/10">
            <AlertCircle className="w-6 h-6 text-accent-red" />
          </div>

          <div className="text-center">
            <h2 className="text-lg font-semibold text-text-primary">
              Something went wrong
            </h2>
            <p className="mt-1 text-sm text-text-tertiary leading-relaxed">
              An unexpected error occurred. Try again or refresh the page.
            </p>
          </div>

          {this.state.error && (
            <pre className="w-full px-3 py-2 rounded-lg bg-surface-secondary text-xs text-text-tertiary font-mono overflow-x-auto max-h-24">
              {this.state.error.message}
            </pre>
          )}

          <button
            onClick={this.handleReset}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue-hover transition-colors duration-200"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Try Again
          </button>
        </motion.div>
      </div>
    )
  }
}
