import { useLocation, useNavigate } from 'react-router-dom'
import saamaLogo from '../assets/saama_logo.svg'

export default function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const isLanding = location.pathname === '/'

  return (
    <header className="sticky top-0 z-[60] flex items-center h-14 px-5 border-b border-border-primary bg-white/80 backdrop-blur-xl">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-0 shrink-0 hover:opacity-80 transition-opacity duration-200"
      >
        <img src={saamaLogo} alt="Saama" className="h-7 w-auto" />
      </button>

      <div className="mx-4 h-6 w-px bg-border-hover shrink-0" />

      <span className="text-[15px] font-semibold text-text-primary tracking-tight whitespace-nowrap">
        Payer Intelligence Platform
      </span>

      {!isLanding && (
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-text-quaternary">v1.0</span>
        </div>
      )}
    </header>
  )
}
