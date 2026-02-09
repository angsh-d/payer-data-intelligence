import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import {
  FileText,
  Layers,
  Users,
  Activity,
  ShieldCheck,
} from 'lucide-react'
import { api, type PolicyBankItem } from '../lib/api'
import { getDrugInfo, getPayerInfo } from '../lib/drugInfo'

function useCountUp(target: number, duration = 1200) {
  const [value, setValue] = useState(0)
  const ref = useRef<number | null>(null)

  useEffect(() => {
    if (target === 0) { setValue(0); return }
    const start = performance.now()
    const animate = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(eased * target))
      if (progress < 1) ref.current = requestAnimationFrame(animate)
    }
    ref.current = requestAnimationFrame(animate)
    return () => { if (ref.current) cancelAnimationFrame(ref.current) }
  }, [target, duration])

  return value
}

function qualityToPercent(q: string): number {
  switch (q?.toLowerCase()) {
    case 'high':
    case 'good': return 95
    case 'medium':
    case 'needs_review': return 70
    case 'low':
    case 'poor': return 40
    default: return 50
  }
}

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] as const },
  }),
}

function ShimmerBlock({ className }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl bg-surface-secondary ${className}`}>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.5s_infinite] bg-gradient-to-r from-transparent via-black/[0.04] to-transparent" />
    </div>
  )
}

function HealthGauge({ score }: { score: number }) {
  const size = 200
  const stroke = 10
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const [offset, setOffset] = useState(circumference)

  useEffect(() => {
    const timer = setTimeout(() => {
      setOffset(circumference - (score / 100) * circumference)
    }, 400)
    return () => clearTimeout(timer)
  }, [score, circumference])

  const displayScore = useCountUp(score, 1400)

  return (
    <div className="relative flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0071e3" />
            <stop offset="50%" stopColor="#30d158" />
            <stop offset="100%" stopColor="#0071e3" />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(0,0,0,0.06)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="url(#gaugeGradient)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.25, 0.46, 0.45, 0.94)' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-5xl font-semibold text-text-primary tracking-tight">{displayScore}</span>
        <span className="text-sm text-text-tertiary mt-1">Health Score</span>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color, index }: {
  icon: typeof FileText
  label: string
  value: number | string
  color: string
  index: number
}) {
  const numericValue = typeof value === 'number' ? value : 0
  const displayValue = useCountUp(numericValue, 1000)

  return (
    <motion.div
      custom={index}
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-6 flex flex-col gap-4"
    >
      <div className={`flex items-center justify-center w-10 h-10 rounded-xl ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-3xl font-semibold text-text-primary tracking-tight">
          {typeof value === 'string' ? value : displayValue}
        </p>
        <p className="text-sm text-text-tertiary mt-1">{label}</p>
      </div>
    </motion.div>
  )
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return dateStr
  }
}

