import { useState, useEffect, useCallback } from 'react'
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
  CircleDot,
} from 'lucide-react'
import { api, type PolicyBankItem, type PolicyVersion, type DiffSummaryResponse } from '../lib/api'
import { getDrugInfo, getPayerInfo } from '../lib/drugInfo'

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] as const },
  }),
}

const fadeIn = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] as const } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
}

function ShimmerBlock({ className }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl bg-surface-secondary ${className}`}>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.5s_infinite] bg-gradient-to-r from-transparent via-black/[0.04] to-transparent" />
    </div>
  )
}

function Spinner({ size = 20 }: { size?: number }) {
  return (
    <motion.div
      animate={{ rotate: 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
    >
      <RefreshCw style={{ width: size, height: size }} className="text-accent-blue" />
    </motion.div>
  )
}

type DiffTab = 'summary' | 'changes' | 'impact'

function SegmentedControl({ tabs, active, onChange }: {
  tabs: { key: DiffTab; label: string; icon: typeof Sparkles }[]
  active: DiffTab
  onChange: (tab: DiffTab) => void
}) {
  return (
    <div className="flex items-center bg-surface-tertiary rounded-xl p-1 gap-0.5">
      {tabs.map((tab) => {
        const Icon = tab.icon
        const isActive = active === tab.key
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 ${
              isActive ? 'text-text-primary' : 'text-text-tertiary hover:text-text-secondary'
            }`}
          >
            {isActive && (
              <motion.div
                layoutId="segment-bg"
                className="absolute inset-0 bg-surface-elevated rounded-lg"
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
            <span className="relative z-10 flex items-center gap-2">
              <Icon className="w-4 h-4" />
              {tab.label}
            </span>
          </button>
        )
      })}
    </div>
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

function severityColor(severity: string) {
  switch (severity?.toLowerCase()) {
    case 'breaking': return 'bg-accent-red/10 text-accent-red border-accent-red/20'
    case 'material': return 'bg-accent-amber/10 text-accent-amber border-accent-amber/20'
    case 'minor': return 'bg-surface-tertiary text-text-secondary border-border-primary'
    case 'cosmetic': return 'bg-surface-tertiary/50 text-text-tertiary border-border-primary'
    default: return 'bg-surface-tertiary text-text-secondary border-border-primary'
  }
}

function severityLabel(severity: string) {
  switch (severity?.toLowerCase()) {
    case 'breaking': return 'High Impact'
    case 'material': return 'Moderate Impact'
    case 'minor': return 'Low Impact'
    case 'cosmetic': return 'Cosmetic'
    default: return 'Info'
  }
}

function changeTypeIcon(type: string) {
  switch (type?.toLowerCase()) {
    case 'added': return <Plus className="w-3.5 h-3.5 text-accent-green" />
    case 'removed': return <Minus className="w-3.5 h-3.5 text-accent-red" />
    case 'modified': return <RefreshCw className="w-3.5 h-3.5 text-accent-amber" />
    default: return <Info className="w-3.5 h-3.5 text-text-tertiary" />
  }
}

