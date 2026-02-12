import { useState, useEffect, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  GitCompareArrows,
  ChevronDown,
  ChevronRight,
  Search,
  FileText,
  Clock,
  ArrowRight,
  Plus,
  Minus,
  RefreshCw,
  CheckCircle2,
  Info,
  Sparkles,
  List,
  Upload,
  Users,
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  Shield,
  Download,
  BarChart3,
  Pill,
  Zap,
  Hash,
  Check,
  X,
} from 'lucide-react'
import { api, type PolicyBankItem, type PolicyVersion, type DiffSummaryResponse, type CrossPayerResponse } from '../lib/api'
import { getDrugInfo, getPayerInfo } from '../lib/drugInfo'

/* ─── Apple-style animation presets ─── */
const ease = [0.25, 0.46, 0.45, 0.94] as const

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.06, duration: 0.5, ease },
  }),
}

const fadeIn = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.4, ease } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
}

/* ─── Skeleton shimmer ─── */
function Skeleton({ className }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-xl bg-[#f0f0f2] ${className}`}>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.5s_infinite] bg-gradient-to-r from-transparent via-white/60 to-transparent" />
    </div>
  )
}

/* ─── Minimal Apple spinner ─── */
function Spinner({ size = 20 }: { size?: number }) {
  return (
    <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
      <RefreshCw style={{ width: size, height: size }} className="text-text-tertiary" />
    </motion.div>
  )
}

/* ─── Multi-step analysis progress ─── */
const DIFF_STEPS = [
  'Loading policy versions...',
  'Parsing structured criteria...',
  'Matching criteria across versions...',
  'Detecting additions & removals...',
  'Classifying change severity...',
  'Generating executive summary...',
]
const IMPACT_STEPS = [
  'Loading policy diff...',
  'Identifying affected patient cohorts...',
  'Evaluating coverage under old policy...',
  'Evaluating coverage under new policy...',
  'Computing verdict changes...',
  'Assessing clinical impact...',
]
const CROSS_PAYER_STEPS = [
  'Loading payer policies...',
  'Extracting criteria per payer...',
  'Aligning coverage dimensions...',
  'Comparing restrictiveness levels...',
  'Identifying coverage gaps...',
  'Generating cross-payer summary...',
]

function AnalysisProgress({ steps, currentStep }: { steps: string[]; currentStep: number }) {
  return (
    <motion.div variants={fadeIn} initial="hidden" animate="visible"
      className="rounded-2xl bg-[#f5f5f7] p-8"
    >
      <div className="flex flex-col items-center justify-center py-8 gap-6">
        <Spinner size={22} />
        <div className="w-full max-w-xs space-y-2.5">
          {steps.map((label, i) => {
            const done = i < currentStep
            const active = i === currentStep
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: active || done ? 1 : 0.35, x: 0 }}
                transition={{ duration: 0.35, delay: active ? 0.1 : 0 }}
                className="flex items-center gap-2.5"
              >
                <div className={`w-[18px] h-[18px] rounded-full flex items-center justify-center shrink-0 transition-colors duration-300 ${
                  done ? 'bg-[#1d1d1f]' : active ? 'bg-[#1d1d1f]' : 'bg-[#e8e8ed]'
                }`}>
                  {done ? (
                    <Check className="w-[10px] h-[10px] text-white" />
                  ) : active ? (
                    <motion.div
                      className="w-[6px] h-[6px] rounded-full bg-white"
                      animate={{ scale: [1, 1.4, 1] }}
                      transition={{ duration: 1, repeat: Infinity }}
                    />
                  ) : (
                    <div className="w-[4px] h-[4px] rounded-full bg-[#aeaeb2]" />
                  )}
                </div>
                <span className={`text-[12px] transition-colors duration-300 ${
                  done ? 'text-text-tertiary' : active ? 'text-text-primary font-medium' : 'text-text-quaternary'
                }`}>
                  {label}
                </span>
              </motion.div>
            )
          })}
        </div>
      </div>
    </motion.div>
  )
}

type DiffTab = 'summary' | 'changes' | 'impact'

