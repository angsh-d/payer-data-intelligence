import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, ArrowUp, X, ChevronDown, Bot } from 'lucide-react'
import { api, type PolicyBankItem } from '../lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  follow_ups?: string[]
}

const SUGGESTIONS = [
  'What medications require step therapy for BCBS?',
  'Compare infliximab coverage across payers',
  'What are the exclusion criteria for Spinraza?',
  'Summarize recent policy changes',
]

const messageVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] as const },
  },
}

function renderFormattedText(text: string) {
  const lines = text.split('\n')
  return lines.map((line, i) => {
    const bulletMatch = line.match(/^[\s]*[-•*]\s+(.*)/)
    if (bulletMatch) {
      return (
        <div key={i} className="flex gap-2 ml-1 my-0.5">
          <span className="text-text-tertiary mt-0.5">•</span>
          <span>{renderInline(bulletMatch[1])}</span>
        </div>
      )
    }

    const numberedMatch = line.match(/^[\s]*(\d+)[.)]\s+(.*)/)
    if (numberedMatch) {
      return (
        <div key={i} className="flex gap-2 ml-1 my-0.5">
          <span className="text-text-tertiary mt-0.5">{numberedMatch[1]}.</span>
          <span>{renderInline(numberedMatch[2])}</span>
        </div>
      )
    }

    if (line.trim() === '') {
      return <div key={i} className="h-2" />
    }

    return <p key={i} className="my-0.5">{renderInline(line)}</p>
  })
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    const boldMatch = part.match(/^\*\*([^*]+)\*\*$/)
    if (boldMatch) {
      return <strong key={i} className="font-semibold text-text-primary">{boldMatch[1]}</strong>
    }
    return <span key={i}>{part}</span>
  })
}

function TypingIndicator() {
  return (
    <motion.div
      variants={messageVariants}
      initial="hidden"
      animate="visible"
      className="flex items-start gap-3 max-w-[80%]"
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-surface-tertiary flex items-center justify-center">
        <Bot className="w-4 h-4 text-accent-purple" />
      </div>
      <div className="rounded-2xl bg-surface-secondary border border-border-primary px-5 py-4">
        <div className="flex gap-1.5 items-center h-5">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-2 h-2 rounded-full bg-text-tertiary"
              animate={{ opacity: [0.3, 1, 0.3], scale: [0.85, 1, 0.85] }}
              transition={{
                duration: 1.2,
                repeat: Infinity,
                delay: i * 0.2,
                ease: 'easeInOut' as const,
              }}
            />
          ))}
        </div>
      </div>
    </motion.div>
  )
}