function changeTypeBg(type: string) {
  switch (type?.toLowerCase()) {
    case 'added': return 'bg-accent-green/10'
    case 'removed': return 'bg-accent-red/10'
    case 'modified': return 'bg-accent-amber/10'
    default: return 'bg-surface-tertiary'
  }
}

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
  const [activeTab, setActiveTab] = useState<DiffTab>('summary')
  const [expandedChanges, setExpandedChanges] = useState<Set<number>>(new Set())

  const [impactResult, setImpactResult] = useState<any>(null)
  const [impactLoading, setImpactLoading] = useState(false)
  const [impactError, setImpactError] = useState<string | null>(null)
  const [expandedPatients, setExpandedPatients] = useState<Set<string>>(new Set())

  useEffect(() => {
    api.getPolicyBank()
      .then(setPolicies)
      .catch(() => setPolicies([]))
      .finally(() => setPoliciesLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedPolicy) {
      setVersions([])
      setSelectedOld(null)
      setSelectedNew(null)
      setDiffResult(null)
      return
    }
    setVersionsLoading(true)
    setSelectedOld(null)
    setSelectedNew(null)
    setDiffResult(null)
    api.getPolicyVersions(selectedPolicy.payer, selectedPolicy.medication)
      .then(setVersions)
      .catch(() => setVersions([]))
      .finally(() => setVersionsLoading(false))
  }, [selectedPolicy])

  const handleVersionClick = useCallback((version: string) => {
    setDiffResult(null)
    if (selectedOld === version) {
      setSelectedOld(null)
    } else if (selectedNew === version) {
      setSelectedNew(null)
    } else if (!selectedOld) {
      setSelectedOld(version)
    } else if (!selectedNew) {
      if (version < selectedOld) {
        setSelectedNew(selectedOld)
        setSelectedOld(version)
      } else {
        setSelectedNew(version)
      }
    } else {
      setSelectedOld(version)
      setSelectedNew(null)
    }
  }, [selectedOld, selectedNew])

  const handleCompare = useCallback(async () => {
    if (!selectedPolicy || !selectedOld || !selectedNew) return
    setDiffLoading(true)
    setActiveTab('summary')
    setExpandedChanges(new Set())
    setImpactResult(null)
    setImpactError(null)
    setExpandedPatients(new Set())
    try {
      const result = await api.getDiffSummary(
        selectedPolicy.payer,
        selectedPolicy.medication,
        selectedOld,
        selectedNew
      )
      setDiffResult(result)
    } catch {
      setDiffResult(null)
    } finally {
      setDiffLoading(false)
    }
  }, [selectedPolicy, selectedOld, selectedNew])

  const fetchImpact = useCallback(async () => {
    if (!selectedPolicy || !selectedOld || !selectedNew) return
    if (impactResult || impactLoading) return
    setImpactLoading(true)
    setImpactError(null)
    try {
      const result = await api.getImpact(
        selectedPolicy.payer,
        selectedPolicy.medication,
        selectedOld,
        selectedNew
      )
      setImpactResult(result)
    } catch (err: any) {
      setImpactError(err?.message || 'Failed to load impact analysis')
    } finally {
      setImpactLoading(false)
    }
  }, [selectedPolicy, selectedOld, selectedNew, impactResult, impactLoading])

  useEffect(() => {
    if (activeTab === 'impact' && !impactResult && !impactLoading && !impactError) {
      fetchImpact()
    }
  }, [activeTab, fetchImpact, impactResult, impactLoading, impactError])

  const diffData = diffResult?.diff
  const rawChanges = diffData?.changes || diffData?.criterion_changes || []
  const changes: any[] = (() => {
    let all: any[] = []
    if (Array.isArray(rawChanges)) {
      all = rawChanges
    } else if (typeof rawChanges === 'object' && rawChanges !== null) {
      all = [
        ...(rawChanges.criteria || []),
        ...(rawChanges.indications || []),
        ...(rawChanges.step_therapy || []),
        ...(rawChanges.exclusions || []),
      ]
    }
    const seen = new Set<string>()
    return all.filter(c => {
      const id = c.criterion_id || c.criterion_name || c.indication_id || c.name || JSON.stringify(c)
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
  })()

  return (
    <div className="p-10 max-w-[1400px] space-y-8">
      <style>{`
        @keyframes shimmer {
          100% { transform: translateX(200%); }
        }
      `}</style>

      <motion.div custom={0} variants={fadeUp} initial="hidden" animate="visible">
        <h1 className="text-3xl font-semibold text-text-primary tracking-tight">Policy Intelligence</h1>
        <p className="text-text-tertiary mt-1">Version tracking and change analysis</p>
      </motion.div>

      <motion.div custom={1} variants={fadeUp} initial="hidden" animate="visible">
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-3 px-5 py-3 rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl hover:bg-surface-hover/60 transition-colors duration-200 w-full max-w-md"
          >
            <Search className="w-4 h-4 text-text-tertiary" />
            <span className={`flex-1 text-left text-sm ${selectedPolicy ? 'text-text-primary' : 'text-text-tertiary'}`}>
              {selectedPolicy
                ? `${getPayerInfo(selectedPolicy.payer).abbreviation} · ${getDrugInfo(selectedPolicy.medication).brandName}`
                : 'Select a policy to analyze...'}
            </span>
            <ChevronDown className={`w-4 h-4 text-text-tertiary transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          <AnimatePresence>
            {dropdownOpen && (
              <motion.div
                initial={{ opacity: 0, y: -8, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.98 }}
                transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] as const }}
                className="absolute z-50 mt-2 w-full max-w-md rounded-2xl border border-border-primary bg-surface-elevated/95 backdrop-blur-2xl shadow-2xl overflow-hidden"
              >
                {policiesLoading ? (
                  <div className="p-4 space-y-2">
                    <ShimmerBlock className="h-10" />
                    <ShimmerBlock className="h-10" />
                    <ShimmerBlock className="h-10" />
                  </div>
                ) : policies.length === 0 ? (
                  <div className="p-6 text-center text-text-tertiary text-sm">No policies found</div>
                ) : (
                  <div className="max-h-64 overflow-y-auto py-1">
                    {policies.map((p) => (
                      <button
                        key={`${p.payer}-${p.medication}`}
                        onClick={() => {
                          setSelectedPolicy(p)
                          setDropdownOpen(false)
                        }}
                        className={`w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-surface-hover/60 transition-colors duration-150 ${
                          selectedPolicy?.payer === p.payer && selectedPolicy?.medication === p.medication
                            ? 'bg-accent-blue/5'
                            : ''
                        }`}
                      >
                        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-surface-tertiary shrink-0">
                          <FileText className="w-4 h-4 text-text-tertiary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-text-primary truncate">{getPayerInfo(p.payer).abbreviation}</p>
                          <p className="text-xs text-text-tertiary truncate">{getDrugInfo(p.medication).brandName} · v{p.latest_version} · {p.version_count} versions</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      {!selectedPolicy ? (
        <motion.div
          variants={fadeIn}
          initial="hidden"
          animate="visible"
          className="flex flex-col items-center justify-center py-32 gap-4"
        >
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-surface-secondary border border-border-primary">
            <GitCompareArrows className="w-8 h-8 text-text-quaternary" />
          </div>
          <p className="text-text-tertiary text-sm">Select a policy to begin analysis</p>
        </motion.div>
      ) : (
        <motion.div
          variants={fadeIn}
          initial="hidden"
          animate="visible"
          className="flex gap-6"
        >
          <div className="w-[280px] shrink-0">
            <motion.div
              custom={2}
              variants={fadeUp}
              initial="hidden"
              animate="visible"
              className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-6"
            >
              <h3 className="text-xs font-medium text-text-secondary tracking-wide uppercase mb-5">Version Timeline</h3>

              {versionsLoading ? (
                <div className="space-y-4">
                  {[...Array(3)].map((_, i) => (
                    <div key={i} className="flex gap-3">
                      <ShimmerBlock className="w-6 h-6 rounded-full shrink-0" />
                      <div className="flex-1 space-y-2">
                        <ShimmerBlock className="h-4 w-20" />
                        <ShimmerBlock className="h-3 w-32" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : versions.length < 2 ? (
                <div className="flex flex-col items-center py-8 gap-3">
                  <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-surface-tertiary">
                    <Upload className="w-5 h-5 text-text-quaternary" />
                  </div>
                  <p className="text-text-tertiary text-xs text-center leading-relaxed">
                    {versions.length === 0
                      ? 'No versions found'
                      : 'Upload another version to enable comparison'}
                  </p>
                </div>
              ) : (
                <div className="relative">
                  <div className="absolute left-[11px] top-3 bottom-3 w-px bg-border-primary" />

                  <div className="space-y-1">
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
                            isSelected
                              ? 'bg-accent-blue/5'
                              : 'hover:bg-surface-hover/40'
                          }`}
                        >
                          <div className={`relative z-10 mt-0.5 w-[22px] h-[22px] rounded-full border-2 flex items-center justify-center shrink-0 transition-all duration-200 ${
                            isSelected
                              ? 'border-accent-blue bg-accent-blue'
                              : 'border-border-primary bg-surface-tertiary group-hover:border-text-quaternary'
                          }`}>
                            {isSelected && (
                              <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                className="w-2 h-2 rounded-full bg-white"
                              />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={`text-sm font-medium ${isSelected ? 'text-accent-blue' : 'text-text-primary'}`}>
                                v{v.version}
                              </span>
                              {isOld && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-blue/10 text-accent-blue font-medium">OLD</span>
                              )}
                              {isNew && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-blue/10 text-accent-blue font-medium">NEW</span>
                              )}
                            </div>
                            <p className="text-xs text-text-tertiary mt-0.5 flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {formatDate(v.cached_at)}
                            </p>
                            {v.source_filename && (
                              <p className="text-xs text-text-quaternary mt-0.5 truncate">{v.source_filename}</p>
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
                  className="mt-5 pt-5 border-t border-border-primary"
                >
                  <button
                    onClick={handleCompare}
                    disabled={diffLoading}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue-hover transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {diffLoading ? (
                      <Spinner size={16} />
                    ) : (
                      <>
                        <GitCompareArrows className="w-4 h-4" />
                        Compare Versions
                      </>
                    )}
                  </button>
                  <p className="text-xs text-text-quaternary text-center mt-2">
                    v{selectedOld} <ArrowRight className="w-3 h-3 inline" /> v{selectedNew}
                  </p>
                </motion.div>
              )}
            </motion.div>
          </div>

          <div className="flex-1 min-w-0">
            {diffLoading ? (
              <motion.div
                variants={fadeIn}
                initial="hidden"
                animate="visible"
                className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8"
              >
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <Spinner size={28} />
                  <div className="text-center">
                    <p className="text-text-secondary text-sm font-medium">Analyzing changes...</p>
                    <p className="text-text-quaternary text-xs mt-1">This may take a moment</p>
                  </div>
                </div>
              </motion.div>
            ) : !diffResult ? (
              <motion.div
                variants={fadeIn}
                initial="hidden"
                animate="visible"
                className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8"
              >
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-surface-tertiary border border-border-primary">
                    <GitCompareArrows className="w-7 h-7 text-text-quaternary" />
                  </div>
                  <div className="text-center">
                    <p className="text-text-secondary text-sm font-medium">
                      {selectedOld && selectedNew
                        ? 'Ready to compare'
                        : 'Select two versions to compare'}
                    </p>
                    <p className="text-text-quaternary text-xs mt-1">
                      {selectedOld && selectedNew
                        ? 'Click "Compare Versions" to analyze differences'
                        : 'Click on version nodes in the timeline'}
                    </p>
                  </div>
                </div>
              </motion.div>
            ) : (
              <motion.div
                variants={fadeIn}
                initial="hidden"
                animate="visible"
                className="space-y-5"
              >
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
                  <span className="text-xs text-text-quaternary">
                    v{selectedOld} → v{selectedNew}
                  </span>
                </div>

                <AnimatePresence mode="wait">
                  {activeTab === 'summary' && (
                    <motion.div
                      key="summary"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -12 }}
                      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] as const }}
                      className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8"
                    >
                      {(() => {
                        const summary = diffResult.summary
                        const s = typeof summary === 'string'
                          ? { executive_summary: summary } as Record<string, any>
                          : (typeof summary === 'object' && summary ? summary : {}) as Record<string, any>

                        const exec = typeof s.executive_summary === 'string' ? s.executive_summary : (s.executive_summary ? String(s.executive_summary) : '')
                        const sections = [
                          { key: 'breaking_changes_summary', label: 'High Impact', dot: 'bg-[#d70015]', text: 'text-[#d70015]' },
                          { key: 'material_changes_summary', label: 'Medium Impact', dot: 'bg-[#b25000]', text: 'text-[#b25000]' },
                          { key: 'minor_changes_summary', label: 'Low Impact', dot: 'bg-[#86868b]', text: 'text-[#86868b]' },
                        ]
                        const actions = s.recommended_actions || null

                        const splitBullets = (raw: any): string[] => {
                          if (!raw) return []
                          if (Array.isArray(raw)) return raw.map(r => String(r)).filter(b => b.length > 5)
                          const text = String(raw)
                          if (!text) return []
                          const byNewline = text.split(/\n/).map(b => b.replace(/^[-•*]\s*/, '').trim()).filter(b => b.length > 5)
                          if (byNewline.length > 1) return byNewline
                          return text.split(/[.,;](?=\s[A-Z])/)
                            .map(b => b.replace(/^[.,;]\s*/, '').trim())
                            .filter(b => b.length > 10)
                        }

                        return (
                          <div className="space-y-6">
                            {exec && (
                              <p className="text-[15px] text-[#1d1d1f] leading-[1.6] font-normal">{exec}</p>
                            )}

                            {sections.some(sec => s[sec.key]) && (
                              <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white overflow-hidden">
                                {sections.map((sec, si) => {
                                  const content = s[sec.key]
                                  if (!content) return null
                                  const items = splitBullets(content)
                                  return (
                                    <div key={sec.key}>
                                      {si > 0 && s[sections[si - 1]?.key] && (
                                        <div className="mx-4 border-t border-[rgba(0,0,0,0.06)]" />
                                      )}
                                      <div className="px-5 py-4">
                                        <div className="flex items-center gap-2 mb-3">
                                          <span className={`w-2 h-2 rounded-full ${sec.dot}`} />
                                          <span className={`text-[11px] font-semibold uppercase tracking-[0.06em] ${sec.text}`}>{sec.label}</span>
                                        </div>
                                        <div className="space-y-2.5 pl-4">
                                          {items.map((item, ii) => (
                                            <p key={ii} className="text-[13px] text-[#1d1d1f] leading-[1.55] relative pl-3.5 before:content-[''] before:absolute before:left-0 before:top-[7px] before:w-[5px] before:h-[5px] before:rounded-full before:bg-[rgba(0,0,0,0.15)]">
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
                              <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-[#f5f5f7] px-5 py-4">
                                <div className="flex items-center gap-2 mb-3">
                                  <CheckCircle2 className="w-3.5 h-3.5 text-[#248a3d]" />
                                  <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[#248a3d]">Recommended Actions</span>
                                </div>
                                <div className="space-y-2.5 pl-4">
                                  {splitBullets(actions).map((item, ii) => (
                                    <p key={ii} className="text-[13px] text-[#1d1d1f] leading-[1.55] relative pl-3.5 before:content-[''] before:absolute before:left-0 before:top-[7px] before:w-[5px] before:h-[5px] before:rounded-full before:bg-[rgba(0,0,0,0.15)]">
                                      {item}
                                    </p>
                                  ))}
                                </div>
                              </div>
                            )}

                            {!exec && !sections.some(sec => s[sec.key]) && !actions && (
                              <p className="text-[#86868b] text-sm">No summary available for this comparison.</p>
                            )}
                          </div>
                        )
                      })()}
                    </motion.div>
                  )}

                  {activeTab === 'impact' && (
                    <motion.div
                      key="impact"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -12 }}
                      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] as const }}
                      className="space-y-5"
                    >
                      {impactLoading ? (
                        <div className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8">
                          <div className="flex flex-col items-center justify-center py-16 gap-4">
                            <Spinner size={28} />
                            <div className="text-center">
                              <p className="text-text-secondary text-sm font-medium">Analyzing patient impact...</p>
                              <p className="text-text-quaternary text-xs mt-1">Evaluating BV/PA cases against policy changes</p>
                            </div>
                          </div>
                        </div>
                      ) : impactError ? (
                        <div className="rounded-2xl border border-accent-red/20 bg-accent-red/5 p-8">
                          <div className="flex flex-col items-center justify-center py-8 gap-3">
                            <AlertTriangle className="w-10 h-10 text-accent-red" />
                            <p className="text-text-secondary text-sm">{impactError}</p>
                            <button
                              onClick={() => { setImpactResult(null); setImpactError(null); fetchImpact(); }}
                              className="text-xs text-accent-blue hover:underline mt-2"
                            >
                              Retry Analysis
                            </button>
                          </div>
                        </div>
                      ) : impactResult ? (
                        <>
                          <div className="grid grid-cols-4 gap-3">
                            {[
                              { label: 'Active Cases', value: impactResult.total_active_cases, icon: Users, color: 'text-accent-blue', bg: 'bg-accent-blue/8' },
                              { label: 'Impacted', value: impactResult.impacted_cases, icon: AlertTriangle, color: 'text-accent-amber', bg: 'bg-accent-amber/8' },
                              { label: 'Verdict Flips', value: impactResult.verdict_flips, icon: TrendingDown, color: 'text-accent-red', bg: 'bg-accent-red/8' },
                              { label: 'At Risk', value: impactResult.at_risk_cases, icon: Shield, color: 'text-accent-purple', bg: 'bg-accent-purple/8' },
                            ].map((stat) => (
                              <div key={stat.label} className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-4">
                                <div className="flex items-center gap-2 mb-2">
                                  <div className={`flex items-center justify-center w-7 h-7 rounded-lg ${stat.bg}`}>
                                    <stat.icon className={`w-3.5 h-3.5 ${stat.color}`} />
                                  </div>
                                  <span className="text-xs text-text-tertiary">{stat.label}</span>
                                </div>
                                <span className="text-2xl font-semibold text-text-primary">{stat.value}</span>
                              </div>
                            ))}
                          </div>

                          {impactResult.action_items?.length > 0 && (
                            <div className="rounded-2xl border border-accent-amber/20 bg-accent-amber/5 p-5">
                              <h4 className="text-xs font-medium text-accent-amber uppercase tracking-wide mb-3">Action Items</h4>
                              <ul className="space-y-2">
                                {impactResult.action_items.map((item: string, i: number) => (
                                  <li key={i} className="flex items-start gap-2 text-sm text-text-primary">
                                    <CircleDot className="w-3.5 h-3.5 text-accent-amber shrink-0 mt-0.5" />
                                    {item}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {impactResult.patient_impacts?.length > 0 ? (
                            <div className="space-y-3">
                              <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide">Individual Patient Impact</h4>
                              {impactResult.patient_impacts.map((pt: any) => {
                                const isExpanded = expandedPatients.has(pt.patient_id)
                                const riskColors: Record<string, { badge: string; dot: string }> = {
                                  verdict_flip: { badge: 'bg-accent-red/10 text-accent-red border-accent-red/20', dot: 'bg-accent-red' },
                                  at_risk: { badge: 'bg-accent-amber/10 text-accent-amber border-accent-amber/20', dot: 'bg-accent-amber' },
                                  improved: { badge: 'bg-accent-green/10 text-accent-green border-accent-green/20', dot: 'bg-accent-green' },
                                  no_impact: { badge: 'bg-surface-tertiary text-text-tertiary border-border-primary', dot: 'bg-text-quaternary' },
                                }
                                const rc = riskColors[pt.risk_level] || riskColors.no_impact
                                const riskLabels: Record<string, string> = {
                                  verdict_flip: 'Verdict Flip',
                                  at_risk: 'At Risk',
                                  improved: 'Improved',
                                  no_impact: 'No Impact',
                                }

                                const likelihoodDelta = pt.projected_likelihood - pt.current_likelihood
                                const statusChanged = pt.current_status !== pt.projected_status

                                return (
                                  <motion.div
                                    key={pt.patient_id}
                                    layout
                                    className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl overflow-hidden"
                                  >
                                    <button
                                      onClick={() => {
                                        const next = new Set(expandedPatients)
                                        isExpanded ? next.delete(pt.patient_id) : next.add(pt.patient_id)
                                        setExpandedPatients(next)
                                      }}
                                      className="w-full flex items-center gap-4 p-4 text-left hover:bg-surface-hover/30 transition-colors duration-200"
                                    >
                                      <div className="flex items-center justify-center w-9 h-9 rounded-full bg-surface-tertiary text-text-secondary text-xs font-semibold shrink-0">
                                        {(pt.patient_name || 'U')[0].toUpperCase()}
                                      </div>
                                      <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                          <span className="text-sm font-medium text-text-primary truncate">{pt.patient_name || pt.patient_id}</span>
                                          <span className="text-xs text-text-quaternary">{pt.case_id || pt.patient_id}</span>
                                        </div>
                                        <div className="flex items-center gap-3 mt-1">
                                          <span className="text-xs text-text-tertiary capitalize">{pt.current_status?.replace(/_/g, ' ')}</span>
                                          {statusChanged && (
                                            <>
                                              <ArrowRight className="w-3 h-3 text-text-quaternary" />
                                              <span className={`text-xs font-medium capitalize ${pt.projected_status?.includes('not') ? 'text-accent-red' : 'text-accent-green'}`}>
                                                {pt.projected_status?.replace(/_/g, ' ')}
                                              </span>
                                            </>
                                          )}
                                        </div>
                                      </div>
                                      <div className="flex items-center gap-3 shrink-0">
                                        {likelihoodDelta !== 0 && (
                                          <div className={`flex items-center gap-1 text-xs font-medium ${likelihoodDelta < 0 ? 'text-accent-red' : 'text-accent-green'}`}>
                                            {likelihoodDelta < 0 ? <TrendingDown className="w-3.5 h-3.5" /> : <TrendingUp className="w-3.5 h-3.5" />}
                                            {likelihoodDelta > 0 ? '+' : ''}{(likelihoodDelta * 100).toFixed(0)}%
                                          </div>
                                        )}
                                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border ${rc.badge}`}>
                                          <span className={`w-1.5 h-1.5 rounded-full ${rc.dot}`} />
                                          {riskLabels[pt.risk_level] || pt.risk_level}
                                        </span>
                                        <motion.div
                                          animate={{ rotate: isExpanded ? 90 : 0 }}
                                          transition={{ duration: 0.2 }}
                                        >
                                          <ChevronRight className="w-4 h-4 text-text-quaternary" />
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
                                          <div className="px-4 pb-4 border-t border-border-secondary pt-4 space-y-4">
                                            <div className="grid grid-cols-2 gap-4">
                                              <div className="rounded-xl bg-surface-tertiary/50 p-3">
                                                <span className="text-[11px] text-text-tertiary uppercase tracking-wide">Current Approval</span>
                                                <div className="flex items-center gap-2 mt-1">
                                                  <span className="text-lg font-semibold text-text-primary">{(pt.current_likelihood * 100).toFixed(0)}%</span>
                                                  <span className="text-xs text-text-secondary capitalize">{pt.current_status?.replace(/_/g, ' ')}</span>
                                                </div>
                                              </div>
                                              <div className="rounded-xl bg-surface-tertiary/50 p-3">
                                                <span className="text-[11px] text-text-tertiary uppercase tracking-wide">Projected Approval</span>
                                                <div className="flex items-center gap-2 mt-1">
                                                  <span className={`text-lg font-semibold ${likelihoodDelta < 0 ? 'text-accent-red' : likelihoodDelta > 0 ? 'text-accent-green' : 'text-text-primary'}`}>
                                                    {(pt.projected_likelihood * 100).toFixed(0)}%
                                                  </span>
                                                  <span className="text-xs text-text-secondary capitalize">{pt.projected_status?.replace(/_/g, ' ')}</span>
                                                </div>
                                              </div>
                                            </div>

                                            {pt.recommended_action && pt.recommended_action !== 'no action needed' && (
                                              <div className="rounded-xl bg-accent-blue/5 border border-accent-blue/15 p-3">
                                                <span className="text-[11px] text-accent-blue uppercase tracking-wide font-medium">Recommended Action</span>
                                                <p className="text-sm text-text-primary mt-1">{pt.recommended_action}</p>
                                              </div>
                                            )}

                                            {pt.criteria_detail?.length > 0 && (
                                              <div>
                                                <span className="text-[11px] text-text-tertiary uppercase tracking-wide">Affected Criteria</span>
                                                <div className="mt-2 space-y-2">
                                                  {pt.criteria_detail.map((cd: any, i: number) => (
                                                    <div key={i} className="flex items-center gap-3 rounded-xl bg-surface-primary/80 border border-border-secondary p-3">
                                                      <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${
                                                        cd.change === 'verdict_flip' ? 'bg-accent-red/10' :
                                                        cd.change === 'added' ? 'bg-accent-green/10' :
                                                        cd.change === 'removed' ? 'bg-accent-red/10' :
                                                        'bg-accent-amber/10'
                                                      }`}>
                                                        {cd.change === 'verdict_flip' ? <TrendingDown className="w-3.5 h-3.5 text-accent-red" /> :
                                                         cd.change === 'added' ? <Plus className="w-3.5 h-3.5 text-accent-green" /> :
                                                         cd.change === 'removed' ? <Minus className="w-3.5 h-3.5 text-accent-red" /> :
                                                         <RefreshCw className="w-3.5 h-3.5 text-accent-amber" />}
                                                      </div>
                                                      <div className="flex-1 min-w-0">
                                                        <span className="text-[13px] font-medium text-text-primary">{cd.criterion_name || cd.criterion_id}</span>
                                                        <div className="flex items-center gap-3 mt-0.5">
                                                          {cd.old_met !== null && cd.old_met !== undefined && (
                                                            <span className={`text-xs ${cd.old_met ? 'text-accent-green' : 'text-accent-red'}`}>
                                                              Was: {cd.old_met ? 'Met' : 'Not Met'}
                                                            </span>
                                                          )}
                                                          {cd.new_met !== null && cd.new_met !== undefined && (
                                                            <span className={`text-xs ${cd.new_met ? 'text-accent-green' : 'text-accent-red'}`}>
                                                              Now: {cd.new_met ? 'Met' : 'Not Met'}
                                                            </span>
                                                          )}
                                                        </div>
                                                      </div>
                                                      <span className={`text-[11px] px-2 py-0.5 rounded-md font-medium capitalize ${
                                                        cd.change === 'verdict_flip' ? 'bg-accent-red/10 text-accent-red' :
                                                        cd.change === 'added' ? 'bg-accent-green/10 text-accent-green' :
                                                        cd.change === 'removed' ? 'bg-accent-red/10 text-accent-red' :
                                                        'bg-accent-amber/10 text-accent-amber'
                                                      }`}>
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
                            <div className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8">
                              <div className="flex flex-col items-center justify-center py-8 gap-3">
                                <Users className="w-10 h-10 text-text-quaternary" />
                                <p className="text-text-secondary text-sm">No active BV/PA cases found for this policy</p>
                                <p className="text-text-quaternary text-xs">Add patient records to see impact analysis</p>
                              </div>
                            </div>
                          )}
                        </>
                      ) : null}
                    </motion.div>
                  )}

                  {activeTab === 'changes' && (
                    <motion.div
                      key="changes"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -12 }}
                      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] as const }}
                      className="space-y-3"
                    >
                      {changes.length === 0 ? (
                        <div className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8">
                          <div className="flex flex-col items-center justify-center py-8 gap-3">
                            <CheckCircle2 className="w-10 h-10 text-accent-green" />
                            <p className="text-text-secondary text-sm">No criterion changes detected</p>
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
                              if (next.has(i)) next.delete(i)
                              else next.add(i)
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
                              className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl overflow-hidden"
                            >
                              <button
                                onClick={hasDetails ? toggleExpand : undefined}
                                className={`w-full flex items-center gap-3 p-5 text-left ${hasDetails ? 'cursor-pointer hover:bg-surface-tertiary/40 transition-colors' : 'cursor-default'}`}
                              >
                                <div className={`flex items-center justify-center w-7 h-7 rounded-lg shrink-0 ${changeTypeBg(change.change_type || change.type)}`}>
                                  {changeTypeIcon(change.change_type || change.type)}
                                </div>
                                <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
                                  <span className="text-sm font-medium text-text-primary">
                                    {change.criterion_name || change.criterion || change.name || `Change ${i + 1}`}
                                  </span>
                                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${severityColor(change.severity)}`}>
                                    {severityLabel(change.severity)}
                                  </span>
                                  <span className="text-xs text-text-tertiary capitalize">
                                    {change.change_type || change.type || 'modified'}
                                  </span>
                                </div>
                                {hasDetails && (
                                  <motion.div
                                    animate={{ rotate: isExpanded ? 90 : 0 }}
                                    transition={{ duration: 0.2 }}
                                    className="shrink-0"
                                  >
                                    <ChevronRight className="w-4 h-4 text-text-tertiary" />
                                  </motion.div>
                                )}
                              </button>

                              <AnimatePresence>
                                {isExpanded && (
                                  <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
                                    className="overflow-hidden"
                                  >
                                    <div className="px-5 pb-5 pt-0 ml-10 border-t border-border-secondary">
                                      {(change.description || change.human_summary) && (
                                        <p className="text-xs text-text-secondary mt-3 leading-relaxed">{change.description || change.human_summary}</p>
                                      )}

                                      {addedVal && (
                                        <div className="mt-3 space-y-2">
                                          <p className="text-[11px] font-medium text-accent-green uppercase tracking-wide">New Criterion Details</p>
                                          {[
                                            { label: 'Description', value: addedVal.description },
                                            { label: 'Policy Text', value: addedVal.policy_text },
                                            { label: 'Category', value: addedVal.category || addedVal.criterion_category },
                                            { label: 'Type', value: addedVal.criterion_type },
                                            { label: 'Required', value: addedVal.is_required != null ? (addedVal.is_required ? 'Yes' : 'No') : null },
                                            { label: 'Threshold', value: addedVal.threshold_value != null ? `${addedVal.comparison_operator || ''} ${addedVal.threshold_value}${addedVal.threshold_value_upper != null ? ` – ${addedVal.threshold_value_upper}` : ''} ${addedVal.threshold_unit || ''}`.trim() : null },
                                          ].filter(r => r.value).map((row, j) => (
                                            <div key={j} className="rounded-lg bg-surface-primary/60 p-2.5 text-xs">
                                              <span className="text-text-tertiary font-medium">{row.label}: </span>
                                              <span className="text-text-primary">{row.value}</span>
                                            </div>
                                          ))}
                                        </div>
                                      )}

                                      {removedVal && (
                                        <div className="mt-3 space-y-2">
                                          <p className="text-[11px] font-medium text-accent-red uppercase tracking-wide">Removed Criterion Details</p>
                                          {[
                                            { label: 'Description', value: removedVal.description },
                                            { label: 'Policy Text', value: removedVal.policy_text },
                                            { label: 'Category', value: removedVal.category || removedVal.criterion_category },
                                          ].filter(r => r.value).map((row, j) => (
                                            <div key={j} className="rounded-lg bg-surface-primary/60 p-2.5 text-xs">
                                              <span className="text-text-tertiary font-medium">{row.label}: </span>
                                              <span className="text-text-primary">{row.value}</span>
                                            </div>
                                          ))}
                                        </div>
                                      )}

                                      {fieldChanges.length > 0 && (
                                        <div className="mt-3 space-y-2">
                                          <p className="text-[11px] font-medium text-accent-amber uppercase tracking-wide">What Changed</p>
                                          {fieldChanges.map((field: any, j: number) => (
                                            <div key={j} className="rounded-lg bg-surface-primary/60 p-3 text-xs space-y-1.5">
                                              <span className="text-text-tertiary font-medium">{(field.field || field.field_name || field.name || `Field ${j + 1}`).replace(/_/g, ' ')}</span>
                                              <div className="flex flex-col gap-1 pl-2 border-l-2 border-border-primary">
                                                {(field.old_value ?? field.old) != null && (
                                                  <div className="flex items-start gap-1.5">
                                                    <span className="text-accent-red font-medium shrink-0">Before:</span>
                                                    <span className="text-text-secondary">{String(field.old_value ?? field.old)}</span>
                                                  </div>
                                                )}
                                                {(field.new_value ?? field.new) != null && (
                                                  <div className="flex items-start gap-1.5">
                                                    <span className="text-accent-green font-medium shrink-0">After:</span>
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
    </div>
  )
}
