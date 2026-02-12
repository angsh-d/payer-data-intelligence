# Payer Data Intelligence — Solution Outline

## What It Is

Payer Data Intelligence (PDI) is an AI-native platform that transforms unstructured payer policy documents into actionable coverage intelligence. It automates the work that prior authorization teams do manually today — reading policy PDFs, extracting coverage criteria, tracking policy changes across years, assessing patient eligibility, and building appeal strategies when claims are denied.

The platform is built entirely on an LLM-first approach: every analytical task (extraction, validation, comparison, reasoning) is performed by large language models rather than rule-based systems.

---

## Capabilities

### 1. Policy Digitalization

Upload a payer policy PDF and the platform converts it into structured, machine-readable coverage criteria through a **3-pass LLM pipeline**:

- **Pass 1 — Extraction:** Reads the full policy document and extracts every atomic coverage criterion (diagnoses, lab requirements, step therapy, age limits, prescriber restrictions, safety screenings, exclusions) into a structured schema with clinical codes, thresholds, and logical groupings.
- **Pass 2 — Validation:** A second model cross-checks the extraction against the original document for completeness, accuracy, and logical correctness. Flags missing criteria, incorrect thresholds, and structural issues.
- **Pass 3 — Reference Validation:** Validates all extracted clinical codes (ICD-10, HCPCS, CPT, NDC) against reference databases.

The output is a fully digitized policy with atomic criteria, logical groups (AND/OR/NOT), indication mappings, step therapy requirements, exclusions, and provenance tracking back to source page numbers.

### 2. Policy Vault & Version Management

A centralized library for all ingested policy documents:

- **Drag-and-drop upload** with automatic metadata inference (payer name, medication, effective date extracted from the document itself)
- **Multi-version support** — upload the same policy across different years and the platform maintains a version timeline
- **Side-by-side view** — browse digitized criteria alongside the original PDF with page-level linking
- **Searchable, filterable** — find policies by medication, payer, quality score, or effective year

### 3. Formulary Intelligence (Version Diff & Change Analysis)

Compare any two versions of a policy to understand what changed:

- **Semantic criterion matching** — criteria are matched by clinical meaning, not by ID, since each version is independently digitalized
- **Severity-coded changes** — every change is classified as breaking (could flip approvals to denials), material (significant but non-breaking), or minor (editorial)
- **LLM-generated executive summary** — a natural language explanation of what changed, who is affected, and what actions to take
- **CSV export** of all changes for downstream reporting

### 4. Patient Impact Analysis

When a policy changes, automatically assess the impact on active patient cases:

- **Evaluates each patient** against both the old and new policy versions
- **Identifies verdict flips** — patients who were previously approved but would now be denied under the new criteria
- **Risk scoring** — categorizes patients as verdict flip, at risk, improved, or no impact
- **Actionable recommendations** — specific next steps for each affected patient (e.g., "gather updated lab results", "file grandfathering request")

### 5. Cross-Payer Analysis

Compare coverage criteria for the same medication across multiple payers:

- **Restrictiveness ranking** — which payer is most/least restrictive, with rationale
- **Dimension-by-dimension comparison** — step therapy, indications, exclusions, documentation requirements
- **Unique requirements** — criteria that only one payer requires, with clinical impact assessment
- **Coverage gaps** — indications covered by some payers but not others

### 6. Coverage Assessment

Evaluate a specific patient's eligibility against a specific payer's policy:

- **Criterion-by-criterion assessment** — each policy requirement evaluated against patient data with confidence scoring
- **Documentation gap identification** — exactly what's missing, who needs to provide it, and priority ranking
- **Conservative decision model** — the system will recommend approve, pend, or escalate to human review. It will **never** recommend denial (following healthcare AI safety principles — only humans may deny coverage).
- **Step therapy evaluation** — verifies prior treatment history against step therapy requirements including drug names, durations, and failure criteria

### 7. Appeal Strategy & Letter Generation

When a prior authorization is denied, generate a comprehensive appeal:

- **Denial analysis** — identifies the denial category, policy gaps exploited, and weaknesses in the denial reasoning
- **Multi-layered strategy** — primary argument, supporting arguments, clinical evidence citations, and specific policy section references
- **Peer-to-peer talking points** — key arguments for medical director discussions
- **Appeal letter drafting** — a complete, physician-ready appeal letter with clinical evidence, policy citations, and formal structure
- **Success likelihood scoring** — estimated probability of appeal success with reasoning

