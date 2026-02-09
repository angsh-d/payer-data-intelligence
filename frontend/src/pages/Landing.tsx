import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  Archive,
  GitCompareArrows,
  MessageSquare,
  ArrowRight,
  Sparkles,
  Shield,
  Zap,
  Brain,
} from 'lucide-react'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] as const },
  }),
}

const experiences = [
  {
    icon: LayoutDashboard,
    title: 'Command Center',
    description: 'Real-time dashboard with policy quality metrics, activity feeds, and coverage status across all payers.',
    path: '/dashboard',
    color: 'text-accent-blue',
    bg: 'bg-accent-blue/8',
  },
  {
    icon: Archive,
    title: 'Policy Vault',
    description: 'Centralized policy bank with drag-and-drop upload, automated digitalization, and structured data extraction.',
    path: '/vault',
    color: 'text-accent-green',
    bg: 'bg-accent-green/8',
  },
  {
    icon: GitCompareArrows,
    title: 'Policy Intelligence',
    description: 'AI-powered semantic version comparison that detects meaningful coverage changes across policy updates.',
    path: '/intelligence',
    color: 'text-accent-purple',
    bg: 'bg-accent-purple/8',
  },
  {
    icon: MessageSquare,
    title: 'Policy Assistant',
    description: 'Conversational AI that answers complex policy questions with citations and evidence-based reasoning.',
    path: '/assistant',
    color: 'text-accent-amber',
    bg: 'bg-accent-amber/8',
  },
]

const howItWorks = [
  {
    step: '01',
    icon: Archive,
    title: 'Ingest & Digitalize',
    description: 'Upload payer policy documents in any format. Our multi-pass extraction pipeline converts unstructured PDFs into structured, queryable clinical criteria.',
  },
  {
    step: '02',
    icon: Brain,
    title: 'AI-Powered Analysis',
    description: 'Large language models semantically match and compare criteria across policy versions, identifying meaningful coverage changes that impact patient access.',
  },
  {
    step: '03',
    icon: Zap,
    title: 'Actionable Intelligence',
    description: 'Surface high-impact changes, generate diff summaries with severity ratings, and provide evidence-based recommendations for your medical affairs team.',
  },
]

export default function Landing() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-surface-primary">
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-surface-secondary/60 via-transparent to-transparent pointer-events-none" />
        <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[800px] h-[800px] rounded-full bg-accent-blue/[0.03] blur-3xl pointer-events-none" />

        <div className="relative max-w-5xl mx-auto px-6 pt-24 pb-20 text-center">
          <motion.div
            custom={0}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent-blue/8 border border-accent-blue/15 mb-8"
          >
            <Sparkles className="w-3.5 h-3.5 text-accent-blue" />
            <span className="text-xs font-medium text-accent-blue tracking-wide">AI-Powered Policy Intelligence</span>
          </motion.div>

          <motion.h1
            custom={1}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="text-5xl sm:text-6xl font-bold text-text-primary tracking-tight leading-[1.1] mb-6"
          >
            Transform payer policies
            <br />
            <span className="text-text-tertiary">into actionable intelligence</span>
          </motion.h1>

          <motion.p
            custom={2}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="max-w-2xl mx-auto text-lg text-text-secondary leading-relaxed mb-10"
          >
            Digitalize, version, compare, and query payer coverage policies with AI.
            Detect meaningful changes across updates and surface insights that
            accelerate market access decisions.
          </motion.p>

          <motion.div
            custom={3}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="flex items-center justify-center gap-4"
          >
            <button
              onClick={() => navigate('/dashboard')}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-accent-blue text-white text-[15px] font-medium hover:bg-accent-blue-hover transition-colors duration-200 shadow-sm"
            >
              Open Platform
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => {
                document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' })
              }}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-surface-secondary text-text-primary text-[15px] font-medium hover:bg-surface-tertiary transition-colors duration-200"
            >
              How It Works
            </button>
          </motion.div>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-24">
        <motion.div
          custom={4}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="text-center mb-14"
        >
          <h2 className="text-3xl font-bold text-text-primary tracking-tight mb-3">Four Core Experiences</h2>
          <p className="text-text-secondary text-base">Everything you need to manage and analyze payer coverage policies</p>
        </motion.div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {experiences.map((exp, i) => (
            <motion.button
              key={exp.path}
              custom={5 + i}
              variants={fadeUp}
              initial="hidden"
              animate="visible"
              onClick={() => navigate(exp.path)}
              className="group relative flex flex-col items-start text-left p-6 rounded-2xl bg-surface-secondary/60 border border-border-secondary hover:border-border-hover hover:bg-surface-secondary transition-all duration-300"
            >
              <div className={`flex items-center justify-center w-10 h-10 rounded-xl ${exp.bg} mb-4`}>
                <exp.icon className={`w-5 h-5 ${exp.color}`} />
              </div>
              <h3 className="text-[15px] font-semibold text-text-primary mb-1.5">{exp.title}</h3>
              <p className="text-[13px] text-text-secondary leading-relaxed">{exp.description}</p>
              <div className="mt-4 flex items-center gap-1.5 text-xs font-medium text-accent-blue opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                Explore <ArrowRight className="w-3 h-3" />
              </div>
            </motion.button>
          ))}
        </div>
      </section>

      <section id="how-it-works" className="bg-surface-secondary/40 border-y border-border-secondary">
        <div className="max-w-5xl mx-auto px-6 py-24">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-text-primary tracking-tight mb-3">How It Works</h2>
            <p className="text-text-secondary text-base">From raw documents to strategic intelligence in three steps</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {howItWorks.map((step, i) => (
              <motion.div
                key={step.step}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-50px' }}
                transition={{ delay: i * 0.15, duration: 0.5 }}
                className="relative"
              >
                <span className="text-[64px] font-bold text-text-quaternary/30 leading-none">{step.step}</span>
                <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-accent-blue/8 mt-2 mb-4">
                  <step.icon className="w-5 h-5 text-accent-blue" />
                </div>
                <h3 className="text-[15px] font-semibold text-text-primary mb-2">{step.title}</h3>
                <p className="text-[13px] text-text-secondary leading-relaxed">{step.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 py-24">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {[
            { icon: Shield, title: 'Enterprise Security', desc: 'All policy data encrypted at rest and in transit with role-based access controls.' },
            { icon: Brain, title: 'LLM-First Design', desc: 'Semantic matching powered by large language models — no brittle regex or keyword rules.' },
            { icon: Zap, title: 'Real-Time Updates', desc: 'Automated change detection alerts when payers update coverage criteria.' },
          ].map((item, i) => (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.4 }}
              className="flex flex-col items-start p-5 rounded-2xl border border-border-secondary"
            >
              <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-surface-secondary mb-3">
                <item.icon className="w-4.5 h-4.5 text-text-secondary" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary mb-1">{item.title}</h3>
              <p className="text-[13px] text-text-secondary leading-relaxed">{item.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <footer className="border-t border-border-secondary py-8 px-6">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-xs text-text-quaternary">&copy; {new Date().getFullYear()} Saama Technologies. All rights reserved.</span>
          <span className="text-xs text-text-quaternary">Payer Intelligence Platform v1.0</span>
        </div>
      </footer>
    </div>
  )
}