export default function CommandCenter() {
  const [policies, setPolicies] = useState<PolicyBankItem[]>([])
  const [healthStatus, setHealthStatus] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const fetchData = async (attempt = 0) => {
      try {
        const [bankResult, healthResult] = await Promise.allSettled([
          api.getPolicyBank(),
          api.health(),
        ])
        if (cancelled) return
        if (bankResult.status === 'fulfilled' && bankResult.value.length > 0) {
          setPolicies(bankResult.value)
        } else if (bankResult.status === 'fulfilled') {
          setPolicies(bankResult.value)
        } else if (attempt < 2) {
          setTimeout(() => fetchData(attempt + 1), 2000)
          return
        }
        if (healthResult.status === 'fulfilled') setHealthStatus(healthResult.value.status)
        else setHealthStatus('error')
        setLoading(false)
      } catch {
        if (!cancelled && attempt < 2) {
          setTimeout(() => fetchData(attempt + 1), 2000)
        } else {
          setLoading(false)
        }
      }
    }
    fetchData()
    return () => { cancelled = true }
  }, [])

  const totalPolicies = policies.length
  const totalVersions = policies.reduce((sum, p) => sum + (p.version_count || 0), 0)
  const uniquePayers = new Set(policies.map(p => p.payer)).size

  const avgHealthScore = policies.length > 0
    ? Math.round(policies.reduce((sum, p) => sum + qualityToPercent(p.extraction_quality), 0) / policies.length)
    : 0

  const recentPolicies = [...policies]
    .sort((a, b) => new Date(b.last_updated).getTime() - new Date(a.last_updated).getTime())
    .slice(0, 6)

  const healthLabel = healthStatus === 'ok' || healthStatus === 'healthy'
    ? 'Operational'
    : healthStatus === 'error'
    ? 'Degraded'
    : healthStatus || '—'

  if (loading) {
    return (
      <div className="p-10 space-y-8">
        <div className="space-y-2">
          <ShimmerBlock className="h-8 w-64" />
          <ShimmerBlock className="h-5 w-48" />
        </div>
        <div className="grid grid-cols-4 gap-5">
          {[...Array(4)].map((_, i) => <ShimmerBlock key={i} className="h-32" />)}
        </div>
        <div className="grid grid-cols-2 gap-5">
          <ShimmerBlock className="h-72" />
          <ShimmerBlock className="h-72" />
        </div>
      </div>
    )
  }

  return (
    <div className="p-10 space-y-8 max-w-[1400px]">
      <style>{`
        @keyframes shimmer {
          100% { transform: translateX(200%); }
        }
      `}</style>

      <motion.div
        custom={0}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
      >
        <h1 className="text-3xl font-semibold text-text-primary tracking-tight">Command Center</h1>
        <p className="text-text-tertiary mt-1">Policy intelligence at a glance</p>
      </motion.div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatCard
          icon={FileText}
          label="Total Policies"
          value={totalPolicies}
          color="bg-accent-blue/10 text-accent-blue"
          index={1}
        />
        <StatCard
          icon={Layers}
          label="Total Versions"
          value={totalVersions}
          color="bg-accent-purple/10 text-accent-purple"
          index={2}
        />
        <StatCard
          icon={Users}
          label="Payers Tracked"
          value={uniquePayers}
          color="bg-accent-amber/10 text-accent-amber"
          index={3}
        />
        <StatCard
          icon={Activity}
          label="System Health"
          value={healthLabel}
          color={
            healthLabel === 'Operational'
              ? 'bg-accent-green/10 text-accent-green'
              : 'bg-accent-red/10 text-accent-red'
          }
          index={4}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <motion.div
          custom={5}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="lg:col-span-2 rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8 flex flex-col items-center justify-center gap-4"
        >
          <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase">Digitalization Quality</h2>
          {policies.length > 0 ? (
            <HealthGauge score={avgHealthScore} />
          ) : (
            <div className="flex flex-col items-center gap-2 py-8">
              <ShieldCheck className="w-10 h-10 text-text-quaternary" />
              <p className="text-text-tertiary text-sm">No policies analyzed yet</p>
            </div>
          )}
        </motion.div>

        <motion.div
          custom={6}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="lg:col-span-3 rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8"
        >
          <h2 className="text-sm font-medium text-text-secondary tracking-wide uppercase mb-6">Recent Activity</h2>
          {recentPolicies.length > 0 ? (
            <div className="space-y-1">
              {recentPolicies.map((policy, i) => (
                <motion.div
                  key={`${policy.payer}-${policy.medication}`}
                  custom={7 + i}
                  variants={fadeUp}
                  initial="hidden"
                  animate="visible"
                  className="flex items-center gap-4 p-3 rounded-xl hover:bg-surface-hover/50 transition-colors duration-200 group"
                >
                  {(() => { const drugInfo = getDrugInfo(policy.medication); const DrugIcon = drugInfo.icon; return (
                  <div className={`flex items-center justify-center w-8 h-8 rounded-lg shrink-0 ${drugInfo.color}`}>
                    <DrugIcon className="w-4 h-4" />
                  </div>
                  ); })()}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">
                      {getPayerInfo(policy.payer).abbreviation}
                      <span className="text-text-tertiary font-normal"> · </span>
                      <span className="text-text-secondary font-normal">{getDrugInfo(policy.medication).brandName}</span>
                    </p>
                    <p className="text-xs text-text-tertiary mt-0.5">
                      v{policy.latest_version} · Updated {formatDate(policy.last_updated)}
                    </p>
                  </div>
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium shrink-0 ${
                    ['high', 'good'].includes(policy.extraction_quality?.toLowerCase())
                      ? 'bg-accent-green/10 text-accent-green'
                      : ['medium', 'needs_review'].includes(policy.extraction_quality?.toLowerCase())
                      ? 'bg-accent-amber/10 text-accent-amber'
                      : 'bg-accent-red/10 text-accent-red'
                  }`}>
                    {policy.extraction_quality === 'good' ? 'Good' : policy.extraction_quality === 'needs_review' ? 'Needs Review' : policy.extraction_quality || 'Unknown'}
                  </span>
                </motion.div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <FileText className="w-10 h-10 text-text-quaternary" />
              <p className="text-text-tertiary text-sm">No recent activity</p>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}
