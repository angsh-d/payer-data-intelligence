import { motion } from 'framer-motion'
import {
  Network,
  Brain,
  GitCompareArrows,
  TrendingUp,
  Scale,
  MessageSquare,
  FileSearch,
  ShieldCheck,
  Microscope,
  Stethoscope,
  Route,
  type LucideIcon,
} from 'lucide-react'

interface AgentNode {
  id: string
  name: string
  role: string
  description: string
  provider: 'claude' | 'gemini' | 'azure' | 'deterministic'
  capabilities: string[]
  icon: LucideIcon
  group: 'orchestration' | 'intelligence' | 'pipeline'
  receives?: string
  produces?: string
}

const providerLabel: Record<string, string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  azure: 'Azure OpenAI',
  deterministic: 'Rule-based',
}

const agents: AgentNode[] = [
  {
    id: 'gateway',
    name: 'LLM Gateway',
    role: 'Central Orchestrator',
    description: 'Routes tasks to the optimal model based on task category, manages fallback chains, and enforces routing policies from configuration.',
    provider: 'deterministic',
    capabilities: ['Task-based model routing', 'Fallback chain management', 'Provider health monitoring'],
    icon: Route,
    group: 'orchestration',
    receives: 'Task requests from all agents',
    produces: 'Routed LLM responses',
  },
  {
    id: 'reasoner',
    name: 'Policy Reasoner',
    role: 'Coverage Assessment',
    description: 'Evaluates patient coverage against digitalized policy criteria. Performs medication alias resolution and generates structured coverage assessments with no fallback — clinical accuracy is non-negotiable.',
    provider: 'claude',
    capabilities: ['Coverage determination', 'Criterion-level assessment', 'Documentation gap identification'],
    icon: Brain,
    group: 'intelligence',
    receives: 'Patient data + Policy criteria',
    produces: 'CoverageAssessment with criterion scores',
  },
  {
    id: 'differ',
    name: 'Policy Differ',
    role: 'Semantic Version Comparison',
    description: 'Compares two versions of a policy using LLM-powered criteria matching. Detects additions, removals, modifications, and unchanged criteria with semantic understanding beyond text diff.',
    provider: 'gemini',
    capabilities: ['Criteria matching across versions', 'Change classification & severity', 'Semantic diff summaries'],
    icon: GitCompareArrows,
    group: 'intelligence',
    receives: 'Two policy versions (criteria JSON)',
    produces: 'DiffSummary with matched changes',
  },
  {
    id: 'impact',
    name: 'Impact Analyzer',
    role: 'Patient Impact Projection',
    description: 'Projects how policy changes affect individual patients. Uses v1 assessment as baseline and applies diff context to project v2 impact without redundant LLM calls.',
    provider: 'claude',
    capabilities: ['Diff-aware v2 projection', 'Per-patient impact scoring', 'Before/after comparison'],
    icon: TrendingUp,
    group: 'intelligence',
    receives: 'Diff summary + Patient assessments',
    produces: 'Impact analysis per patient',
  },
  {
    id: 'cross-payer',
    name: 'Cross-Payer Analyzer',
    role: 'Multi-Payer Comparison',
    description: 'Compares coverage policies across multiple payers for the same medication. Identifies coverage gaps, commonalities, and payer-specific restrictions.',
    provider: 'claude',
    capabilities: ['Multi-payer criteria comparison', 'Coverage gap analysis', 'Payer restriction mapping'],
    icon: Scale,
    group: 'intelligence',
    receives: 'Multiple payer policies',
    produces: 'Cross-payer comparison matrix',
  },
  {
    id: 'assistant',
    name: 'Policy Assistant',
    role: 'Conversational Q&A',
    description: 'Answers natural language questions about policies with citations and evidence-based reasoning. Maintains context across conversation turns.',
    provider: 'claude',
    capabilities: ['Evidence-based Q&A', 'Citation generation', 'Multi-turn context'],
    icon: MessageSquare,
    group: 'intelligence',
    receives: 'User query + Policy context',
    produces: 'Cited answer with evidence',
  },
  {
    id: 'extractor',
    name: 'Pass 1 — Extractor',
    role: 'Structured Criteria Extraction',
    description: 'First pass of the digitalization pipeline. Converts unstructured policy PDFs into structured clinical criteria JSON using large-context extraction.',
    provider: 'gemini',
    capabilities: ['PDF text extraction', 'Criteria structuring', 'Clinical category classification'],
    icon: FileSearch,
    group: 'pipeline',
    receives: 'Raw policy document (PDF/text)',
    produces: 'RawExtractionResult (structured JSON)',
  },
  {
    id: 'validator',
    name: 'Pass 2 — Validator',
    role: 'Cross-Validation',
    description: 'Validates extracted criteria against the original source document. Catches hallucinations, missing criteria, and extraction errors using a different model than Pass 1.',
    provider: 'claude',
    capabilities: ['Source verification', 'Hallucination detection', 'Completeness checking'],
    icon: ShieldCheck,
    group: 'pipeline',
    receives: 'RawExtractionResult + Source document',
    produces: 'ValidatedExtractionResult',
  },
  {
    id: 'reference',
    name: 'Pass 3 — Reference Validator',
    role: 'Clinical Code Validation',
    description: 'Validates clinical codes (ICD-10, HCPCS, CPT, NDC) referenced in criteria against authoritative code databases. Flags invalid or deprecated codes.',
    provider: 'deterministic',
    capabilities: ['ICD-10 code validation', 'HCPCS/CPT verification', 'NDC cross-reference'],
    icon: Microscope,
    group: 'pipeline',
    receives: 'ValidatedExtractionResult',
    produces: 'Code-validated criteria',
  },
  {
    id: 'codifier',
    name: 'Pass 4 — Clinical Codifier',
    role: 'Clinical Codification',
    description: 'Enriches validated criteria with clinical codes, standard terminology mappings, and codified representations for downstream interoperability.',
    provider: 'gemini',
    capabilities: ['Clinical code assignment', 'Terminology mapping', 'Interoperability enrichment'],
    icon: Stethoscope,
    group: 'pipeline',
    receives: 'Validated criteria',
    produces: 'Fully codified policy JSON',
  },
]

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] as const },
  }),
}

