import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import CommandCenter from './pages/CommandCenter'
import PolicyVault from './pages/PolicyVault'
import PolicyIntelligence from './pages/PolicyIntelligence'
import PolicyAssistant from './pages/PolicyAssistant'

export default function App() {
  return (
    <div className="flex h-screen w-screen bg-surface-primary overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<CommandCenter />} />
          <Route path="/vault" element={<PolicyVault />} />
          <Route path="/intelligence" element={<PolicyIntelligence />} />
          <Route path="/assistant" element={<PolicyAssistant />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
