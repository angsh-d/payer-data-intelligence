import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plus,
  Upload,
  FileText,
  Shield,
  Clock,
  CheckCircle2,
  AlertCircle,
  X,
  Loader2,
} from 'lucide-react'
import { api, type PolicyBankItem, type UploadResponse } from '../lib/api'
import { getDrugInfo, getPayerInfo } from '../lib/drugInfo'

function relativeTime(dateStr: string): string {
  try {
    const now = Date.now()
    const then = new Date(dateStr).getTime()
    const diff = now - then
    const seconds = Math.floor(diff / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)
    const weeks = Math.floor(days / 7)
    const months = Math.floor(days / 30)
    if (months > 0) return `${months} month${months > 1 ? 's' : ''} ago`
    if (weeks > 0) return `${weeks} week${weeks > 1 ? 's' : ''} ago`
    if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`
    if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`
    if (minutes > 0) return `${minutes} min${minutes > 1 ? 's' : ''} ago`
    return 'Just now'
  } catch {
    return dateStr
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function qualityColor(q: string) {
  switch (q?.toLowerCase()) {
    case 'high': return 'bg-accent-green/10 text-accent-green'
    case 'medium': return 'bg-accent-amber/10 text-accent-amber'
    case 'low': return 'bg-accent-red/10 text-accent-red'
    default: return 'bg-surface-tertiary text-text-tertiary'
  }
}

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] as const },
  }),
}

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
}

const modalVariants = {
  hidden: { opacity: 0, scale: 0.95, y: 10 },
  visible: { opacity: 1, scale: 1, y: 0, transition: { duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] as const } },
  exit: { opacity: 0, scale: 0.95, y: 10, transition: { duration: 0.2 } },
}