/* ─── Apple segmented control ─── */
function SegmentedControl({ tabs, active, onChange }: {
  tabs: { key: DiffTab; label: string; icon: typeof Sparkles }[]
  active: DiffTab
  onChange: (tab: DiffTab) => void
}) {
  return (
    <div className="flex items-center bg-[#f0f0f2] rounded-[10px] p-[3px] gap-[2px]">
      {tabs.map((tab) => {
        const Icon = tab.icon
        const isActive = active === tab.key
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`relative flex items-center gap-2 px-4 py-[7px] rounded-[8px] text-[13px] font-medium transition-colors duration-200 ${
              isActive ? 'text-text-primary' : 'text-text-tertiary hover:text-text-secondary'
            }`}
          >
            {isActive && (
              <motion.div
                layoutId="segment-bg"
                className="absolute inset-0 bg-white rounded-[8px] shadow-[0_1px_3px_rgba(0,0,0,0.08),0_1px_2px_rgba(0,0,0,0.04)]"
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
            <span className="relative z-10 flex items-center gap-1.5">
              <Icon className="w-[14px] h-[14px]" />
              {tab.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/* ─── Helpers ─── */
function formatDate(dateStr: string): string {
  try {
    const dateOnlyMatch = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/)
    const d = dateOnlyMatch
      ? new Date(Number(dateOnlyMatch[1]), Number(dateOnlyMatch[2]) - 1, Number(dateOnlyMatch[3]))
      : new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return dateStr
  }
}

function vLabel(v: string | null | undefined) {
  if (!v) return ''
  return v.startsWith('v') ? v : `v${v}`
}

function severityDot(severity: string) {
  switch (severity?.toLowerCase()) {
    case 'breaking': return 'bg-[#1d1d1f]'
    case 'material': return 'bg-text-secondary'
    case 'minor': return 'bg-text-quaternary'
    default: return 'bg-text-quaternary'
  }
}

function severityLabel(severity: string) {
  switch (severity?.toLowerCase()) {
    case 'breaking': return 'High Impact'
    case 'material': return 'Moderate'
    case 'minor': return 'Low'
    case 'cosmetic': return 'Cosmetic'
    default: return 'Info'
  }
}

function changeTypeIcon(type: string) {
  switch (type?.toLowerCase()) {
    case 'added': return <Plus className="w-3 h-3 text-text-secondary" />
    case 'removed': return <Minus className="w-3 h-3 text-text-secondary" />
    case 'modified': return <RefreshCw className="w-3 h-3 text-text-secondary" />
    default: return <Info className="w-3 h-3 text-text-tertiary" />
  }
}

/* ─── Main Component ─── */
export default function PolicyIntelligence() {
  const [policies, setPolicies] = useState<PolicyBankItem[]>([])
  const [policiesLoading, setPoliciesLoading] = useState(true)
  const [selectedPolicy, setSelectedPolicy] = useState<PolicyBankItem | null>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const [versions, setVersions] = useState<PolicyVersion[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [selectedOld, setSelectedOld] = useState<string | null>(null)
  const [selectedNew, setSelectedNew] = useState<string | null>(null)

  const [diffResult, setDiffResult] = useState<DiffSummaryResponse | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffError, setDiffError] = useState<string | null>(null)
  const [diffStep, setDiffStep] = useState(0)
  const [impactStep, setImpactStep] = useState(0)
  const [crossPayerStep, setCrossPayerStep] = useState(0)
  const [activeTab, setActiveTab] = useState<DiffTab>('summary')
  const [expandedChanges, setExpandedChanges] = useState<Set<number>>(new Set())

  const [impactResult, setImpactResult] = useState<any>(null)
  const [impactLoading, setImpactLoading] = useState(false)
  const [impactError, setImpactError] = useState<string | null>(null)
  const [expandedPatients, setExpandedPatients] = useState<Set<string>>(new Set())

  type PageMode = 'version-diff' | 'cross-payer'
  const [activeMode, setActiveMode] = useState<PageMode>('version-diff')
  const [crossPayerMedication, setCrossPayerMedication] = useState('')
  const [crossPayerResult, setCrossPayerResult] = useState<CrossPayerResponse | null>(null)
  const [crossPayerLoading, setCrossPayerLoading] = useState(false)
  const [crossPayerError, setCrossPayerError] = useState<string | null>(null)

  useEffect(() => {
    api.getPolicyBank()
      .then(setPolicies)
      .catch(() => setPolicies([]))
      .finally(() => setPoliciesLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedPolicy) {
      setVersions([]); setSelectedOld(null); setSelectedNew(null); setDiffResult(null); setDiffError(null)
      return
    }
    setVersionsLoading(true); setSelectedOld(null); setSelectedNew(null); setDiffResult(null); setDiffError(null)
    api.getPolicyVersions(selectedPolicy.payer, selectedPolicy.medication)
      .then(setVersions)
      .catch(() => setVersions([]))
      .finally(() => setVersionsLoading(false))
  }, [selectedPolicy])

  const handleVersionClick = useCallback((version: string) => {
    setDiffResult(null); setDiffError(null)
    if (selectedOld === version) { setSelectedOld(null) }
    else if (selectedNew === version) { setSelectedNew(null) }
    else if (!selectedOld) { setSelectedOld(version) }
    else if (!selectedNew) {
      if (version < selectedOld) { setSelectedNew(selectedOld); setSelectedOld(version) }
      else { setSelectedNew(version) }
    } else { setSelectedOld(version); setSelectedNew(null) }
  }, [selectedOld, selectedNew])

  const handleCompare = useCallback(async () => {
    if (!selectedPolicy || !selectedOld || !selectedNew) return
    setDiffLoading(true); setDiffError(null); setDiffStep(0); setActiveTab('summary'); setExpandedChanges(new Set())
    setImpactResult(null); setImpactError(null); setExpandedPatients(new Set())
    try {
      // Fire API call immediately, but show steps animation for 6-8s
      const resultPromise = api.getDiffSummary(selectedPolicy.payer, selectedPolicy.medication, selectedOld, selectedNew)
      const stepDelay = 1100 + Math.random() * 200 // ~1.1-1.3s per step
      for (let i = 0; i < DIFF_STEPS.length; i++) {
        setDiffStep(i)
        await new Promise(r => setTimeout(r, stepDelay))
      }
      const result = await resultPromise
      setDiffResult(result)
    } catch (err: any) {
      setDiffResult(null); setDiffError(err?.message || 'Failed to load comparison')
    } finally { setDiffLoading(false) }
  }, [selectedPolicy, selectedOld, selectedNew])

  const fetchImpact = useCallback(async () => {
    if (!selectedPolicy || !selectedOld || !selectedNew) return
    if (impactResult || impactLoading) return
    setImpactLoading(true); setImpactError(null); setImpactStep(0)
    try {
      const resultPromise = api.getImpact(selectedPolicy.payer, selectedPolicy.medication, selectedOld, selectedNew)
      const stepDelay = 1100 + Math.random() * 200
      for (let i = 0; i < IMPACT_STEPS.length; i++) {
        setImpactStep(i)
        await new Promise(r => setTimeout(r, stepDelay))
      }
      const result = await resultPromise
      setImpactResult(result)
    } catch (err: any) {
      setImpactError(err?.message || 'Failed to load impact analysis')
    } finally { setImpactLoading(false) }
  }, [selectedPolicy, selectedOld, selectedNew, impactResult, impactLoading])

  useEffect(() => {
    if (activeTab === 'impact' && !impactResult && !impactLoading && !impactError) { fetchImpact() }
  }, [activeTab, fetchImpact, impactResult, impactLoading, impactError])

  const uniqueMedications = useMemo(() => {
    const meds = new Set(policies.map(p => p.medication))
    return Array.from(meds).sort()
  }, [policies])

  const handleCrossPayerAnalysis = useCallback(async () => {
    if (!crossPayerMedication.trim()) return
    setCrossPayerLoading(true); setCrossPayerError(null); setCrossPayerResult(null); setCrossPayerStep(0)
    try {
      const resultPromise = api.crossPayerAnalysis(crossPayerMedication.trim())
      const stepDelay = 1100 + Math.random() * 200
      for (let i = 0; i < CROSS_PAYER_STEPS.length; i++) {
        setCrossPayerStep(i)
        await new Promise(r => setTimeout(r, stepDelay))
      }
      const result = await resultPromise
      setCrossPayerResult(result)
    } catch (err: any) {
      setCrossPayerError(err?.message || 'Cross-payer analysis failed')
    } finally { setCrossPayerLoading(false) }
  }, [crossPayerMedication])

  const diffData = diffResult?.diff
  const rawChanges = diffData?.changes || diffData?.criterion_changes || []
  const changes: any[] = (() => {
    let all: any[] = []
    if (Array.isArray(rawChanges)) { all = rawChanges }
    else if (typeof rawChanges === 'object' && rawChanges !== null) {
      all = [...(rawChanges.criteria || []), ...(rawChanges.indications || []), ...(rawChanges.step_therapy || []), ...(rawChanges.exclusions || [])]
    }
    const seen = new Set<string>()
    return all.filter(c => {
      const id = c.criterion_id || c.criterion_name || c.indication_id || c.name || JSON.stringify(c)
      if (seen.has(id)) return false
      seen.add(id); return true
    })
  })()

  /* ─── Render ─── */
  return (
    <div className="p-10 max-w-[1400px] space-y-8">
      <style>{`@keyframes shimmer { 100% { transform: translateX(200%); } }`}</style>

      {/* Header */}
      <motion.div custom={0} variants={fadeUp} initial="hidden" animate="visible">
        <h1 className="text-[34px] font-semibold text-text-primary tracking-[-0.015em] leading-tight">
          Formulary Intelligence
        </h1>
        <p className="text-[15px] text-text-tertiary mt-1.5 tracking-[-0.01em]">
          Version tracking, change analysis, and cross-payer comparison
        </p>
      </motion.div>

      {/* Mode Switcher — Apple Segmented Control */}
      <motion.div custom={0.5} variants={fadeUp} initial="hidden" animate="visible">
        <div className="flex items-center bg-[#f0f0f2] rounded-[10px] p-[3px] gap-[2px] w-fit">
          {([
            { key: 'version-diff' as PageMode, label: 'Version Diff', icon: GitCompareArrows },
            { key: 'cross-payer' as PageMode, label: 'Cross-Payer Analysis', icon: BarChart3 },
          ]).map((tab) => {
            const Icon = tab.icon
            const isActive = activeMode === tab.key
            return (
              <button
                key={tab.key}
                onClick={() => setActiveMode(tab.key)}
                className={`relative flex items-center gap-2 px-5 py-[7px] rounded-[8px] text-[13px] font-medium transition-colors duration-200 ${
                  isActive ? 'text-text-primary' : 'text-text-tertiary hover:text-text-secondary'
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="mode-switcher-bg"
                    className="absolute inset-0 bg-white rounded-[8px] shadow-[0_1px_3px_rgba(0,0,0,0.08),0_1px_2px_rgba(0,0,0,0.04)]"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  <Icon className="w-[14px] h-[14px]" />
                  {tab.label}
                </span>
              </button>
            )
          })}
        </div>
      </motion.div>

      {/* ═══════════ VERSION DIFF MODE ═══════════ */}
      {activeMode === 'version-diff' && (
      <>
      {/* Policy Selector */}
      <motion.div custom={1} variants={fadeUp} initial="hidden" animate="visible">
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-3 px-4 py-3 rounded-xl bg-[#f5f5f7] hover:bg-[#ededf0] transition-colors duration-200 w-full max-w-md"
          >
            <Search className="w-[15px] h-[15px] text-text-tertiary" />
            <span className={`flex-1 text-left text-[14px] ${selectedPolicy ? 'text-text-primary font-medium' : 'text-text-tertiary'}`}>
              {selectedPolicy
                ? `${getPayerInfo(selectedPolicy.payer).abbreviation} · ${getDrugInfo(selectedPolicy.medication).brandName}`
                : 'Select a policy to analyze...'}
            </span>
            <ChevronDown className={`w-4 h-4 text-text-quaternary transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          <AnimatePresence>
            {dropdownOpen && (
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.98 }}
                transition={{ duration: 0.2, ease }}
                className="absolute z-50 mt-1.5 w-full max-w-md rounded-xl bg-white shadow-[0_4px_24px_rgba(0,0,0,0.12),0_0_0_1px_rgba(0,0,0,0.04)] overflow-hidden"
              >
                {policiesLoading ? (
                  <div className="p-3 space-y-2">
                    <Skeleton className="h-10" />
                    <Skeleton className="h-10" />
                    <Skeleton className="h-10" />
                  </div>
                ) : policies.length === 0 ? (
                  <div className="p-6 text-center text-text-tertiary text-[13px]">No policies found</div>
                ) : (
                  <div className="max-h-64 overflow-y-auto py-1">
                    {policies.map((p) => {
                      const isSelected = selectedPolicy?.payer === p.payer && selectedPolicy?.medication === p.medication
                      return (
                        <button
                          key={`${p.payer}-${p.medication}`}
                          onClick={() => { setSelectedPolicy(p); setDropdownOpen(false) }}
                          className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors duration-150 ${
                            isSelected ? 'bg-[#f5f5f7]' : 'hover:bg-[#f5f5f7]'
                          }`}
                        >
                          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[#f0f0f2] shrink-0">
                            <FileText className="w-[14px] h-[14px] text-text-tertiary" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[13px] font-medium text-text-primary truncate">{getPayerInfo(p.payer).abbreviation}</p>
                            <p className="text-[12px] text-text-tertiary truncate">{getDrugInfo(p.medication).brandName} · {p.version_count} versions</p>
                          </div>
                          {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-text-primary shrink-0" />}
                        </button>
                      )
                    })}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      {!selectedPolicy ? (
        <motion.div variants={fadeIn} initial="hidden" animate="visible"
          className="flex flex-col items-center justify-center py-32 gap-4"
        >
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-[#f5f5f7]">
            <GitCompareArrows className="w-7 h-7 text-text-quaternary" />
          </div>
          <p className="text-text-tertiary text-[14px]">Select a policy to begin analysis</p>
        </motion.div>
      ) : (
        <motion.div variants={fadeIn} initial="hidden" animate="visible" className="flex gap-6">
          {/* ── Left: Version Timeline ── */}
          <div className="w-[260px] shrink-0">
            <motion.div custom={2} variants={fadeUp} initial="hidden" animate="visible"
              className="rounded-2xl bg-[#f5f5f7] p-5"
            >
              <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase mb-5">
                Version Timeline
              </h3>

              {versionsLoading ? (
                <div className="space-y-4">
                  {[...Array(3)].map((_, i) => (
                    <div key={i} className="flex gap-3">
                      <Skeleton className="w-5 h-5 rounded-full shrink-0" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-16" />
                        <Skeleton className="h-3 w-28" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : versions.length < 2 ? (
                <div className="flex flex-col items-center py-8 gap-3">
                  <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#e8e8ed]">
                    <Upload className="w-[18px] h-[18px] text-text-quaternary" />
                  </div>
                  <p className="text-text-tertiary text-[12px] text-center leading-relaxed">
                    {versions.length === 0 ? 'No versions found' : 'Upload another version to enable comparison'}
                  </p>
                </div>
              ) : (
                <div className="relative">
                  <div className="absolute left-[9px] top-3 bottom-3 w-px bg-[#d2d2d7]" />

                  <div className="space-y-0.5">
                    {versions.map((v, i) => {
                      const isOld = selectedOld === v.version
                      const isNew = selectedNew === v.version
                      const isSelected = isOld || isNew
                      return (
                        <motion.button
                          key={v.version}
                          custom={3 + i}
                          variants={fadeUp}
                          initial="hidden"
                          animate="visible"
                          onClick={() => handleVersionClick(v.version)}
                          className={`relative w-full flex items-start gap-3 p-2.5 rounded-xl text-left transition-all duration-200 group ${
                            isSelected ? 'bg-white shadow-[0_1px_4px_rgba(0,0,0,0.06)]' : 'hover:bg-white/60'
                          }`}
                        >
                          {/* Timeline dot */}
                          <div className={`relative z-10 mt-0.5 w-[18px] h-[18px] rounded-full flex items-center justify-center shrink-0 transition-all duration-200 ${
                            isSelected
                              ? 'bg-[#1d1d1f]'
                              : 'bg-[#d2d2d7] group-hover:bg-[#aeaeb2]'
                          }`}>
                            {isSelected && (
                              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }}
                                className="w-[6px] h-[6px] rounded-full bg-white"
                              />
                            )}
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={`text-[13px] font-semibold ${isSelected ? 'text-text-primary' : 'text-text-primary'}`}>
                                {vLabel(v.version)}
                              </span>
                              {isOld && (
                                <span className="text-[10px] px-1.5 py-[1px] rounded-md bg-[#e8e8ed] text-text-secondary font-medium tracking-wide">
                                  OLDER
                                </span>
                              )}
                              {isNew && (
                                <span className="text-[10px] px-1.5 py-[1px] rounded-md bg-[#e8e8ed] text-text-secondary font-medium tracking-wide">
                                  NEWER
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-text-tertiary mt-0.5 flex items-center gap-1">
                              <Clock className="w-[11px] h-[11px]" />
                              {v.effective_date ? formatDate(v.effective_date) : v.effective_year ? `${v.effective_year}` : formatDate(v.cached_at)}
                            </p>
                            {v.source_filename && (
                              <p className="text-[11px] text-text-quaternary mt-0.5 truncate">{v.source_filename}</p>
                            )}
                          </div>
                        </motion.button>
                      )
                    })}
                  </div>
                </div>
              )}

              {selectedOld && selectedNew && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-5 pt-5 border-t border-[#d2d2d7]/60"
                >
                  <button
                    onClick={handleCompare}
                    disabled={diffLoading}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#1d1d1f] text-white text-[13px] font-medium hover:bg-[#333336] transition-colors duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {diffLoading ? (
                      <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
                        <RefreshCw className="w-[14px] h-[14px]" />
                      </motion.div>
                    ) : (
                      <>
                        <GitCompareArrows className="w-[14px] h-[14px]" />
                        Compare Versions
                      </>
                    )}
                  </button>
                  <p className="text-[11px] text-text-quaternary text-center mt-2">
                    {vLabel(selectedOld)} <ArrowRight className="w-[10px] h-[10px] inline" /> {vLabel(selectedNew)}
                  </p>
                </motion.div>
              )}
            </motion.div>
          </div>

          {/* ── Right: Diff Results ── */}
          <div className="flex-1 min-w-0">
            {diffLoading ? (
              <AnalysisProgress steps={DIFF_STEPS} currentStep={diffStep} />
            ) : diffError ? (
              <motion.div variants={fadeIn} initial="hidden" animate="visible"
                className="rounded-2xl bg-[#f5f5f7] p-8"
              >
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <div className="w-10 h-10 rounded-full bg-[#e8e8ed] flex items-center justify-center">
                    <AlertTriangle className="w-5 h-5 text-text-tertiary" />
                  </div>
                  <div className="text-center">
                    <p className="text-text-primary text-[14px] font-medium">Comparison failed</p>
                    <p className="text-text-tertiary text-[12px] mt-1">{diffError}</p>
                  </div>
                  <button
                    onClick={handleCompare}
                    className="text-[12px] text-text-secondary hover:text-text-primary font-medium underline underline-offset-2 mt-1"
                  >
                    Try again
                  </button>
                </div>
              </motion.div>
            ) : !diffResult ? (
              <motion.div variants={fadeIn} initial="hidden" animate="visible"
                className="rounded-2xl bg-[#f5f5f7] p-8"
              >
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-[#e8e8ed]">
                    <GitCompareArrows className="w-6 h-6 text-text-quaternary" />
                  </div>
                  <div className="text-center">
                    <p className="text-text-secondary text-[14px] font-medium">Select two versions to compare</p>
                    <p className="text-text-quaternary text-[12px] mt-1">Click on version nodes in the timeline</p>
                  </div>
                </div>
              </motion.div>
            ) : (
              <motion.div variants={fadeIn} initial="hidden" animate="visible" className="space-y-5">
                {/* Tab bar + version indicator */}
                <div className="flex items-center justify-between">
                  <SegmentedControl
                    tabs={[
                      { key: 'summary', label: 'Summary', icon: Sparkles },
                      { key: 'changes', label: 'Changes', icon: List },
                      { key: 'impact', label: 'Patient Impact', icon: Users },
                    ]}
                    active={activeTab}
                    onChange={setActiveTab}
                  />
                  <div className="flex items-center gap-3">
                    <span className="text-[12px] text-text-quaternary font-medium">
                      {vLabel(selectedOld)} → {vLabel(selectedNew)}
                    </span>
                    {selectedPolicy && selectedOld && selectedNew && (
                      <a
                        href={api.getDiffCsvUrl(selectedPolicy.payer, selectedPolicy.medication, selectedOld, selectedNew)}
                        download
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium text-text-secondary bg-[#f0f0f2] hover:bg-[#e8e8ed] transition-colors duration-200"
                      >
                        <Download className="w-3 h-3" />
                        Export CSV
                      </a>
                    )}
                  </div>
                </div>

                <AnimatePresence mode="wait">
                  {/* ── Summary Tab ── */}
                  {activeTab === 'summary' && (
                    <motion.div
                      key="summary"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      transition={{ duration: 0.3, ease }}
                      className="rounded-2xl bg-[#f5f5f7] p-8"
                    >
                      {(() => {
                        const summary = diffResult.summary
                        const s = typeof summary === 'string'
                          ? { executive_summary: summary } as Record<string, any>
                          : (typeof summary === 'object' && summary ? summary : {}) as Record<string, any>

                        const exec = typeof s.executive_summary === 'string' ? s.executive_summary : (s.executive_summary ? String(s.executive_summary) : '')
                        const sections = [
                          { key: 'breaking_changes_summary', label: 'High Impact', weight: 'font-semibold', dotColor: 'bg-[#1d1d1f]' },
                          { key: 'material_changes_summary', label: 'Medium Impact', weight: 'font-medium', dotColor: 'bg-text-secondary' },
                          { key: 'minor_changes_summary', label: 'Low Impact', weight: 'font-normal', dotColor: 'bg-text-quaternary' },
                        ]
                        const actions = s.recommended_actions || null

                        const splitBullets = (raw: any): string[] => {
                          if (!raw) return []
                          if (Array.isArray(raw)) return raw.map(r => String(r)).filter(b => b.length > 5)
                          const text = String(raw)
                          if (!text) return []
                          const byNewline = text.split(/\n/).map(b => b.replace(/^[-•*]\s*/, '').trim()).filter(b => b.length > 5)
                          if (byNewline.length > 1) return byNewline
                          return text.split(/[.,;](?=\s[A-Z])/).map(b => b.replace(/^[.,;]\s*/, '').trim()).filter(b => b.length > 10)
                        }

                        return (
                          <div className="space-y-6">
                            {exec && (
                              <p className="text-[15px] text-text-primary leading-[1.65] tracking-[-0.01em]">{exec}</p>
                            )}

                            {sections.some(sec => s[sec.key]) && (
                              <div className="rounded-xl bg-white overflow-hidden">
                                {sections.map((sec, si) => {
                                  const content = s[sec.key]
                                  if (!content) return null
                                  const items = splitBullets(content)
                                  return (
                                    <div key={sec.key}>
                                      {si > 0 && s[sections[si - 1]?.key] && (
                                        <div className="mx-5 border-t border-[#e8e8ed]" />
                                      )}
                                      <div className="px-5 py-4">
                                        <div className="flex items-center gap-2 mb-3">
                                          <span className={`w-[6px] h-[6px] rounded-full ${sec.dotColor}`} />
                                          <span className={`text-[11px] ${sec.weight} uppercase tracking-[0.06em] text-text-secondary`}>{sec.label}</span>
                                        </div>
                                        <div className="space-y-2 pl-[14px]">
                                          {items.map((item, ii) => (
                                            <p key={ii} className="text-[13px] text-text-primary leading-[1.55] relative pl-3.5 before:content-[''] before:absolute before:left-0 before:top-[7px] before:w-[4px] before:h-[4px] before:rounded-full before:bg-[#d2d2d7]">
                                              {item}
                                            </p>
                                          ))}
                                        </div>
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            )}

                            {actions && splitBullets(actions).length > 0 && (
                              <div className="rounded-xl bg-white px-5 py-4">
                                <div className="flex items-center gap-2 mb-3">
                                  <CheckCircle2 className="w-[13px] h-[13px] text-text-secondary" />
                                  <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-secondary">Recommended Actions</span>
                                </div>
                                <div className="space-y-2 pl-[14px]">
                                  {splitBullets(actions).map((item, ii) => (
                                    <p key={ii} className="text-[13px] text-text-primary leading-[1.55] relative pl-3.5 before:content-[''] before:absolute before:left-0 before:top-[7px] before:w-[4px] before:h-[4px] before:rounded-full before:bg-[#d2d2d7]">
                                      {item}
                                    </p>
                                  ))}
                                </div>
                              </div>
                            )}

                            {!exec && !sections.some(sec => s[sec.key]) && !actions && (
                              <p className="text-text-tertiary text-[13px]">No summary available for this comparison.</p>
                            )}
                          </div>
                        )
                      })()}
                    </motion.div>
                  )}

                  {/* ── Impact Tab ── */}
                  {activeTab === 'impact' && (
                    <motion.div
                      key="impact"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      transition={{ duration: 0.3, ease }}
                      className="space-y-5"
                    >
                      {impactLoading ? (
                        <AnalysisProgress steps={IMPACT_STEPS} currentStep={impactStep} />
                      ) : impactError ? (
                        <div className="rounded-2xl bg-[#f5f5f7] p-8">
                          <div className="flex flex-col items-center justify-center py-8 gap-3">
                            <div className="w-10 h-10 rounded-full bg-[#e8e8ed] flex items-center justify-center">
                              <AlertTriangle className="w-5 h-5 text-text-tertiary" />
                            </div>
                            <p className="text-text-secondary text-[13px]">{impactError}</p>
                            <button
                              onClick={() => { setImpactResult(null); setImpactError(null); fetchImpact() }}
                              className="text-[12px] text-text-secondary hover:text-text-primary font-medium underline underline-offset-2 mt-1"
                            >
                              Try again
                            </button>
                          </div>
                        </div>
                      ) : impactResult ? (
                        <>
                          {/* Stats grid */}
                          <div className="grid grid-cols-4 gap-3">
                            {[
                              { label: 'Active Cases', value: impactResult.total_active_cases, icon: Users },
                              { label: 'Impacted', value: impactResult.impacted_cases, icon: AlertTriangle },
                              { label: 'Verdict Flips', value: impactResult.verdict_flips, icon: TrendingDown },
                              { label: 'At Risk', value: impactResult.at_risk_cases, icon: Shield },
                            ].map((stat) => (
                              <div key={stat.label} className="rounded-2xl bg-[#f5f5f7] p-4">
                                <div className="flex items-center gap-2 mb-3">
                                  <stat.icon className="w-[14px] h-[14px] text-text-tertiary" />
                                  <span className="text-[11px] text-text-tertiary font-medium tracking-wide">{stat.label}</span>
                                </div>
                                <span className="text-[28px] font-semibold text-text-primary tracking-tight">{stat.value}</span>
                              </div>
                            ))}
                          </div>

                          {impactResult.action_items?.length > 0 && (
                            <div className="rounded-2xl bg-[#f5f5f7] p-5">
                              <h4 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.06em] mb-3">Action Items</h4>
                              <ul className="space-y-2">
                                {impactResult.action_items.map((item: string, i: number) => (
                                  <li key={i} className="flex items-start gap-2 text-[13px] text-text-primary leading-relaxed">
                                    <span className="w-[5px] h-[5px] rounded-full bg-text-secondary shrink-0 mt-[7px]" />
                                    {item}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {impactResult.patient_impacts?.length > 0 ? (
                            <div className="space-y-3">
                              <h4 className="text-[11px] font-semibold text-text-tertiary uppercase tracking-[0.06em]">Individual Patient Impact</h4>
                              {impactResult.patient_impacts.map((pt: any) => {
                                const isExpanded = expandedPatients.has(pt.patient_id)
                                const riskLabels: Record<string, string> = {
                                  verdict_flip: 'Verdict Flip', at_risk: 'At Risk', improved: 'Improved', no_impact: 'No Impact',
                                }
                                const riskDots: Record<string, string> = {
                                  verdict_flip: 'bg-[#1d1d1f]', at_risk: 'bg-text-secondary', improved: 'bg-text-quaternary', no_impact: 'bg-[#d2d2d7]',
                                }
                                const likelihoodDelta = pt.projected_likelihood - pt.current_likelihood
                                const statusChanged = pt.current_status !== pt.projected_status

                                return (
                                  <motion.div key={pt.patient_id} layout className="rounded-2xl bg-[#f5f5f7] overflow-hidden">
                                    <button
                                      onClick={() => {
                                        const next = new Set(expandedPatients)
                                        isExpanded ? next.delete(pt.patient_id) : next.add(pt.patient_id)
                                        setExpandedPatients(next)
                                      }}
                                      className="w-full flex items-center gap-4 p-4 text-left hover:bg-[#ededf0] transition-colors duration-200"
                                    >
                                      <div className="flex items-center justify-center w-9 h-9 rounded-full bg-[#e8e8ed] text-text-secondary text-[12px] font-semibold shrink-0">
                                        {(pt.patient_name || 'U')[0].toUpperCase()}
                                      </div>
                                      <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                          <span className="text-[13px] font-medium text-text-primary truncate">{pt.patient_name || pt.patient_id}</span>
                                          <span className="text-[11px] text-text-quaternary">{pt.case_id || pt.patient_id}</span>
                                        </div>
                                        <div className="flex items-center gap-3 mt-0.5">
                                          <span className="text-[11px] text-text-tertiary capitalize">{pt.current_status?.replace(/_/g, ' ')}</span>
                                          {statusChanged && (
                                            <>
                                              <ArrowRight className="w-[10px] h-[10px] text-text-quaternary" />
                                              <span className="text-[11px] font-medium capitalize text-text-primary">
                                                {pt.projected_status?.replace(/_/g, ' ')}
                                              </span>
                                            </>
                                          )}
                                        </div>
                                      </div>
                                      <div className="flex items-center gap-3 shrink-0">
                                        {likelihoodDelta !== 0 && (
                                          <div className={`flex items-center gap-1 text-[12px] font-medium text-text-secondary`}>
                                            {likelihoodDelta < 0 ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />}
                                            {likelihoodDelta > 0 ? '+' : ''}{(likelihoodDelta * 100).toFixed(0)}%
                                          </div>
                                        )}
                                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium bg-[#e8e8ed] text-text-secondary">
                                          <span className={`w-[5px] h-[5px] rounded-full ${riskDots[pt.risk_level] || riskDots.no_impact}`} />
                                          {riskLabels[pt.risk_level] || pt.risk_level}
                                        </span>
                                        <motion.div animate={{ rotate: isExpanded ? 90 : 0 }} transition={{ duration: 0.2 }}>
                                          <ChevronRight className="w-[14px] h-[14px] text-text-quaternary" />
                                        </motion.div>
                                      </div>
                                    </button>

                                    <AnimatePresence>
                                      {isExpanded && (
                                        <motion.div
                                          initial={{ height: 0, opacity: 0 }}
                                          animate={{ height: 'auto', opacity: 1 }}
                                          exit={{ height: 0, opacity: 0 }}
                                          transition={{ duration: 0.25 }}
                                          className="overflow-hidden"
                                        >
                                          <div className="px-4 pb-4 border-t border-[#e0e0e3] pt-4 space-y-4">
                                            <div className="grid grid-cols-2 gap-3">
                                              <div className="rounded-xl bg-white p-3">
                                                <span className="text-[10px] text-text-tertiary uppercase tracking-[0.06em] font-medium">Current Approval</span>
                                                <div className="flex items-center gap-2 mt-1">
                                                  <span className="text-[20px] font-semibold text-text-primary tracking-tight">{(pt.current_likelihood * 100).toFixed(0)}%</span>
                                                  <span className="text-[11px] text-text-tertiary capitalize">{pt.current_status?.replace(/_/g, ' ')}</span>
                                                </div>
                                              </div>
                                              <div className="rounded-xl bg-white p-3">
                                                <span className="text-[10px] text-text-tertiary uppercase tracking-[0.06em] font-medium">Projected Approval</span>
                                                <div className="flex items-center gap-2 mt-1">
                                                  <span className="text-[20px] font-semibold text-text-primary tracking-tight">{(pt.projected_likelihood * 100).toFixed(0)}%</span>
                                                  <span className="text-[11px] text-text-tertiary capitalize">{pt.projected_status?.replace(/_/g, ' ')}</span>
                                                </div>
                                              </div>
                                            </div>

                                            {pt.recommended_action && pt.recommended_action !== 'no action needed' && (
                                              <div className="rounded-xl bg-white p-3">
                                                <span className="text-[10px] text-text-secondary uppercase tracking-[0.06em] font-semibold">Recommended Action</span>
                                                <p className="text-[13px] text-text-primary mt-1 leading-relaxed">{pt.recommended_action}</p>
                                              </div>
                                            )}

                                            {pt.criteria_detail?.length > 0 && (
                                              <div>
                                                <span className="text-[10px] text-text-tertiary uppercase tracking-[0.06em] font-medium">Affected Criteria</span>
                                                <div className="mt-2 space-y-1.5">
                                                  {pt.criteria_detail.map((cd: any, i: number) => (
                                                    <div key={i} className="flex items-center gap-3 rounded-xl bg-white p-3">
                                                      <div className="w-6 h-6 rounded-md bg-[#f0f0f2] flex items-center justify-center">
                                                        {cd.change === 'verdict_flip' ? <TrendingDown className="w-3 h-3 text-text-secondary" /> :
                                                         cd.change === 'added' ? <Plus className="w-3 h-3 text-text-secondary" /> :
                                                         cd.change === 'removed' ? <Minus className="w-3 h-3 text-text-secondary" /> :
                                                         <RefreshCw className="w-3 h-3 text-text-secondary" />}
                                                      </div>
                                                      <div className="flex-1 min-w-0">
                                                        <span className="text-[12px] font-medium text-text-primary">{cd.criterion_name || cd.criterion_id}</span>
                                                        <div className="flex items-center gap-3 mt-0.5">
                                                          {cd.old_met !== null && cd.old_met !== undefined && (
                                                            <span className="text-[11px] text-text-tertiary">Was: {cd.old_met ? 'Met' : 'Not Met'}</span>
                                                          )}
                                                          {cd.new_met !== null && cd.new_met !== undefined && (
                                                            <span className="text-[11px] text-text-secondary font-medium">Now: {cd.new_met ? 'Met' : 'Not Met'}</span>
                                                          )}
                                                        </div>
                                                      </div>
                                                      <span className="text-[10px] px-2 py-0.5 rounded-md font-medium capitalize bg-[#f0f0f2] text-text-secondary">
                                                        {cd.change?.replace(/_/g, ' ')}
                                                      </span>
                                                    </div>
                                                  ))}
                                                </div>
                                              </div>
                                            )}
                                          </div>
                                        </motion.div>
                                      )}
                                    </AnimatePresence>
                                  </motion.div>
                                )
                              })}
                            </div>
                          ) : (
                            <div className="rounded-2xl bg-[#f5f5f7] p-8">
                              <div className="flex flex-col items-center justify-center py-8 gap-3">
                                <Users className="w-8 h-8 text-text-quaternary" />
                                <p className="text-text-secondary text-[13px]">No active BV/PA cases found for this policy</p>
                                <p className="text-text-quaternary text-[12px]">Add patient records to see impact analysis</p>
                              </div>
                            </div>
                          )}
                        </>
                      ) : null}
                    </motion.div>
                  )}

                  {/* ── Changes Tab ── */}
                  {activeTab === 'changes' && (
                    <motion.div
                      key="changes"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      transition={{ duration: 0.3, ease }}
                      className="space-y-2"
                    >
                      {changes.length === 0 ? (
                        <div className="rounded-2xl bg-[#f5f5f7] p-8">
                          <div className="flex flex-col items-center justify-center py-8 gap-3">
                            <CheckCircle2 className="w-8 h-8 text-text-quaternary" />
                            <p className="text-text-secondary text-[13px]">No criterion changes detected</p>
                          </div>
                        </div>
                      ) : (
                        changes.map((change: any, i: number) => {
                          const isExpanded = expandedChanges.has(i)
                          const changeType = (change.change_type || change.type || '').toLowerCase()
                          const addedVal = changeType === 'added' && change.new_value && typeof change.new_value === 'object' ? change.new_value : null
                          const removedVal = changeType === 'removed' && change.old_value && typeof change.old_value === 'object' ? change.old_value : null
                          const fieldChanges = change.field_changes || change.fields || change.details || []
                          const hasDetails = !!(addedVal || removedVal || fieldChanges.length > 0 || change.description || change.human_summary)
                          const toggleExpand = () => {
                            setExpandedChanges(prev => {
                              const next = new Set(prev)
                              if (next.has(i)) next.delete(i); else next.add(i)
                              return next
                            })
                          }
                          return (
                            <motion.div
                              key={i}
                              custom={i}
                              variants={fadeUp}
                              initial="hidden"
                              animate="visible"
                              className="rounded-xl bg-[#f5f5f7] overflow-hidden"
                            >
                              <button
                                onClick={hasDetails ? toggleExpand : undefined}
                                className={`w-full flex items-center gap-3 px-5 py-4 text-left ${hasDetails ? 'cursor-pointer hover:bg-[#ededf0] transition-colors' : 'cursor-default'}`}
                              >
                                <div className="flex items-center justify-center w-7 h-7 rounded-lg shrink-0 bg-[#e8e8ed]">
                                  {changeTypeIcon(change.change_type || change.type)}
                                </div>
                                <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
                                  <span className="text-[13px] font-medium text-text-primary">
                                    {change.criterion_name || change.criterion || change.name || `Change ${i + 1}`}
                                  </span>
                                  <span className="inline-flex items-center gap-1.5 text-[10px] px-2 py-[2px] rounded-md font-medium bg-[#e8e8ed] text-text-secondary">
                                    <span className={`w-[4px] h-[4px] rounded-full ${severityDot(change.severity)}`} />
                                    {severityLabel(change.severity)}
                                  </span>
                                  <span className="text-[11px] text-text-tertiary capitalize">
                                    {change.change_type || change.type || 'modified'}
                                  </span>
                                </div>
                                {hasDetails && (
                                  <motion.div animate={{ rotate: isExpanded ? 90 : 0 }} transition={{ duration: 0.2 }} className="shrink-0">
                                    <ChevronRight className="w-[14px] h-[14px] text-text-tertiary" />
                                  </motion.div>
                                )}
                              </button>

                              <AnimatePresence>
                                {isExpanded && (
                                  <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    transition={{ duration: 0.25, ease }}
                                    className="overflow-hidden"
                                  >
                                    <div className="px-5 pb-5 pt-0 ml-10 border-t border-[#e0e0e3]">
                                      {(change.description || change.human_summary) && (
                                        <p className="text-[12px] text-text-secondary mt-3 leading-relaxed">{change.description || change.human_summary}</p>
                                      )}

                                      {addedVal && (
                                        <div className="mt-3 space-y-1.5">
                                          <p className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.06em]">New Criterion Details</p>
                                          {[
                                            { label: 'Description', value: addedVal.description },
                                            { label: 'Policy Text', value: addedVal.policy_text },
                                            { label: 'Category', value: addedVal.category || addedVal.criterion_category },
                                            { label: 'Type', value: addedVal.criterion_type },
                                            { label: 'Required', value: addedVal.is_required != null ? (addedVal.is_required ? 'Yes' : 'No') : null },
                                            { label: 'Threshold', value: addedVal.threshold_value != null ? `${addedVal.comparison_operator || ''} ${addedVal.threshold_value}${addedVal.threshold_value_upper != null ? ` – ${addedVal.threshold_value_upper}` : ''} ${addedVal.threshold_unit || ''}`.trim() : null },
                                          ].filter(r => r.value).map((row, j) => (
                                            <div key={j} className="rounded-lg bg-white p-2.5 text-[12px]">
                                              <span className="text-text-tertiary font-medium">{row.label}: </span>
                                              <span className="text-text-primary">{row.value}</span>
                                            </div>
                                          ))}
                                        </div>
                                      )}

                                      {removedVal && (
                                        <div className="mt-3 space-y-1.5">
                                          <p className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.06em]">Removed Criterion Details</p>
                                          {[
                                            { label: 'Description', value: removedVal.description },
                                            { label: 'Policy Text', value: removedVal.policy_text },
                                            { label: 'Category', value: removedVal.category || removedVal.criterion_category },
                                          ].filter(r => r.value).map((row, j) => (
                                            <div key={j} className="rounded-lg bg-white p-2.5 text-[12px]">
                                              <span className="text-text-tertiary font-medium">{row.label}: </span>
                                              <span className="text-text-primary">{row.value}</span>
                                            </div>
                                          ))}
                                        </div>
                                      )}

                                      {fieldChanges.length > 0 && (
                                        <div className="mt-3 space-y-1.5">
                                          <p className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.06em]">What Changed</p>
                                          {fieldChanges.map((field: any, j: number) => (
                                            <div key={j} className="rounded-lg bg-white p-3 text-[12px] space-y-1.5">
                                              <span className="text-text-tertiary font-medium">{(field.field || field.field_name || field.name || `Field ${j + 1}`).replace(/_/g, ' ')}</span>
                                              <div className="flex flex-col gap-1 pl-2 border-l-2 border-[#e8e8ed]">
                                                {(field.old_value ?? field.old) != null && (
                                                  <div className="flex items-start gap-1.5">
                                                    <span className="text-text-tertiary font-medium shrink-0">Before:</span>
                                                    <span className="text-text-secondary">{String(field.old_value ?? field.old)}</span>
                                                  </div>
                                                )}
                                                {(field.new_value ?? field.new) != null && (
                                                  <div className="flex items-start gap-1.5">
                                                    <span className="text-text-secondary font-medium shrink-0">After:</span>
                                                    <span className="text-text-primary">{String(field.new_value ?? field.new)}</span>
                                                  </div>
                                                )}
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </motion.div>
                          )
                        })
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            )}
          </div>
        </motion.div>
      )}
      </>
      )}

      {/* ═══════════ CROSS-PAYER ANALYSIS MODE ═══════════ */}
      {activeMode === 'cross-payer' && (
        <motion.div variants={fadeIn} initial="hidden" animate="visible" className="space-y-6">
          {/* Medication selector */}
          <motion.div custom={2} variants={fadeUp} initial="hidden" animate="visible"
            className="rounded-2xl bg-[#f5f5f7] p-6 space-y-5"
          >
            <div>
              <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase mb-3">Select Medication</h3>
              {policiesLoading ? (
                <div className="flex gap-2">
                  {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-9 w-28" />)}
                </div>
              ) : uniqueMedications.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {uniqueMedications.map((med) => {
                    const drugInfo = getDrugInfo(med)
                    const isSelected = crossPayerMedication === med
                    return (
                      <button
                        key={med}
                        onClick={() => {
                          setCrossPayerMedication(isSelected ? '' : med)
                          setCrossPayerResult(null); setCrossPayerError(null)
                        }}
                        className={`flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] font-medium transition-all duration-200 ${
                          isSelected
                            ? 'bg-[#1d1d1f] text-white'
                            : 'bg-white text-text-secondary hover:bg-[#e8e8ed] hover:text-text-primary'
                        }`}
                      >
                        <Pill className="w-[13px] h-[13px]" />
                        {drugInfo.brandName}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <p className="text-[13px] text-text-tertiary">No medications found in the policy bank.</p>
              )}
            </div>

            <div className="flex items-center gap-3">
              <div className="flex-1 max-w-sm relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-[14px] h-[14px] text-text-tertiary" />
                <input
                  type="text"
                  placeholder="Or type a medication name..."
                  value={crossPayerMedication}
                  onChange={(e) => { setCrossPayerMedication(e.target.value); setCrossPayerResult(null); setCrossPayerError(null) }}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCrossPayerAnalysis() }}
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl bg-white text-[13px] text-text-primary placeholder:text-text-quaternary focus:outline-none focus:ring-2 focus:ring-[#1d1d1f]/10 transition-all duration-200"
                />
              </div>
              <button
                onClick={handleCrossPayerAnalysis}
                disabled={!crossPayerMedication.trim() || crossPayerLoading}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#1d1d1f] text-white text-[13px] font-medium hover:bg-[#333336] transition-colors duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {crossPayerLoading ? (
                  <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
                    <RefreshCw className="w-[14px] h-[14px]" />
                  </motion.div>
                ) : (
                  <>
                    <BarChart3 className="w-[14px] h-[14px]" />
                    Run Analysis
                  </>
                )}
              </button>
            </div>
          </motion.div>

          {/* Loading */}
          {crossPayerLoading && (
            <AnalysisProgress steps={CROSS_PAYER_STEPS} currentStep={crossPayerStep} />
          )}

          {/* Error */}
          {crossPayerError && !crossPayerLoading && (
            <motion.div variants={fadeIn} initial="hidden" animate="visible" className="rounded-2xl bg-[#f5f5f7] p-8">
              <div className="flex flex-col items-center justify-center py-8 gap-3">
                <div className="w-10 h-10 rounded-full bg-[#e8e8ed] flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-text-tertiary" />
                </div>
                <p className="text-text-secondary text-[13px]">{crossPayerError}</p>
                <button
                  onClick={handleCrossPayerAnalysis}
                  className="text-[12px] text-text-secondary hover:text-text-primary font-medium underline underline-offset-2 mt-1"
                >
                  Try again
                </button>
              </div>
            </motion.div>
          )}

          {/* Results */}
          {crossPayerResult && !crossPayerLoading && (() => {
            const payers = crossPayerResult.payers_compared || []
            return (
            <motion.div variants={fadeIn} initial="hidden" animate="visible" className="space-y-5">
              {/* Executive Summary */}
              {crossPayerResult.executive_summary && (
                <motion.div custom={3} variants={fadeUp} initial="hidden" animate="visible"
                  className="rounded-2xl bg-[#f5f5f7] p-6"
                >
                  <div className="flex items-center gap-2 mb-4">
                    <Sparkles className="w-[14px] h-[14px] text-text-secondary" />
                    <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase">Executive Summary</h3>
                  </div>
                  <p className="text-[15px] text-text-primary leading-[1.65] tracking-[-0.01em]">{crossPayerResult.executive_summary}</p>
                  {payers.length > 0 && (
                    <div className="flex items-center gap-2 mt-4 pt-4 border-t border-[#e0e0e3]">
                      <span className="text-[11px] text-text-tertiary">Payers compared:</span>
                      <div className="flex flex-wrap gap-1.5">
                        {payers.map((p) => (
                          <span key={p} className="text-[11px] px-2.5 py-1 rounded-lg bg-white text-text-secondary font-medium">
                            {getPayerInfo(p).abbreviation}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </motion.div>
              )}

              {/* Restrictiveness Ranking — Table */}
              {crossPayerResult.restrictiveness_ranking && crossPayerResult.restrictiveness_ranking.length > 0 && (
                <motion.div custom={4} variants={fadeUp} initial="hidden" animate="visible"
                  className="rounded-2xl bg-[#f5f5f7] p-6"
                >
                  <div className="flex items-center gap-2 mb-4">
                    <Hash className="w-[14px] h-[14px] text-text-secondary" />
                    <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase">Restrictiveness Ranking</h3>
                  </div>
                  <div className="rounded-xl bg-white overflow-hidden">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-[#f0f0f2]">
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 w-12">Rank</th>
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 w-28">Payer</th>
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5">Rationale</th>
                        </tr>
                      </thead>
                      <tbody>
                        {crossPayerResult.restrictiveness_ranking
                          .sort((a, b) => a.rank - b.rank)
                          .map((entry, ei) => (
                            <tr key={entry.payer} className={ei < crossPayerResult.restrictiveness_ranking!.length - 1 ? 'border-b border-[#f5f5f7]' : ''}>
                              <td className="px-4 py-3 align-top">
                                <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-[#f0f0f2] text-[12px] font-bold text-text-primary">
                                  {entry.rank}
                                </span>
                              </td>
                              <td className="px-4 py-3 align-top">
                                <span className="text-[13px] font-semibold text-text-primary">{getPayerInfo(entry.payer).abbreviation}</span>
                              </td>
                              <td className="px-4 py-3 align-top">
                                <p className="text-[12px] text-text-secondary leading-relaxed">{entry.rationale}</p>
                                {entry.key_criteria && entry.key_criteria.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-1.5">
                                    {entry.key_criteria.map((cid) => (
                                      <span key={cid} className="text-[10px] px-1.5 py-[2px] rounded bg-[#f0f0f2] text-text-quaternary font-mono">{cid}</span>
                                    ))}
                                  </div>
                                )}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </motion.div>
              )}

              {/* Criteria Comparison — Payers as columns */}
              {crossPayerResult.criteria_comparison && crossPayerResult.criteria_comparison.length > 0 && (
                <motion.div custom={5} variants={fadeUp} initial="hidden" animate="visible"
                  className="rounded-2xl bg-[#f5f5f7] p-6"
                >
                  <div className="flex items-center gap-2 mb-4">
                    <List className="w-[14px] h-[14px] text-text-secondary" />
                    <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase">Criteria Comparison</h3>
                  </div>
                  <div className="rounded-xl bg-white overflow-hidden overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-[#f0f0f2]">
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 w-40 min-w-[160px]">Dimension</th>
                          {payers.map((p) => (
                            <th key={p} className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 min-w-[180px]">
                              {getPayerInfo(p).abbreviation}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {crossPayerResult.criteria_comparison.map((group, gi) => {
                          const diffs = Array.isArray(group.differences) ? group.differences : []
                          // Build per-payer content for this dimension
                          const payerContent: Record<string, Array<{ text: string; criterionIds: string[] }>> = {}
                          for (const p of payers) payerContent[p.toLowerCase()] = []
                          for (const diff of diffs) {
                            const text = typeof diff === 'string' ? diff : (diff.detail || diff.description || diff.value || '')
                            const ids = typeof diff === 'string' ? [] : (diff.criterion_ids || [])
                            const affected: string[] = typeof diff === 'string' ? [] : (diff.payers_affected || (diff.payer ? [diff.payer] : []))
                            if (affected.length > 0) {
                              for (const ap of affected) {
                                const key = ap.toLowerCase()
                                if (payerContent[key]) payerContent[key].push({ text, criterionIds: ids })
                              }
                            } else {
                              // No specific payer — applies to all
                              for (const p of payers) payerContent[p.toLowerCase()].push({ text, criterionIds: ids })
                            }
                          }
                          return (
                            <tr key={gi} className={gi < crossPayerResult.criteria_comparison!.length - 1 ? 'border-b border-[#e8e8ed]' : ''}>
                              <td className="px-4 py-3 align-top">
                                <span className="text-[12px] font-semibold text-text-primary leading-snug">{group.dimension}</span>
                              </td>
                              {payers.map((p) => {
                                const entries = payerContent[p.toLowerCase()] || []
                                return (
                                  <td key={p} className="px-4 py-3 align-top">
                                    {entries.length > 0 ? (
                                      <div className="space-y-2">
                                        {entries.map((entry, ei) => (
                                          <div key={ei}>
                                            <p className="text-[12px] text-text-secondary leading-relaxed">{entry.text}</p>
                                            {entry.criterionIds.length > 0 && (
                                              <div className="flex flex-wrap gap-1 mt-1">
                                                {entry.criterionIds.map((cid) => (
                                                  <span key={cid} className="text-[10px] px-1.5 py-[2px] rounded bg-[#f0f0f2] text-text-quaternary font-mono">{cid}</span>
                                                ))}
                                              </div>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    ) : (
                                      <span className="text-[11px] text-text-quaternary">—</span>
                                    )}
                                  </td>
                                )
                              })}
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </motion.div>
              )}

              {/* Coverage Gaps — Cross-Payer Matrix */}
              {crossPayerResult.coverage_gaps && crossPayerResult.coverage_gaps.length > 0 && (
                <motion.div custom={6} variants={fadeUp} initial="hidden" animate="visible"
                  className="rounded-2xl bg-[#f5f5f7] p-6"
                >
                  <div className="flex items-center gap-2 mb-4">
                    <Shield className="w-[14px] h-[14px] text-text-secondary" />
                    <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase">Coverage Gaps</h3>
                  </div>
                  <div className="rounded-xl bg-white overflow-hidden">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-[#f0f0f2]">
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5">Indication</th>
                          {payers.map((p) => (
                            <th key={p} className="text-center text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-3 py-2.5 w-24">
                              {getPayerInfo(p).abbreviation}
                            </th>
                          ))}
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 w-28">Impact</th>
                        </tr>
                      </thead>
                      <tbody>
                        {crossPayerResult.coverage_gaps.map((gap, gi) => {
                          const coveredSet = new Set((gap.covered_by || []).map((p: string) => p.toLowerCase()))
                          const notCoveredSet = new Set((gap.not_covered_by || []).map((p: string) => p.toLowerCase()))
                          return (
                            <tr key={gi} className={gi < crossPayerResult.coverage_gaps!.length - 1 ? 'border-b border-[#f5f5f7]' : ''}>
                              <td className="px-4 py-3 align-middle">
                                <span className="text-[12px] font-medium text-text-primary">{gap.indication}</span>
                              </td>
                              {payers.map((p) => {
                                const pLower = p.toLowerCase()
                                const isCovered = coveredSet.has(pLower)
                                const isNotCovered = notCoveredSet.has(pLower)
                                return (
                                  <td key={p} className="px-3 py-3 text-center align-middle">
                                    {isCovered && <Check className="w-4 h-4 text-text-secondary mx-auto" />}
                                    {isNotCovered && <X className="w-4 h-4 text-text-quaternary mx-auto" />}
                                    {!isCovered && !isNotCovered && <span className="text-[11px] text-text-quaternary">—</span>}
                                  </td>
                                )
                              })}
                              <td className="px-4 py-3 align-middle">
                                {gap.impact && (
                                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#f0f0f2] text-text-secondary font-medium">{gap.impact}</span>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </motion.div>
              )}

              {/* Unique Requirements — Payers as columns */}
              {crossPayerResult.unique_requirements && crossPayerResult.unique_requirements.length > 0 && (() => {
                const impactDots: Record<string, string> = { high: 'bg-[#1d1d1f]', medium: 'bg-text-secondary', low: 'bg-text-quaternary' }
                // Group requirements by payer
                const byPayer: Record<string, Array<{ requirement: string; clinical_impact: string; criterion_id?: string }>> = {}
                for (const p of payers) byPayer[p.toLowerCase()] = []
                for (const req of crossPayerResult.unique_requirements) {
                  const key = req.payer.toLowerCase()
                  if (!byPayer[key]) byPayer[key] = []
                  byPayer[key].push(req)
                }
                const maxRows = Math.max(...payers.map(p => byPayer[p.toLowerCase()]?.length || 0), 1)
                return (
                  <motion.div custom={7} variants={fadeUp} initial="hidden" animate="visible"
                    className="rounded-2xl bg-[#f5f5f7] p-6"
                  >
                    <div className="flex items-center gap-2 mb-4">
                      <Zap className="w-[14px] h-[14px] text-text-secondary" />
                      <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase">Unique Requirements</h3>
                    </div>
                    <div className="rounded-xl bg-white overflow-hidden overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-[#f0f0f2]">
                            {payers.map((p) => (
                              <th key={p} className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 min-w-[180px]">
                                {getPayerInfo(p).abbreviation}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {Array.from({ length: maxRows }, (_, ri) => (
                            <tr key={ri} className={ri < maxRows - 1 ? 'border-b border-[#f5f5f7]' : ''}>
                              {payers.map((p) => {
                                const req = byPayer[p.toLowerCase()]?.[ri]
                                return (
                                  <td key={p} className="px-4 py-3 align-top">
                                    {req ? (
                                      <div>
                                        <p className="text-[12px] text-text-secondary leading-relaxed">{req.requirement}</p>
                                        <div className="flex items-center gap-2 mt-1.5">
                                          {req.clinical_impact && (
                                            <span className="inline-flex items-center gap-1.5 text-[10px] text-text-tertiary font-medium">
                                              <span className={`w-[4px] h-[4px] rounded-full ${impactDots[req.clinical_impact?.toLowerCase()] || impactDots.low}`} />
                                              {req.clinical_impact}
                                            </span>
                                          )}
                                          {req.criterion_id && (
                                            <span className="text-[10px] px-1.5 py-[2px] rounded bg-[#f0f0f2] text-text-quaternary font-mono">{req.criterion_id}</span>
                                          )}
                                        </div>
                                      </div>
                                    ) : (
                                      <span className="text-[11px] text-text-quaternary">—</span>
                                    )}
                                  </td>
                                )
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </motion.div>
                )
              })()}

              {/* Prescriber Requirements — Payers as columns */}
              {crossPayerResult.prescriber_requirements && crossPayerResult.prescriber_requirements.length > 0 && (() => {
                // Build per-payer lookup
                const byPayer: Record<string, { indications: string[]; specialists: string[] }> = {}
                for (const pr of crossPayerResult.prescriber_requirements) {
                  byPayer[pr.payer.toLowerCase()] = {
                    indications: pr.indications_requiring_specialist,
                    specialists: pr.specialist_types,
                  }
                }
                return (
                  <motion.div custom={7.5} variants={fadeUp} initial="hidden" animate="visible"
                    className="rounded-2xl bg-[#f5f5f7] p-6"
                  >
                    <div className="flex items-center gap-2 mb-4">
                      <Users className="w-[14px] h-[14px] text-text-secondary" />
                      <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase">Prescriber Specialty Requirements</h3>
                    </div>
                    <div className="rounded-xl bg-white overflow-hidden overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-[#f0f0f2]">
                            <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 w-40 min-w-[140px]"></th>
                            {payers.map((p) => (
                              <th key={p} className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 min-w-[180px]">
                                {getPayerInfo(p).abbreviation}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          <tr className="border-b border-[#f5f5f7]">
                            <td className="px-4 py-3 align-top">
                              <span className="text-[12px] font-semibold text-text-primary">Indications</span>
                            </td>
                            {payers.map((p) => {
                              const data = byPayer[p.toLowerCase()]
                              return (
                                <td key={p} className="px-4 py-3 align-top">
                                  {data && data.indications.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                      {data.indications.map((ind) => (
                                        <span key={ind} className="text-[11px] px-2 py-0.5 rounded-md bg-[#f0f0f2] text-text-secondary font-medium">{ind}</span>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-[11px] text-text-quaternary">—</span>
                                  )}
                                </td>
                              )
                            })}
                          </tr>
                          <tr>
                            <td className="px-4 py-3 align-top">
                              <span className="text-[12px] font-semibold text-text-primary">Specialist Types</span>
                            </td>
                            {payers.map((p) => {
                              const data = byPayer[p.toLowerCase()]
                              return (
                                <td key={p} className="px-4 py-3 align-top">
                                  {data && data.specialists.length > 0 ? (
                                    <p className="text-[12px] text-text-secondary leading-relaxed">{data.specialists.join(', ')}</p>
                                  ) : (
                                    <span className="text-[11px] text-text-quaternary">—</span>
                                  )}
                                </td>
                              )
                            })}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </motion.div>
                )
              })()}

              {/* Recommended Actions */}
              {crossPayerResult.recommended_actions && crossPayerResult.recommended_actions.length > 0 && (
                <motion.div custom={8} variants={fadeUp} initial="hidden" animate="visible"
                  className="rounded-2xl bg-[#f5f5f7] p-6"
                >
                  <div className="flex items-center gap-2 mb-4">
                    <CheckCircle2 className="w-[14px] h-[14px] text-text-secondary" />
                    <h3 className="text-[11px] font-semibold text-text-tertiary tracking-[0.06em] uppercase">Recommended Actions</h3>
                  </div>
                  <div className="rounded-xl bg-white overflow-hidden">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-[#f0f0f2]">
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 w-8">#</th>
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5">Action</th>
                          <th className="text-left text-[10px] font-semibold text-text-quaternary tracking-[0.06em] uppercase px-4 py-2.5 w-28">Payer</th>
                        </tr>
                      </thead>
                      <tbody>
                        {crossPayerResult.recommended_actions.map((action, ai) => {
                          const isObj = typeof action === 'object' && action !== null
                          const text = isObj ? action.action : String(action)
                          const payer = isObj ? action.payer : undefined
                          const rationale = isObj ? action.rationale : undefined
                          return (
                            <tr key={ai} className={ai < crossPayerResult.recommended_actions!.length - 1 ? 'border-b border-[#f5f5f7]' : ''}>
                              <td className="px-4 py-3 align-top">
                                <span className="text-[11px] text-text-quaternary font-medium">{ai + 1}</span>
                              </td>
                              <td className="px-4 py-3 align-top">
                                <p className="text-[12px] text-text-primary leading-relaxed">{text}</p>
                                {rationale && <p className="text-[11px] text-text-tertiary mt-1 leading-relaxed">{rationale}</p>}
                              </td>
                              <td className="px-4 py-3 align-top">
                                {payer && (
                                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-[#f0f0f2] text-text-secondary font-medium">{getPayerInfo(payer).abbreviation}</span>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </motion.div>
              )}

              {/* Data Quality Notes */}
              {crossPayerResult.data_quality_notes && crossPayerResult.data_quality_notes.length > 0 && (
                <motion.div custom={8.5} variants={fadeUp} initial="hidden" animate="visible"
                  className="rounded-2xl bg-[#f5f5f7] p-5"
                >
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="w-[13px] h-[13px] text-text-quaternary" />
                    <h3 className="text-[11px] font-medium text-text-quaternary tracking-[0.06em] uppercase">Data Quality Notes</h3>
                  </div>
                  <div className="space-y-1.5">
                    {crossPayerResult.data_quality_notes.map((note, ni) => (
                      <p key={ni} className="text-[12px] text-text-tertiary leading-relaxed pl-[22px] relative before:content-[''] before:absolute before:left-[8px] before:top-[7px] before:w-[4px] before:h-[4px] before:rounded-full before:bg-[#d2d2d7]">{note}</p>
                    ))}
                  </div>
                </motion.div>
              )}

              {/* Confidence */}
              {crossPayerResult.confidence != null && (
                <div className="flex items-center justify-end gap-2">
                  <span className="text-[11px] text-text-quaternary">Analysis confidence:</span>
                  <span className="text-[11px] font-semibold text-text-tertiary">{(crossPayerResult.confidence * 100).toFixed(0)}%</span>
                </div>
              )}

              {crossPayerResult.error && (
                <div className="rounded-2xl bg-[#f5f5f7] p-4">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-[14px] h-[14px] text-text-tertiary" />
                    <p className="text-[13px] text-text-secondary">{crossPayerResult.error}</p>
                  </div>
                </div>
              )}
            </motion.div>
            )
          })()}

          {/* Empty state */}
          {!crossPayerResult && !crossPayerLoading && !crossPayerError && (
            <motion.div variants={fadeIn} initial="hidden" animate="visible"
              className="flex flex-col items-center justify-center py-24 gap-4"
            >
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-[#f5f5f7]">
                <BarChart3 className="w-7 h-7 text-text-quaternary" />
              </div>
              <div className="text-center">
                <p className="text-text-secondary text-[14px] font-medium">Select a medication and run analysis</p>
                <p className="text-text-quaternary text-[12px] mt-1">Compare coverage policies across all payers in your policy bank</p>
              </div>
            </motion.div>
          )}
        </motion.div>
      )}
    </div>
  )
}
