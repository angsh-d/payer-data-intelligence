import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import Sidebar from './components/Sidebar'
import ErrorBoundary from './components/ErrorBoundary'
import { ToastProvider } from './components/Toast'
import Landing from './pages/Landing'
import CommandCenter from './pages/CommandCenter'
import PolicyVault from './pages/PolicyVault'
import PolicyIntelligence from './pages/PolicyIntelligence'
import PolicyAssistant from './pages/PolicyAssistant'

export default function App() {
  const location = useLocation()
  const isLanding = location.pathname === '/'

  if (isLanding) {
    return (
      <ErrorBoundary>
        <ToastProvider>
          <div className="flex flex-col h-screen w-screen bg-surface-primary overflow-hidden">
            <Navbar />
            <main className="flex-1 overflow-y-auto">
              <Landing />
            </main>
          </div>
        </ToastProvider>
      </ErrorBoundary>
    )
  }

  return (
    <ErrorBoundary>
      <ToastProvider>
        <div className="flex flex-col h-screen w-screen bg-surface-primary overflow-hidden">
          <Navbar />
          <div className="flex flex-1 overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto">
              <ErrorBoundary>
                <Routes>
                  <Route path="/dashboard" element={<CommandCenter />} />
                  <Route path="/vault" element={<PolicyVault />} />
                  <Route path="/intelligence" element={<PolicyIntelligence />} />
                  <Route path="/assistant" element={<PolicyAssistant />} />
                  <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
              </ErrorBoundary>
            </main>
          </div>
        </div>
      </ToastProvider>
    </ErrorBoundary>
  )
}