### 8. Policy Assistant (Conversational Q&A)

A natural language interface for querying policy data:

- **Ask questions in plain English** — "What step therapy does BCBS require for infliximab?", "How do Cigna and UHC differ on Spinraza coverage?"
- **Filter by payer and medication** — scope queries to specific policies
- **Conversation memory** — follow-up questions understand prior context within a session
- **Streaming responses** — answers stream in real-time with citations to specific criterion IDs
- **Semantic caching** — similar questions serve cached answers to reduce cost and latency
- **RAG retrieval** — answers grounded in actual policy text chunks via vector search

### 9. Operations Dashboard

At-a-glance view of the policy intelligence program:

- **Health score** — aggregate digitalization quality across all policies
- **Key metrics** — total policies, versions, payers tracked, system health
- **Recent activity** — latest policy uploads and updates
- **LLM usage metrics** — token consumption, latency, and cost tracking across all model providers

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface                           │
│                                                             │
│   Dashboard    Policy Vault    Formulary       Policy       │
│                                Intelligence    Assistant    │
│                                                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
              REST / SSE / WebSocket
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  Application Services                        │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐│
│  │   Coverage    │ │   Appeal     │ │   Cross-Payer        ││
│  │   Reasoner    │ │   Agent      │ │   Analyzer           ││
│  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘│
│         │                │                     │            │
│  ┌──────▼────────────────▼─────────────────────▼───────────┐│
│  │              Policy Digitalization Engine                ││
│  │                                                         ││
│  │   Upload &         3-Pass           Version    Policy   ││
│  │   Metadata    ──▶  Pipeline    ──▶  Diff  ──▶ Impact   ││
│  │   Inference        (Extract/        Analysis   Analysis ││
│  │                     Validate/                           ││
│  │                     Reference)                          ││
│  └─────────────────────────┬───────────────────────────────┘│
│                            │                                │
│  ┌─────────────────────────▼───────────────────────────────┐│
│  │              LLM Gateway (Task Router)                   ││
│  │                                                         ││
│  │   Routes each task to the right model:                  ││
│  │                                                         ││
│  │   Claude ─── Clinical reasoning, appeals, Q&A           ││
│  │              (no fallback, temperature 0.0)             ││
│  │                                                         ││
│  │   Gemini ─── Extraction, summarization, embeddings      ││
│  │              (falls back to Azure OpenAI)               ││
│  │                                                         ││
│  │   Azure ──── Fallback provider only                     ││
│  └─────────────────────────────────────────────────────────┘│
│                            │                                │
│  ┌─────────────────────────▼───────────────────────────────┐│
│  │              Persistence & Caching                       ││
│  │                                                         ││
│  │   Policy Store ── Versioned policies + digitized JSON   ││
│  │   Diff Cache ──── LLM-generated change summaries        ││
│  │   Vector Store ── RAG embeddings for Q&A retrieval      ││
│  │   Semantic Cache ─ Q&A response deduplication           ││
│  │   Metrics Store ── LLM token/cost tracking              ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Supporting Services                         ││
│  │                                                         ││
│  │   File Watcher ── Auto-digitalize new policy files      ││
│  │   WebSocket ───── Real-time pipeline progress           ││
│  │   Prompt System ─ Versioned, externalized LLM prompts   ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## Design Principles

**LLM-First** — Every analytical task is performed by a language model. No rule-based extraction, no regex parsing, no template-based summaries. The right model is chosen for each job based on its strengths.

**Clinical Safety** — The system never recommends denial. Coverage decisions that could result in denial are always escalated to human reviewers. Prompts include hallucination guards to prevent fabrication of clinical codes or policy citations.

**Multi-Model, Task-Routed** — Claude handles clinical reasoning where accuracy is non-negotiable (no fallback). Gemini handles high-volume extraction and summarization (with Azure OpenAI as fallback). Routing is config-driven — no code changes needed to reassign tasks.

**Multi-Pass Validation** — A single LLM pass is insufficient for clinical-grade accuracy. The 3-pass pipeline (extract, validate, reference-check) uses model diversity to catch errors.

**Externalized Prompts** — All LLM prompts are versioned `.txt` files, not hardcoded in application code. This allows prompt iteration without code deployments and enables non-developers to modify prompt behavior.
