import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  GitCompareArrows,
  ChevronDown,
  Search,
  FileText,
  Clock,
  ArrowRight,
  Plus,
  Minus,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Info,
  Sparkles,
  BarChart3,
  List,
  Upload,
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

  const diffData = diffResult?.diff
  const changes: any[] = diffData?.changes || diffData?.criterion_changes || []
  const stats = diffData?.statistics || diffData?.stats || {}

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
                      { key: 'impact', label: 'Impact', icon: BarChart3 },
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
                      <div className="flex items-center gap-2 mb-5">
                        <Sparkles className="w-4 h-4 text-accent-purple" />
                        <h3 className="text-sm font-medium text-text-secondary">AI-Generated Summary</h3>
                      </div>
                      <div className="prose prose-sm max-w-none">
                        <p className="text-text-primary leading-relaxed whitespace-pre-wrap text-sm">
                          {typeof diffResult.summary === 'string'
                            ? diffResult.summary
                            : typeof diffResult.summary === 'object' && diffResult.summary
                              ? Object.entries(diffResult.summary as Record<string, string>)
                                  .map(([key, val]) => `${key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}:\n${val}`)
                                  .join('\n\n')
                              : 'No summary available for this comparison.'}
                        </p>
                      </div>
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
                        changes.map((change: any, i: number) => (
                          <motion.div
                            key={i}
                            custom={i}
                            variants={fadeUp}
                            initial="hidden"
                            animate="visible"
                            className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-5"
                          >
                            <div className="flex items-start gap-3">
                              <div className={`flex items-center justify-center w-7 h-7 rounded-lg shrink-0 mt-0.5 ${changeTypeBg(change.change_type || change.type)}`}>
                                {changeTypeIcon(change.change_type || change.type)}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-sm font-medium text-text-primary">
                                    {change.criterion_name || change.criterion || change.name || `Change ${i + 1}`}
                                  </span>
                                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${severityColor(change.severity)}`}>
                                    {(change.severity || 'minor').toUpperCase()}
                                  </span>
                                  <span className="text-xs text-text-tertiary capitalize">
                                    {change.change_type || change.type || 'modified'}
                                  </span>
                                </div>

                                {change.description && (
                                  <p className="text-xs text-text-secondary mt-2 leading-relaxed">{change.description}</p>
                                )}

                                {(change.field_changes || change.fields || change.details) && (
                                  <div className="mt-3 space-y-1.5">
                                    {(change.field_changes || change.fields || change.details || []).map((field: any, j: number) => (
                                      <div key={j} className="flex items-start gap-2 text-xs">
                                        <span className="text-text-tertiary font-mono shrink-0">{field.field || field.name || `Field ${j + 1}`}:</span>
                                        <div className="flex flex-col gap-0.5">
                                          {field.old_value !== undefined && (
                                            <span className="text-accent-red/80 line-through">{String(field.old_value)}</span>
                                          )}
                                          {field.new_value !== undefined && (
                                            <span className="text-accent-green/80">{String(field.new_value)}</span>
                                          )}
                                          {field.change && <span className="text-text-secondary">{field.change}</span>}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          </motion.div>
                        ))
                      )}
                    </motion.div>
                  )}

                  {activeTab === 'impact' && (
                    <motion.div
                      key="impact"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -12 }}
                      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] as const }}
                      className="rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-8"
                    >
                      <div className="flex items-center gap-2 mb-6">
                        <BarChart3 className="w-4 h-4 text-accent-blue" />
                        <h3 className="text-sm font-medium text-text-secondary">Impact Analysis</h3>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-8">
                        {[
                          {
                            label: 'Old Criteria',
                            value: stats.old_criteria_count ?? stats.criteria_old ?? stats.total_old ?? '—',
                            color: 'text-text-secondary',
                          },
                          {
                            label: 'New Criteria',
                            value: stats.new_criteria_count ?? stats.criteria_new ?? stats.total_new ?? '—',
                            color: 'text-text-secondary',
                          },
                          {
                            label: 'Added',
                            value: stats.added ?? stats.criteria_added ?? 0,
                            color: 'text-accent-green',
                            icon: Plus,
                          },
                          {
                            label: 'Removed',
                            value: stats.removed ?? stats.criteria_removed ?? 0,
                            color: 'text-accent-red',
                            icon: Minus,
                          },
                          {
                            label: 'Modified',
                            value: stats.modified ?? stats.criteria_modified ?? 0,
                            color: 'text-accent-amber',
                            icon: RefreshCw,
                          },
                        ].map((stat) => {
                          const Icon = stat.icon
                          return (
                            <div
                              key={stat.label}
                              className="rounded-xl border border-border-primary bg-surface-tertiary/50 p-4"
                            >
                              <div className="flex items-center gap-1.5 mb-1">
                                {Icon && <Icon className={`w-3 h-3 ${stat.color}`} />}
                                <span className="text-xs text-text-tertiary">{stat.label}</span>
                              </div>
                              <span className={`text-2xl font-semibold ${stat.color}`}>
                                {stat.value}
                              </span>
                            </div>
                          )
                        })}
                      </div>

                      {(stats.severity_assessment || stats.overall_severity || diffData?.severity_assessment) && (
                        <div className="rounded-xl border border-border-primary bg-surface-tertiary/30 p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <AlertTriangle className="w-4 h-4 text-accent-amber" />
                            <span className="text-xs font-medium text-text-secondary">Severity Assessment</span>
                          </div>
                          <p className="text-sm text-text-primary leading-relaxed">
                            {stats.severity_assessment || stats.overall_severity || diffData?.severity_assessment || 'No severity assessment available.'}
                          </p>
                        </div>
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
