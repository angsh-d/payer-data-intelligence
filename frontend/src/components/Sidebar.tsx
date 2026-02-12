import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  Archive,
  GitCompareArrows,
  MessageSquare,
  ChevronRight,
  Sparkles,
} from 'lucide-react'

const navItems = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Command Center' },
  { path: '/vault', icon: Archive, label: 'Policy Vault' },
  { path: '/intelligence', icon: GitCompareArrows, label: 'Formulary Intelligence' },
  { path: '/assistant', icon: MessageSquare, label: 'Policy Assistant' },
]

export default function Sidebar() {
  const [expanded, setExpanded] = useState(false)
  const location = useLocation()

  return (
    <motion.aside
      className="relative z-50 flex flex-col h-screen border-r border-border-primary bg-surface-secondary/80 backdrop-blur-2xl"
      initial={false}
      animate={{ width: expanded ? 240 : 72 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
    >
      <div className="flex items-center h-16 px-5 gap-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-accent-blue/10">
          <Sparkles className="w-4 h-4 text-accent-blue" />
        </div>
        <AnimatePresence>
          {expanded && (
            <motion.span
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="text-sm font-semibold text-text-primary whitespace-nowrap tracking-tight"
            >
              Agenti AI
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <nav className="flex-1 flex flex-col gap-1 px-3 mt-4">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className="group relative flex items-center gap-3 h-11 rounded-xl px-3 transition-all duration-200"
            >
              {isActive && (
                <motion.div
                  layoutId="sidebar-active"
                  className="absolute inset-0 rounded-xl bg-surface-hover"
                  transition={{ type: 'spring', stiffness: 500, damping: 35 }}
                />
              )}
              <div className="relative z-10 flex items-center gap-3 w-full">
                <item.icon
                  className={`w-[18px] h-[18px] shrink-0 transition-colors duration-200 ${
                    isActive ? 'text-text-primary' : 'text-text-tertiary group-hover:text-text-secondary'
                  }`}
                />
                <AnimatePresence>
                  {expanded && (
                    <motion.span
                      initial={{ opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -4 }}
                      transition={{ duration: 0.12 }}
                      className={`text-[13px] whitespace-nowrap transition-colors duration-200 ${
                        isActive
                          ? 'text-text-primary font-medium'
                          : 'text-text-tertiary group-hover:text-text-secondary'
                      }`}
                    >
                      {item.label}
                    </motion.span>
                  )}
                </AnimatePresence>
              </div>
            </NavLink>
          )
        })}
      </nav>

      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-center h-12 mx-3 mb-4 rounded-xl text-text-quaternary hover:text-text-tertiary hover:bg-surface-hover/50 transition-all duration-200"
      >
        <motion.div
          animate={{ rotate: expanded ? 180 : 0 }}
          transition={{ type: 'spring', stiffness: 400, damping: 25 }}
        >
          <ChevronRight className="w-4 h-4" />
        </motion.div>
      </button>
    </motion.aside>
  )
}