function ShimmerBlock({ className }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-2xl bg-surface-secondary ${className}`}>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.5s_infinite] bg-gradient-to-r from-transparent via-black/[0.04] to-transparent" />
    </div>
  )
}

function AnimatedDots() {
  return (
    <span className="inline-flex gap-0.5 ml-1">
      {[0, 1, 2].map(i => (
        <motion.span
          key={i}
          className="inline-block w-1 h-1 rounded-full bg-current"
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.3 }}
        />
      ))}
    </span>
  )
}

type UploadStep = 'idle' | 'inferring' | 'extracting' | 'validating' | 'storing' | 'success' | 'error'

const uploadSteps = ['Extracting', 'Validating', 'Storing'] as const

function UploadModal({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [payer, setPayer] = useState('')
  const [medication, setMedication] = useState('')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [notes, setNotes] = useState('')
  const [step, setStep] = useState<UploadStep>('idle')
  const [activeUploadStep, setActiveUploadStep] = useState(0)
  const [error, setError] = useState('')
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const reset = useCallback(() => {
    setFile(null)
    setPayer('')
    setMedication('')
    setEffectiveDate('')
    setNotes('')
    setStep('idle')
    setActiveUploadStep(0)
    setError('')
    setUploadResult(null)
  }, [])

  const handleClose = useCallback(() => {
    reset()
    onClose()
  }, [reset, onClose])

  const handleFile = useCallback(async (f: File) => {
    setFile(f)
    setStep('inferring')
    setError('')
    try {
      const meta = await api.inferMetadata(f)
      setPayer(meta.payer_name || '')
      setMedication(meta.medication_name || '')
      setEffectiveDate(meta.effective_date || '')
      setStep('idle')
    } catch {
      setStep('idle')
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files?.[0]
    if (f) handleFile(f)
  }, [handleFile])

  const handleUpload = useCallback(async () => {
    if (!file || !payer || !medication) return
    setStep('extracting')
    setActiveUploadStep(0)
    setError('')

    try {
      const stepDelay = (ms: number) => new Promise(r => setTimeout(r, ms))
      await stepDelay(800)
      setStep('validating')
      setActiveUploadStep(1)
      await stepDelay(600)
      setStep('storing')
      setActiveUploadStep(2)

      const result = await api.uploadPolicy(file, payer, medication, notes || undefined)
      setUploadResult(result)
      setStep('success')
      onSuccess()
    } catch (err: any) {
      setError(err?.message || 'Upload failed')
      setStep('error')
    }
  }, [file, payer, medication, notes, onSuccess])

  const isUploading = step === 'extracting' || step === 'validating' || step === 'storing'

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          variants={overlayVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={handleClose} />
          <motion.div
            variants={modalVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="relative w-full max-w-lg rounded-2xl border border-border-primary bg-surface-elevated shadow-2xl overflow-hidden"
          >
            <div className="flex items-center justify-between p-6 pb-0">
              <h2 className="text-lg font-semibold text-text-primary">Upload Policy</h2>
              <button
                onClick={handleClose}
                className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-hover transition-colors"
              >
                <X className="w-4 h-4 text-text-tertiary" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              {step === 'success' ? (
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex flex-col items-center gap-4 py-8"
                >
                  <div className="w-16 h-16 rounded-full bg-accent-green/10 flex items-center justify-center">
                    <CheckCircle2 className="w-8 h-8 text-accent-green" />
                  </div>
                  <div className="text-center">
                    <p className="text-lg font-semibold text-text-primary">Upload Successful</p>
                    <p className="text-sm text-text-secondary mt-1">
                      {getPayerInfo(payer).abbreviation} · {getDrugInfo(medication).brandName}
                    </p>
                    {uploadResult && (
                      <div className="mt-4 flex flex-wrap items-center justify-center gap-3 text-xs text-text-tertiary">
                        <span>Version {uploadResult.version}</span>
                        <span>·</span>
                        <span className={qualityColor(uploadResult.extraction_quality) + ' px-2 py-0.5 rounded-full text-xs font-medium'}>
                          {uploadResult.extraction_quality} quality
                        </span>
                        <span>·</span>
                        <span>{uploadResult.criteria_count} criteria</span>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={handleClose}
                    className="mt-4 px-6 py-2.5 rounded-full bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue-hover transition-colors"
                  >
                    Done
                  </button>
                </motion.div>
              ) : step === 'error' ? (
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex flex-col items-center gap-4 py-8"
                >
                  <div className="w-16 h-16 rounded-full bg-accent-red/10 flex items-center justify-center">
                    <AlertCircle className="w-8 h-8 text-accent-red" />
                  </div>
                  <div className="text-center">
                    <p className="text-lg font-semibold text-text-primary">Upload Failed</p>
                    <p className="text-sm text-accent-red mt-1">{error}</p>
                  </div>
                  <button
                    onClick={() => { setStep('idle'); setError(''); }}
                    className="mt-4 px-6 py-2.5 rounded-full bg-surface-tertiary text-text-primary text-sm font-medium hover:bg-surface-hover transition-colors"
                  >
                    Try Again
                  </button>
                </motion.div>
              ) : (
                <>
                  {!file ? (
                    <div
                      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                      onDragLeave={() => setDragOver(false)}
                      onDrop={handleDrop}
                      onClick={() => fileInputRef.current?.click()}
                      className={`relative flex flex-col items-center justify-center gap-3 p-10 rounded-xl border-2 border-dashed cursor-pointer transition-all duration-200 ${
                        dragOver
                          ? 'border-accent-blue bg-accent-blue/5'
                          : 'border-border-primary hover:border-border-hover hover:bg-surface-hover/30'
                      }`}
                    >
                      <Upload className={`w-8 h-8 ${dragOver ? 'text-accent-blue' : 'text-text-quaternary'} transition-colors`} />
                      <div className="text-center">
                        <p className="text-sm font-medium text-text-secondary">
                          Drop your policy PDF here
                        </p>
                        <p className="text-xs text-text-tertiary mt-1">or click to browse</p>
                      </div>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.txt,.doc,.docx"
                        className="hidden"
                        onChange={e => {
                          const f = e.target.files?.[0]
                          if (f) handleFile(f)
                        }}
                      />
                    </div>
                  ) : (
                    <div className="flex items-center gap-3 p-4 rounded-xl bg-surface-tertiary/50 border border-border-primary">
                      <div className="w-10 h-10 rounded-lg bg-accent-blue/10 flex items-center justify-center shrink-0">
                        <FileText className="w-5 h-5 text-accent-blue" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-text-primary truncate">{file.name}</p>
                        <p className="text-xs text-text-tertiary">{formatFileSize(file.size)}</p>
                      </div>
                      {step === 'inferring' && (
                        <Loader2 className="w-4 h-4 text-accent-blue animate-spin shrink-0" />
                      )}
                      {!isUploading && step !== 'inferring' && (
                        <button
                          onClick={() => { setFile(null); setPayer(''); setMedication(''); setEffectiveDate(''); }}
                          className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-surface-hover transition-colors shrink-0"
                        >
                          <X className="w-3.5 h-3.5 text-text-tertiary" />
                        </button>
                      )}
                    </div>
                  )}

                  {file && (
                    <>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-xs font-medium text-text-tertiary mb-1.5">Payer Name</label>
                          <input
                            type="text"
                            value={payer}
                            onChange={e => setPayer(e.target.value)}
                            disabled={isUploading}
                            placeholder="e.g. Blue Cross Blue Shield"
                            className="w-full px-4 py-2.5 rounded-xl bg-surface-tertiary/50 border border-border-primary text-sm text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-all disabled:opacity-50"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-text-tertiary mb-1.5">Medication Name</label>
                          <input
                            type="text"
                            value={medication}
                            onChange={e => setMedication(e.target.value)}
                            disabled={isUploading}
                            placeholder="e.g. Ibrance"
                            className="w-full px-4 py-2.5 rounded-xl bg-surface-tertiary/50 border border-border-primary text-sm text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-all disabled:opacity-50"
                          />
                        </div>
                        {effectiveDate && (
                          <div>
                            <label className="block text-xs font-medium text-text-tertiary mb-1.5">Effective Date</label>
                            <input
                              type="text"
                              value={effectiveDate}
                              onChange={e => setEffectiveDate(e.target.value)}
                              disabled={isUploading}
                              className="w-full px-4 py-2.5 rounded-xl bg-surface-tertiary/50 border border-border-primary text-sm text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-all disabled:opacity-50"
                            />
                          </div>
                        )}
                        <div>
                          <label className="block text-xs font-medium text-text-tertiary mb-1.5">Amendment Notes <span className="text-text-quaternary">(optional)</span></label>
                          <textarea
                            value={notes}
                            onChange={e => setNotes(e.target.value)}
                            disabled={isUploading}
                            rows={2}
                            placeholder="Describe any changes or context..."
                            className="w-full px-4 py-2.5 rounded-xl bg-surface-tertiary/50 border border-border-primary text-sm text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-all resize-none disabled:opacity-50"
                          />
                        </div>
                      </div>

                      {isUploading && (
                        <div className="flex items-center justify-center gap-6 py-3">
                          {uploadSteps.map((label, i) => (
                            <div key={label} className="flex items-center gap-1.5">
                              {i < activeUploadStep ? (
                                <CheckCircle2 className="w-4 h-4 text-accent-green" />
                              ) : i === activeUploadStep ? (
                                <Loader2 className="w-4 h-4 text-accent-blue animate-spin" />
                              ) : (
                                <div className="w-4 h-4 rounded-full border border-border-primary" />
                              )}
                              <span className={`text-xs font-medium ${
                                i === activeUploadStep ? 'text-accent-blue' : i < activeUploadStep ? 'text-accent-green' : 'text-text-quaternary'
                              }`}>
                                {label}
                                {i === activeUploadStep && <AnimatedDots />}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      {!isUploading && (
                        <button
                          onClick={handleUpload}
                          disabled={!payer || !medication || step === 'inferring'}
                          className="w-full py-3 rounded-xl bg-accent-blue text-white text-sm font-semibold hover:bg-accent-blue-hover transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-[0_0_20px_rgba(0,113,227,0.3)]"
                        >
                          Upload Policy
                        </button>
                      )}
                    </>
                  )}
                </>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default function PolicyVault() {
  const [policies, setPolicies] = useState<PolicyBankItem[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)

  const fetchPolicies = useCallback(() => {
    setLoading(true)
    api.getPolicyBank()
      .then(setPolicies)
      .catch(() => setPolicies([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchPolicies() }, [fetchPolicies])

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
        className="flex items-start justify-between"
      >
        <div>
          <h1 className="text-3xl font-semibold text-text-primary tracking-tight">Policy Vault</h1>
          <p className="text-text-tertiary mt-1">Manage and organize your policy document library</p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue-hover transition-all hover:shadow-[0_0_20px_rgba(0,113,227,0.3)]"
        >
          <Plus className="w-4 h-4" />
          Upload Policy
        </button>
      </motion.div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {[...Array(6)].map((_, i) => (
            <ShimmerBlock key={i} className="h-48" />
          ))}
        </div>
      ) : policies.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] as const }}
          className="flex flex-col items-center justify-center py-32 gap-5"
        >
          <div className="w-20 h-20 rounded-2xl bg-surface-secondary flex items-center justify-center">
            <Shield className="w-10 h-10 text-text-quaternary" />
          </div>
          <div className="text-center">
            <p className="text-lg font-semibold text-text-secondary">No policies yet</p>
            <p className="text-sm text-text-tertiary mt-1 max-w-sm">
              Upload your first policy document to start building your intelligent policy vault.
            </p>
          </div>
          <button
            onClick={() => setModalOpen(true)}
            className="mt-2 flex items-center gap-2 px-6 py-2.5 rounded-full bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue-hover transition-all hover:shadow-[0_0_20px_rgba(0,113,227,0.3)]"
          >
            <Plus className="w-4 h-4" />
            Upload Policy
          </button>
        </motion.div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {policies.map((policy, i) => {
            const drugInfo = getDrugInfo(policy.medication)
            const payerInfo = getPayerInfo(policy.payer)
            const DrugIcon = drugInfo.icon
            const showGeneric = drugInfo.genericName && drugInfo.genericName.toLowerCase() !== drugInfo.brandName.toLowerCase()
            return (
              <motion.div
                key={`${policy.payer}-${policy.medication}`}
                custom={i + 1}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className="group rounded-2xl border border-border-primary bg-surface-secondary/60 backdrop-blur-xl p-6 flex flex-col gap-4 hover:bg-surface-hover/40 hover:border-border-hover transition-all duration-300"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-6 h-6 rounded-full ${payerInfo.color} flex items-center justify-center shrink-0`}>
                      <span className="text-[10px] font-bold text-white leading-none">{payerInfo.abbreviation.charAt(0)}</span>
                    </div>
                    <span className="inline-flex px-3 py-1 rounded-full bg-surface-tertiary text-xs font-semibold text-text-secondary tracking-wide">
                      {payerInfo.abbreviation}
                    </span>
                  </div>
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${qualityColor(policy.extraction_quality)}`}>
                    {policy.extraction_quality || 'Unknown'}
                  </span>
                </div>

                <div className="flex-1">
                  <div className="flex items-center gap-2.5">
                    <div className={`w-8 h-8 rounded-lg ${drugInfo.color.split(' ').find(c => c.startsWith('bg-')) || 'bg-surface-tertiary'} flex items-center justify-center shrink-0`}>
                      <DrugIcon className={`w-4 h-4 ${drugInfo.color.split(' ').find(c => c.startsWith('text-')) || 'text-text-secondary'}`} />
                    </div>
                    <h3 className="text-xl font-semibold text-text-primary tracking-tight group-hover:text-accent-blue transition-colors duration-200">
                      {drugInfo.brandName}
                    </h3>
                  </div>
                  {(showGeneric || drugInfo.category) && (
                    <div className="flex items-center gap-2 mt-1.5 ml-[42px]">
                      {showGeneric && (
                        <span className="text-xs text-text-tertiary">{drugInfo.genericName}</span>
                      )}
                      {showGeneric && drugInfo.category && (
                        <span className="text-text-quaternary text-xs">·</span>
                      )}
                      {drugInfo.category && (
                        <span className="text-xs text-text-quaternary">{drugInfo.category}</span>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-border-primary">
                  <div className="flex items-center gap-1.5 text-xs text-text-tertiary">
                    <FileText className="w-3.5 h-3.5" />
                    <span>{policy.version_count} version{policy.version_count !== 1 ? 's' : ''}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-text-tertiary">
                    <Clock className="w-3.5 h-3.5" />
                    <span>{relativeTime(policy.last_updated)}</span>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}

      <UploadModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={fetchPolicies}
      />
    </div>
  )
}
