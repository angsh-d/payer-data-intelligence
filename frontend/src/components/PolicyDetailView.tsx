import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft,
  ChevronDown,
  FileText,
  AlertCircle,
  Loader2,
  BookOpen,
  Stethoscope,
  Pill,
  ShieldCheck,
  ClipboardList,
  Ban,
  FlaskConical,
} from 'lucide-react'
import { api, type PolicyBankItem } from '../lib/api'
import { getDrugInfo, getPayerInfo } from '../lib/drugInfo'

interface PolicyDetailViewProps {
  policy: PolicyBankItem
  onBack: () => void
}

interface CriterionData {
  criterion_id?: string
  criterion_name?: string
  description?: string
  policy_text?: string
  category?: string
  criterion_type?: string
  is_required?: boolean
  source_page?: number | null
  source_text_excerpt?: string
  evidence_types?: string[]
  [key: string]: any
}

const categoryIcons: Record<string, typeof Stethoscope> = {
  diagnosis: Stethoscope,
  lab_results: FlaskConical,
  treatment_history: Pill,
  step_therapy: ClipboardList,
  prescriber: ShieldCheck,
  safety: ShieldCheck,
  concurrent_therapy: Ban,
  documentation: BookOpen,
}

const categoryLabels: Record<string, string> = {
  diagnosis: 'Diagnosis',
  lab_results: 'Lab Results',
  treatment_history: 'Treatment History',
  step_therapy: 'Step Therapy',
  prescriber: 'Prescriber',
  safety: 'Safety',
  concurrent_therapy: 'Concurrent Therapy',
  documentation: 'Documentation',
}

function groupCriteriaByCategory(criteria: Record<string, CriterionData>): Record<string, CriterionData[]> {
  const groups: Record<string, CriterionData[]> = {}
  for (const [id, c] of Object.entries(criteria)) {
    const cat = c.category || 'other'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push({ ...c, criterion_id: c.criterion_id || id })
  }
  return groups
}