function FilterDropdown({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: string[]
  value: string | null
  onChange: (val: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  if (value) {
    return (
      <button
        onClick={() => onChange(null)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-accent-blue/30 bg-accent-blue/10 text-accent-blue text-sm font-medium transition-colors hover:bg-accent-blue/15"
      >
        <span className="truncate max-w-[140px]">{value}</span>
        <X className="w-3.5 h-3.5 flex-shrink-0" />
      </button>
    )
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border-primary text-text-secondary text-sm font-medium transition-colors hover:bg-surface-hover hover:text-text-primary"
      >
        {label}
        <ChevronDown className="w-3.5 h-3.5" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="absolute bottom-full mb-2 left-0 min-w-[180px] max-h-[240px] overflow-y-auto rounded-xl border border-border-primary bg-surface-elevated backdrop-blur-xl shadow-2xl z-50"
          >
            {options.map((opt) => (
              <button
                key={opt}
                onClick={() => {
                  onChange(opt)
                  setOpen(false)
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:bg-surface-hover hover:text-text-primary transition-colors first:rounded-t-xl last:rounded-b-xl"
              >
                {opt}
              </button>
            ))}
            {options.length === 0 && (
              <div className="px-4 py-3 text-sm text-text-quaternary">No options</div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function PolicyAssistant() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [payerFilter, setPayerFilter] = useState<string | null>(null)
  const [medicationFilter, setMedicationFilter] = useState<string | null>(null)
  const [payers, setPayers] = useState<string[]>([])
  const [medications, setMedications] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.getPolicyBank().then((policies: PolicyBankItem[]) => {
      const uniquePayers = [...new Set(policies.map((p) => p.payer))].sort()
      const uniqueMeds = [...new Set(policies.map((p) => p.medication))].sort()
      setPayers(uniquePayers)
      setMedications(uniqueMeds)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const sendMessage = async (text: string) => {
    const question = text.trim()
    if (!question || loading) return

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: question }])
    setLoading(true)

    try {
      const res = await api.queryAssistant(
        question,
        payerFilter || undefined,
        medicationFilter || undefined
      )
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: res.answer,
          follow_ups: res.follow_up_questions,
        },
      ])
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `I encountered an error processing your request: ${err.message || 'Unknown error'}. Please try again.`,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    sendMessage(input)
  }

  const handleSuggestion = (suggestion: string) => {
    sendMessage(suggestion)
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex flex-col h-full relative">
      <div className="flex-1 overflow-y-auto px-6 pt-6 pb-40">
        {!hasMessages ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] as const }}
            className="flex flex-col items-center justify-center h-full text-center"
          >
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-accent-purple/20 via-accent-blue/20 to-accent-green/10 flex items-center justify-center mb-6 border border-border-primary">
              <Sparkles className="w-10 h-10 text-accent-purple" />
            </div>
            <h1 className="text-3xl font-semibold text-text-primary tracking-tight mb-2">
              Policy Assistant
            </h1>
            <p className="text-text-tertiary text-base mb-10 max-w-md">
              Ask anything about your payer policies
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl w-full">
              {SUGGESTIONS.map((s, i) => (
                <motion.button
                  key={s}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{
                    delay: 0.3 + i * 0.08,
                    duration: 0.4,
                    ease: [0.25, 0.46, 0.45, 0.94] as const,
                  }}
                  onClick={() => handleSuggestion(s)}
                  className="text-left px-4 py-3.5 rounded-2xl border border-border-primary bg-surface-secondary/60 text-sm text-text-secondary hover:bg-surface-hover hover:text-text-primary transition-all duration-200 hover:border-border-hover"
                >
                  {s}
                </motion.button>
              ))}
            </div>
          </motion.div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-5">
            <AnimatePresence initial={false}>
              {messages.map((msg, i) => (
                <motion.div
                  key={i}
                  variants={messageVariants}
                  initial="hidden"
                  animate="visible"
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {msg.role === 'assistant' && (
                    <div className="flex items-start gap-3 max-w-[85%]">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-surface-tertiary flex items-center justify-center mt-1">
                        <Bot className="w-4 h-4 text-accent-purple" />
                      </div>
                      <div className="space-y-3">
                        <div className="rounded-2xl rounded-tl-lg bg-surface-secondary border border-border-primary px-5 py-4 text-sm text-text-secondary leading-relaxed">
                          {renderFormattedText(msg.content)}
                        </div>
                        {msg.follow_ups && msg.follow_ups.length > 0 && (
                          <div className="flex flex-wrap gap-2 pl-1">
                            {msg.follow_ups.map((fq) => (
                              <button
                                key={fq}
                                onClick={() => handleSuggestion(fq)}
                                className="px-3 py-1.5 rounded-full border border-border-primary bg-surface-secondary/40 text-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary transition-all duration-200"
                              >
                                {fq}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  {msg.role === 'user' && (
                    <div className="max-w-[75%]">
                      <div className="rounded-2xl rounded-br-lg bg-accent-blue px-5 py-3.5 text-sm text-white leading-relaxed">
                        {msg.content}
                      </div>
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
            {loading && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-surface-primary via-surface-primary/95 to-transparent pt-8 pb-6 px-6">
        <div className="max-w-3xl mx-auto space-y-3">
          <div className="flex items-center gap-2 px-1">
            <FilterDropdown
              label="Payer"
              options={payers}
              value={payerFilter}
              onChange={setPayerFilter}
            />
            <FilterDropdown
              label="Medication"
              options={medications}
              value={medicationFilter}
              onChange={setMedicationFilter}
            />
          </div>

          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-3 rounded-2xl border border-border-primary bg-surface-secondary/80 backdrop-blur-xl px-4 py-3 shadow-lg shadow-black/20 transition-colors focus-within:border-border-hover"
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about policies..."
              disabled={loading}
              className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-quaternary outline-none disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-blue flex items-center justify-center transition-all duration-200 hover:bg-accent-blue-hover disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ArrowUp className="w-4 h-4 text-white" />
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