const pipelineAgents = agents.filter((a) => a.group === 'pipeline')
const intelligenceAgents = agents.filter((a) => a.group === 'intelligence')
const gateway = agents.find((a) => a.group === 'orchestration')!

const providers = [
  { id: 'claude', name: 'Claude (Anthropic)', desc: 'Policy reasoning, validation, Q&A — no fallback for clinical accuracy' },
  { id: 'gemini', name: 'Gemini (Google)', desc: 'Extraction, summarization, codification — high-throughput tasks' },
  { id: 'azure', name: 'Azure OpenAI', desc: 'Fallback provider for Gemini failures — ensures pipeline resilience' },
]

function ProviderDot({ provider }: { provider: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-1.5 h-1.5 rounded-full bg-text-quaternary" />
      <span className="text-[11px] text-text-quaternary">{providerLabel[provider]}</span>
    </span>
  )
}

function AgentCard({ agent, index }: { agent: AgentNode; index: number }) {
  return (
    <motion.div
      custom={index}
      variants={fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: '-40px' }}
      className="flex flex-col p-5 rounded-2xl bg-surface-secondary/60 border border-border-secondary hover:border-border-hover hover:-translate-y-0.5 transition-all duration-300"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-surface-tertiary">
          <agent.icon className="w-4.5 h-4.5 text-text-secondary" />
        </div>
        <ProviderDot provider={agent.provider} />
      </div>
      <h3 className="text-[15px] font-semibold text-text-primary mb-0.5">{agent.name}</h3>
      <p className="text-[11px] font-medium text-text-tertiary uppercase tracking-widest mb-2">{agent.role}</p>
      <p className="text-[13px] text-text-secondary leading-relaxed mb-4 flex-1">{agent.description}</p>
      <ul className="space-y-1.5 mb-4">
        {agent.capabilities.map((cap) => (
          <li key={cap} className="flex items-start gap-2 text-[12px] text-text-tertiary">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-text-quaternary shrink-0" />
            {cap}
          </li>
        ))}
      </ul>
      {(agent.receives || agent.produces) && (
        <div className="pt-3 border-t border-border-secondary space-y-1">
          {agent.receives && (
            <p className="text-[11px] text-text-quaternary">
              <span className="font-medium text-text-tertiary">In:</span> {agent.receives}
            </p>
          )}
          {agent.produces && (
            <p className="text-[11px] text-text-quaternary">
              <span className="font-medium text-text-tertiary">Out:</span> {agent.produces}
            </p>
          )}
        </div>
      )}
    </motion.div>
  )
}