export default function PolicyDetailView({ policy, onBack }: PolicyDetailViewProps) {
  const [digitizedData, setDigitizedData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hasPdf, setHasPdf] = useState(false)
  const [pdfPage, setPdfPage] = useState(1)
  const [expandedCriteria, setExpandedCriteria] = useState<Set<string>>(new Set())
  const [activeCriterionId, setActiveCriterionId] = useState<string | null>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  const drugInfo = getDrugInfo(policy.medication)
  const payerInfo = getPayerInfo(policy.payer)
  const pdfUrl = api.getPdfUrl(policy.payer, policy.medication)

  useEffect(() => {
    setLoading(true)
    setError(null)

    const fetchData = async () => {
      try {
        const [data, pdfExists] = await Promise.all([
          api.getDigitizedPolicy(policy.payer, policy.medication),
          api.checkPdfExists(policy.payer, policy.medication),
        ])
        setDigitizedData(data)
        setHasPdf(pdfExists)
      } catch (e: any) {
        setError(e.message || 'Failed to load policy data')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [policy.payer, policy.medication])

  const navigateToPage = useCallback((page: number) => {
    if (!page || page < 1) return
    setPdfPage(page)
    if (iframeRef.current) {
      iframeRef.current.src = `${pdfUrl}#page=${page}`
    }
  }, [pdfUrl])

  const handleCriterionClick = useCallback((criterion: CriterionData) => {
    const id = criterion.criterion_id || ''
    setActiveCriterionId(id)

    setExpandedCriteria(prev => {
      const next = new Set(prev)
      next.add(id)
      return next
    })

    if (criterion.source_page && criterion.source_page > 0) {
      navigateToPage(criterion.source_page)
    }
  }, [navigateToPage])

  const toggleExpand = useCallback((id: string) => {
    setExpandedCriteria(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 text-accent-blue animate-spin" />
          <p className="text-sm text-text-tertiary">Loading policy data...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-10 max-w-[1400px]">
        <button onClick={onBack} className="flex items-center gap-2 text-sm text-text-secondary hover:text-accent-blue transition-colors mb-6">
          <ArrowLeft className="w-4 h-4" />
          Back to Policy Vault
        </button>
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <AlertCircle className="w-10 h-10 text-accent-red" />
          <p className="text-text-secondary">{error}</p>
        </div>
      </div>
    )
  }

  const atomicCriteria = digitizedData?.atomic_criteria || {}
  const criterionGroups = digitizedData?.criterion_groups || {}
  const indications = digitizedData?.indications || []
  const exclusions = digitizedData?.exclusions || []
  const safetyScreenings = digitizedData?.safety_screenings || []
  const provenances = digitizedData?.provenances || {}
  const grouped = groupCriteriaByCategory(atomicCriteria)

  const renderFieldValue = (_key: string, value: any): string => {
    if (value === null || value === undefined) return '—'
    if (typeof value === 'boolean') return value ? 'Yes' : 'No'
    if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
    return String(value)
  }

  const displayFields = [
    'description', 'policy_text', 'criterion_type', 'is_required',
    'evidence_types', 'source_text_excerpt', 'minimum_duration_days',
    'patient_data_path',
  ]

  return (
    <div className="h-full">
      <div className="px-8 pt-6 pb-4 border-b border-[rgba(0,0,0,0.06)] bg-white">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-[13px] text-[#86868b] hover:text-[#0071e3] transition-colors mb-4"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Policy Vault
        </button>
        <div className="flex items-center gap-4">
          <div className={`w-10 h-10 rounded-xl ${drugInfo.color.split(' ').find(c => c.startsWith('bg-')) || 'bg-surface-tertiary'} flex items-center justify-center`}>
            <drugInfo.icon className={`w-5 h-5 ${drugInfo.color.split(' ').find(c => c.startsWith('text-')) || 'text-text-secondary'}`} />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-[#1d1d1f] tracking-tight">{drugInfo.brandName}</h1>
              <span className="inline-flex px-2.5 py-0.5 rounded-full bg-[#f5f5f7] text-[11px] font-semibold text-[#6e6e73] tracking-wide">
                {payerInfo.abbreviation}
              </span>
            </div>
            <p className="text-[13px] text-[#86868b] mt-0.5">
              {drugInfo.genericName}{drugInfo.category ? ` · ${drugInfo.category}` : ''}
              {digitizedData?.policy_id ? ` · Policy ${digitizedData.policy_id}` : ''}
            </p>
          </div>
        </div>
      </div>

      <div className="flex h-[calc(100vh-160px)]">
        <div className="w-1/2 overflow-y-auto border-r border-[rgba(0,0,0,0.06)] bg-[#fafafa]">
          <div className="p-6 space-y-5">

            {digitizedData?.policy_title && (
              <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-5">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[#86868b] mb-3">Policy Overview</h3>
                <div className="grid grid-cols-2 gap-3 text-[13px]">
                  {digitizedData.policy_title && (
                    <div><span className="text-[#86868b]">Title</span><p className="text-[#1d1d1f] font-medium mt-0.5">{digitizedData.policy_title}</p></div>
                  )}
                  {digitizedData.policy_number && (
                    <div><span className="text-[#86868b]">Number</span><p className="text-[#1d1d1f] font-medium mt-0.5">{digitizedData.policy_number}</p></div>
                  )}
                  {digitizedData.effective_date && (
                    <div><span className="text-[#86868b]">Effective</span><p className="text-[#1d1d1f] font-medium mt-0.5">{digitizedData.effective_date}</p></div>
                  )}
                  {digitizedData.last_revision_date && (
                    <div><span className="text-[#86868b]">Revised</span><p className="text-[#1d1d1f] font-medium mt-0.5">{digitizedData.last_revision_date}</p></div>
                  )}
                  {digitizedData.policy_type && (
                    <div><span className="text-[#86868b]">Type</span><p className="text-[#1d1d1f] font-medium mt-0.5">{digitizedData.policy_type.replace(/_/g, ' ')}</p></div>
                  )}
                  {digitizedData.extraction_quality && (
                    <div><span className="text-[#86868b]">Quality</span><p className="text-[#1d1d1f] font-medium mt-0.5 capitalize">{digitizedData.extraction_quality}</p></div>
                  )}
                </div>
              </div>
            )}

            {Object.keys(grouped).length > 0 && (
              <div className="space-y-3">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[#86868b] px-1">
                  Extracted Criteria ({Object.values(atomicCriteria).length})
                </h3>
                {Object.entries(grouped).map(([category, criteria]) => {
                  const CatIcon = categoryIcons[category] || FileText
                  const label = categoryLabels[category] || category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                  return (
                    <div key={category} className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white overflow-hidden">
                      <div className="px-5 py-3 bg-[#fafafa] border-b border-[rgba(0,0,0,0.04)] flex items-center gap-2">
                        <CatIcon className="w-3.5 h-3.5 text-[#86868b]" />
                        <span className="text-[12px] font-semibold text-[#6e6e73]">{label}</span>
                        <span className="text-[11px] text-[#aeaeb2] ml-auto">{criteria.length}</span>
                      </div>
                      <div className="divide-y divide-[rgba(0,0,0,0.04)]">
                        {criteria.map((criterion) => {
                          const id = criterion.criterion_id || ''
                          const isExpanded = expandedCriteria.has(id)
                          const isActive = activeCriterionId === id
                          const page = criterion.source_page
                          const prov = provenances[id]
                          const sourcePage = page || prov?.source_page

                          return (
                            <div
                              key={id}
                              className={`transition-colors duration-150 ${isActive ? 'bg-[#0071e3]/[0.04]' : ''}`}
                            >
                              <button
                                onClick={() => {
                                  toggleExpand(id)
                                  handleCriterionClick({ ...criterion, source_page: sourcePage })
                                }}
                                className="w-full px-5 py-3 flex items-center gap-3 text-left hover:bg-[rgba(0,0,0,0.02)] transition-colors"
                              >
                                <div className={`w-4 h-4 flex items-center justify-center transition-transform ${isExpanded ? 'rotate-0' : '-rotate-90'}`}>
                                  <ChevronDown className="w-3.5 h-3.5 text-[#aeaeb2]" />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="text-[13px] font-medium text-[#1d1d1f] truncate">
                                      {criterion.criterion_name || criterion.description || id}
                                    </span>
                                    {criterion.is_required && (
                                      <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-[#d70015]/10 text-[#d70015] font-medium">Required</span>
                                    )}
                                  </div>
                                  {criterion.description && criterion.criterion_name && (
                                    <p className="text-[12px] text-[#86868b] truncate mt-0.5">{criterion.description}</p>
                                  )}
                                </div>
                                {sourcePage && (
                                  <span className="shrink-0 text-[11px] text-[#0071e3] font-medium px-2 py-0.5 rounded-full bg-[#0071e3]/[0.06]">
                                    p.{sourcePage}
                                  </span>
                                )}
                              </button>

                              <AnimatePresence>
                                {isExpanded && (
                                  <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    transition={{ duration: 0.2 }}
                                    className="overflow-hidden"
                                  >
                                    <div className="px-5 pb-4 pl-12 space-y-2">
                                      {displayFields.map(field => {
                                        const val = criterion[field]
                                        if (val === undefined || val === null || val === '' || (Array.isArray(val) && val.length === 0)) return null
                                        const label = field.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                                        return (
                                          <div key={field} className="flex gap-3">
                                            <span className="text-[11px] text-[#aeaeb2] w-28 shrink-0 pt-0.5 uppercase tracking-wide font-medium">{label}</span>
                                            <span className="text-[12px] text-[#1d1d1f] leading-relaxed flex-1">{renderFieldValue(field, val)}</span>
                                          </div>
                                        )
                                      })}
                                      {prov?.extraction_confidence && (
                                        <div className="flex gap-3">
                                          <span className="text-[11px] text-[#aeaeb2] w-28 shrink-0 pt-0.5 uppercase tracking-wide font-medium">Confidence</span>
                                          <span className="text-[12px] text-[#1d1d1f] capitalize">{prov.extraction_confidence}</span>
                                        </div>
                                      )}
                                      {prov?.validation_action && (
                                        <div className="flex gap-3">
                                          <span className="text-[11px] text-[#aeaeb2] w-28 shrink-0 pt-0.5 uppercase tracking-wide font-medium">Validation</span>
                                          <span className="text-[12px] text-[#1d1d1f] capitalize">{prov.validation_action}</span>
                                        </div>
                                      )}
                                    </div>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {indications.length > 0 && (
              <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white overflow-hidden">
                <div className="px-5 py-3 bg-[#fafafa] border-b border-[rgba(0,0,0,0.04)] flex items-center gap-2">
                  <ClipboardList className="w-3.5 h-3.5 text-[#86868b]" />
                  <span className="text-[12px] font-semibold text-[#6e6e73]">Indications</span>
                  <span className="text-[11px] text-[#aeaeb2] ml-auto">{indications.length}</span>
                </div>
                <div className="divide-y divide-[rgba(0,0,0,0.04)]">
                  {indications.map((ind: any, i: number) => (
                    <div key={i} className="px-5 py-3">
                      <p className="text-[13px] font-medium text-[#1d1d1f]">{ind.indication_name || `Indication ${i + 1}`}</p>
                      {ind.initial_approval_duration_months && (
                        <p className="text-[12px] text-[#86868b] mt-1">Initial: {ind.initial_approval_duration_months} months</p>
                      )}
                      {ind.continuation_approval_duration_months && (
                        <p className="text-[12px] text-[#86868b]">Continuation: {ind.continuation_approval_duration_months} months</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {exclusions.length > 0 && (
              <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white overflow-hidden">
                <div className="px-5 py-3 bg-[#fafafa] border-b border-[rgba(0,0,0,0.04)] flex items-center gap-2">
                  <Ban className="w-3.5 h-3.5 text-[#86868b]" />
                  <span className="text-[12px] font-semibold text-[#6e6e73]">Exclusions</span>
                  <span className="text-[11px] text-[#aeaeb2] ml-auto">{exclusions.length}</span>
                </div>
                <div className="divide-y divide-[rgba(0,0,0,0.04)]">
                  {exclusions.map((ex: any, i: number) => (
                    <div key={i} className="px-5 py-3">
                      <p className="text-[13px] font-medium text-[#1d1d1f]">{ex.name || `Exclusion ${i + 1}`}</p>
                      {ex.description && <p className="text-[12px] text-[#86868b] mt-1">{ex.description}</p>}
                      {ex.policy_text && <p className="text-[12px] text-[#6e6e73] mt-1 italic">"{ex.policy_text}"</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {safetyScreenings.length > 0 && (
              <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white overflow-hidden">
                <div className="px-5 py-3 bg-[#fafafa] border-b border-[rgba(0,0,0,0.04)] flex items-center gap-2">
                  <ShieldCheck className="w-3.5 h-3.5 text-[#86868b]" />
                  <span className="text-[12px] font-semibold text-[#6e6e73]">Safety Screenings</span>
                  <span className="text-[11px] text-[#aeaeb2] ml-auto">{safetyScreenings.length}</span>
                </div>
                <div className="divide-y divide-[rgba(0,0,0,0.04)]">
                  {safetyScreenings.map((ss: any, i: number) => (
                    <div key={i} className="px-5 py-3">
                      <p className="text-[13px] font-medium text-[#1d1d1f]">{ss.name || `Screening ${i + 1}`}</p>
                      {ss.description && <p className="text-[12px] text-[#86868b] mt-1">{ss.description}</p>}
                      {ss.frequency && <p className="text-[12px] text-[#6e6e73] mt-1">Frequency: {ss.frequency}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {Object.keys(criterionGroups).length > 0 && (
              <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white overflow-hidden">
                <div className="px-5 py-3 bg-[#fafafa] border-b border-[rgba(0,0,0,0.04)] flex items-center gap-2">
                  <BookOpen className="w-3.5 h-3.5 text-[#86868b]" />
                  <span className="text-[12px] font-semibold text-[#6e6e73]">Criterion Groups</span>
                  <span className="text-[11px] text-[#aeaeb2] ml-auto">{Object.keys(criterionGroups).length}</span>
                </div>
                <div className="divide-y divide-[rgba(0,0,0,0.04)]">
                  {Object.entries(criterionGroups).map(([gid, group]: [string, any]) => (
                    <div key={gid} className="px-5 py-3">
                      <p className="text-[13px] font-medium text-[#1d1d1f]">{group.group_name || gid}</p>
                      {group.description && <p className="text-[12px] text-[#86868b] mt-1">{group.description}</p>}
                      {group.logic && <p className="text-[12px] text-[#6e6e73] mt-1">Logic: {group.logic}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        </div>

        <div className="w-1/2 bg-[#f0f0f0] flex flex-col">
          {hasPdf ? (
            <>
              <div className="px-5 py-3 bg-white border-b border-[rgba(0,0,0,0.06)] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5 text-[#86868b]" />
                  <span className="text-[12px] font-semibold text-[#6e6e73]">Source Document</span>
                </div>
                <span className="text-[11px] text-[#aeaeb2]">Page {pdfPage}</span>
              </div>
              <iframe
                ref={iframeRef}
                src={`${pdfUrl}#page=${pdfPage}`}
                className="flex-1 w-full border-0"
                title="Policy PDF"
              />
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-[rgba(0,0,0,0.04)] flex items-center justify-center">
                <FileText className="w-8 h-8 text-[#aeaeb2]" />
              </div>
              <div className="text-center">
                <p className="text-[15px] font-medium text-[#6e6e73]">No PDF Available</p>
                <p className="text-[13px] text-[#aeaeb2] mt-1 max-w-xs">
                  The original PDF document was not found for this policy. Only the extracted data is shown.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
