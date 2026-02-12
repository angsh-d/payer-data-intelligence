import { useLocation, useNavigate } from 'react-router-dom'
import saamaLogo from '../assets/saama_logo.svg'

export default function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const isLanding = location.pathname === '/'
  const isAgents = location.pathname === '/agents'

  return (
    <header className="z-[60] flex items-center h-14 min-h-[3.5rem] px-5 border-b border-border-primary bg-white/80 backdrop-blur-xl shrink-0">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-0 shrink-0 hover:opacity-80 transition-opacity duration-200"
      >
        <img src={saamaLogo} alt="Saama" className="h-7 w-auto" />
      </button>

      <div className="mx-4 h-6 w-px bg-border-hover shrink-0" />

      <button
        onClick={() => navigate('/')}
        className="text-[15px] font-semibold text-text-primary tracking-tight whitespace-nowrap hover:opacity-80 transition-opacity duration-200"
      >
        Formulary Intelligence Agent
      </button>

      {(isLanding || isAgents) && (
        <div className="ml-auto flex items-center gap-6">
          <button
            onClick={() => navigate('/agents')}
            className={`text-[13px] font-medium transition-colors duration-200 ${
              isAgents ? 'text-text-primary' : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            Agents
          </button>
        </div>
      )}

      {!(isLanding || isAgents) && (
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-text-quaternary">v1.0</span>
        </div>
      )}
    </header>
  )
}