function PipelineFlow() {
  return (
    <div className="flex items-center gap-3 overflow-x-auto pb-2">
      {pipelineAgents.map((agent, i) => (
        <div key={agent.id} className="flex items-center gap-3 shrink-0">
          <div className="flex flex-col items-center gap-2 min-w-[140px]">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-surface-tertiary">
              <agent.icon className="w-5 h-5 text-text-secondary" />
            </div>
            <span className="text-[12px] font-semibold text-text-primary text-center">{agent.name}</span>
            <ProviderDot provider={agent.provider} />
          </div>
          {i < pipelineAgents.length - 1 && (
            <div className="flex items-center">
              <div className="w-8 h-px bg-border-hover" />
              <div className="w-0 h-0 border-t-[3px] border-t-transparent border-b-[3px] border-b-transparent border-l-[5px] border-l-border-hover" />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function Agents() {
  return (
    <div className="min-h-screen bg-surface-primary">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-surface-secondary/60 via-transparent to-transparent pointer-events-none" />
        <div className="relative max-w-5xl mx-auto px-6 pt-24 pb-16 text-center">
          <motion.div
            custom={0}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-surface-secondary border border-border-hover mb-8"
          >
            <Network className="w-3.5 h-3.5 text-text-secondary" />
            <span className="text-xs font-medium text-text-secondary tracking-wide">System Architecture</span>
          </motion.div>

          <motion.h1
            custom={1}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="text-5xl font-bold text-text-primary tracking-tight leading-[1.1] mb-6"
          >
            Multi-Agent Architecture
          </motion.h1>

          <motion.p
            custom={2}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="max-w-2xl mx-auto text-lg text-text-secondary leading-relaxed"
          >
            Ten specialized agents orchestrated through a central gateway,
            each optimized for a specific stage of policy intelligence.
          </motion.p>
        </div>
      </section>

      {/* Central Hub */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <motion.div
          custom={3}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="flex flex-col items-center"
        >
          <div className="flex flex-col items-center p-6 rounded-2xl bg-surface-secondary/60 border border-border-hover w-full max-w-md">
            <div className="flex items-center justify-center w-12 h-12 rounded-2xl bg-surface-tertiary mb-3">
              <gateway.icon className="w-6 h-6 text-text-secondary" />
            </div>
            <h3 className="text-[17px] font-semibold text-text-primary mb-1">{gateway.name}</h3>
            <p className="text-[11px] font-medium text-text-tertiary uppercase tracking-widest mb-2">{gateway.role}</p>
            <p className="text-[13px] text-text-secondary leading-relaxed text-center mb-3">{gateway.description}</p>
            <div className="flex items-center gap-4">
              {gateway.capabilities.map((cap) => (
                <span key={cap} className="text-[11px] text-text-quaternary">{cap}</span>
              ))}
            </div>
          </div>

          {/* Connection lines down */}
          <div className="flex items-center gap-20 my-4">
            <div className="flex flex-col items-center">
              <div className="w-px h-8 bg-border-hover" />
              <div className="w-0 h-0 border-l-[3px] border-l-transparent border-r-[3px] border-r-transparent border-t-[5px] border-t-border-hover" />
            </div>
            <div className="flex flex-col items-center">
              <div className="w-px h-8 bg-border-hover" />
              <div className="w-0 h-0 border-l-[3px] border-l-transparent border-r-[3px] border-r-transparent border-t-[5px] border-t-border-hover" />
            </div>
          </div>

          <div className="flex items-start gap-12 text-[11px] font-medium text-text-tertiary uppercase tracking-widest">
            <span>Policy Intelligence</span>
            <span>Digitalization Pipeline</span>
          </div>
        </motion.div>
      </section>

      {/* Pipeline Section */}
      <section className="bg-surface-secondary/40 border-y border-border-secondary">
        <div className="max-w-5xl mx-auto px-6 py-20">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="mb-10"
          >
            <p className="text-xs font-medium text-text-tertiary uppercase tracking-widest mb-3">Digitalization Pipeline</p>
            <h2 className="text-3xl font-bold text-text-primary tracking-tight mb-2">Four-Pass Processing</h2>
            <p className="text-text-secondary text-base">Sequential pipeline that transforms raw policy documents into validated, codified clinical criteria.</p>
          </motion.div>

          {/* Pipeline flow diagram */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1, duration: 0.5 }}
            className="flex justify-center mb-14 p-6 rounded-2xl bg-surface-primary/80 border border-border-secondary"
          >
            <PipelineFlow />
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {pipelineAgents.map((agent, i) => (
              <AgentCard key={agent.id} agent={agent} index={i + 4} />
            ))}
          </div>
        </div>
      </section>

      {/* Intelligence Agents */}
      <section className="max-w-5xl mx-auto px-6 py-20">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="mb-10"
        >
          <p className="text-xs font-medium text-text-tertiary uppercase tracking-widest mb-3">Policy Intelligence</p>
          <h2 className="text-3xl font-bold text-text-primary tracking-tight mb-2">Analytical Agents</h2>
          <p className="text-text-secondary text-base">Independent agents that reason over digitalized policies to deliver coverage insights, comparisons, and answers.</p>
        </motion.div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {intelligenceAgents.map((agent, i) => (
            <AgentCard key={agent.id} agent={agent} index={i + 8} />
          ))}
        </div>
      </section>

      {/* LLM Providers */}
      <section className="bg-surface-secondary/40 border-y border-border-secondary">
        <div className="max-w-5xl mx-auto px-6 py-20">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="mb-10"
          >
            <p className="text-xs font-medium text-text-tertiary uppercase tracking-widest mb-3">Backing Services</p>
            <h2 className="text-3xl font-bold text-text-primary tracking-tight mb-2">LLM Providers</h2>
            <p className="text-text-secondary text-base">Task-optimized model selection ensures each agent uses the best model for its specific workload.</p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {providers.map((prov, i) => (
              <motion.div
                key={prov.id}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.4 }}
                className="flex flex-col items-start p-5 rounded-2xl bg-surface-primary/80 border border-border-secondary"
              >
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-2 h-2 rounded-full bg-text-quaternary" />
                  <h3 className="text-sm font-semibold text-text-primary">{prov.name}</h3>
                </div>
                <p className="text-[13px] text-text-secondary leading-relaxed">{prov.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border-secondary py-8 px-6">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-xs text-text-quaternary">&copy; {new Date().getFullYear()} Saama Technologies. All rights reserved.</span>
          <span className="text-xs text-text-quaternary">Formulary Intelligence Agent v1.0</span>
        </div>
      </footer>
    </div>
  )
}
