> **⚡ Runs on anything:** 4GB RAM, i3 processor, no GPU required. Pure Python, zero native compilation.

# 🌌 F.R.I.D.A.Y. — Autonomous Cognitive AI Operating System for General Intelligence

<p align="center">
  <img src="assets/logo.png" alt="Friday Logo" width="400" />
</p>

<p align="center">
  <a href="https://github.com/subhansh-dev/Friday/stargazers">
    <img src="https://img.shields.io/github/stars/subhansh-dev/Friday?style=flat" alt="Stars" />
  </a>
  <a href="https://github.com/subhansh-dev/Friday/forks">
    <img src="https://img.shields.io/github/forks/subhansh-dev/Friday?style=flat" alt="Forks" />
  </a>
  <a href="https://github.com/subhansh-dev/Friday/issues">
    <img src="https://img.shields.io/github/issues/subhansh-dev/Friday" alt="Issues" />
  </a>
  <a href="https://github.com/subhansh-dev/Friday/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/subhansh-dev/Friday" alt="License" />
  </a>
  <a href="https://python.org/versions/3.11">
    <img src="https://img.shields.io/badge/Python-3.12+-blue" alt="Python" />
  </a>
</p>

-> Friday is still experimental and also expect some bugs as im a solo developer with hardware limitations🥀<-

> **⚠️ IMPORTANT — READ BEFORE USE**
>
> F.R.I.D.A.Y. is an autonomous cognitive AI operating system with capabilities spanning research, creative writing, document analysis, coding, system control, and security analysis. It includes **optional** cybersecurity features (vulnerability scanning, penetration testing tools) that are intended **ONLY** for:
> - Authorized security research on systems you own or have explicit permission to test
> - Educational purposes in controlled environments
> - Defensive security operations on your own infrastructure
>
> **The creator (Subhansh) does NOT take any responsibility for:**
> - Any illegal or unauthorized use of F.R.I.D.A.Y.
> - Any damage, data loss, or legal consequences caused by users cloning or using this software
> - Any exploitation of systems without proper authorization
>
> **By using this software, you agree that:**
> - You will ONLY use it for lawful purposes
> - You will obtain proper authorization before testing any system
> - You accept FULL responsibility for any consequences of your actions
> - The creator cannot be held liable for any misuse
>
> See the [Legal Disclaimer & Warning](#%EF%B8%8F-legal-disclaimer--warning) section for complete details.

---

## 📋 Table of Contents

- [About F.R.I.D.A.Y](#-about-friday)
- [Motivation](#-motivation)
- [Why F.R.I.D.A.Y](#-why-friday)
- [Features At A Glance](#-features-at-a-glance)
- [Cognitive Architecture](#-cognitive-architecture)
- [Core Brain Systems (50 Modules)](#-core-brain-systems-50-modules)
- [Autonomous Research Agent](#-autonomous-research-agent)
- [Creative Studio](#-creative-studio)
- [Document Intelligence](#-document-intelligence)
- [Cognitive Coding Engine](#-cognitive-coding-engine)
- [Cybersecurity Pipeline](#%EF%B8%8F-cybersecurity-pipeline)
- [Skill Engine (56 Tools)](#-skill-engine-56-tools)
- [Voice & Emotion System](#%EF%B8%8F-voice--emotion-system)
- [Memory Architecture](#-memory-architecture)
- [Holo Earth — Gesture-Controlled Google Earth](#-holo-earth--gesture-controlled-google-earth)
- [Holo Builder — Iron Man AR](#%EF%B8%8F-holo-builder--iron-man-ar-builder)
- [Gesture Music Control](#-gesture-music-control)
- [Project Structure](#-project-structure)
- [Tech Stack](#-tech-stack)
- [Installation](#-installation)
- [Configuration](#%EF%B8%8F-configuration)
- [Usage](#-usage)
- [Cybersecurity Confirmation Protocol](#-cybersecurity-confirmation-protocol)
- [Legal Disclaimer & Warning](#%EF%B8%8F-legal-disclaimer--warning)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌟 About F.R.I.D.A.Y

**F.R.I.D.A.Y.** is a next-generation **Autonomous Cognitive AI Operating System** — not a chatbot, not a wrapper around an API. A full cognitive architecture with real-time voice interaction, 38 cognitive modules, autonomous research and creative writing engines, document intelligence, 56 tool actions, neural memory systems, and autonomous decision-making.

**95,000+ lines of Python. 180+ source files. Zero shortcuts.** *(~115,000 lines total counting everything — configs, docs, assets, the works.)*

Built as the spiritual successor to Jarvis-MT67, Friday represents a new paradigm in AI assistance — not just responding to commands, but actively learning, anticipating needs, and evolving with each interaction.

### What Makes It Different

| Traditional AI Assistants | F.R.I.D.A.Y. |
|---------------------------|---------------|
| Stateless — forgets you every session | **Neural memory** with Hebbian learning across sessions |
| Reactive — waits for commands | **Proactive** — anticipates needs, idle exploration, autonomous goal pursuit |
| Single model, single purpose | **50 cognitive modules** coordinating via Global Workspace |
| No self-awareness | **Self-model** + **introspection engine** with confidence calibration & bias detection |
| No learning from mistakes | **Dreaming system** replays experiences, **code evolution** enables self-improvement |
| Generic responses | **Theory of mind** models the user's expertise, intent, and emotional state |
| One voice, one tone | **10 voice emotions** with natural accent |
| Can't research or create | **Autonomous research**, **creative writing**, **document analysis** built-in |
| Manual security scanning | **Dual security pipelines** (Mythos + Cyber Reasoning) |
| Sequential agent execution | **Multi-agent orchestrator** — run 30 agents in parallel, debate, pipeline, or swarm mode |
| No long-term planning | **Autonomous planner** with MCTS-inspired goal decomposition and replanning |
| Static memory | **Memory consolidation** (episodic→semantic), **associative memory** (spreading activation), **predictive memory** (anticipatory recall) |
| No cross-domain reasoning | **Abstraction engine** — analogical transfer, first principles, counterfactual reasoning |
| No world awareness | **World simulation** — real-time event tracking, trend detection, counterfactual modeling |

---

## 🎯 Motivation

Contemporary AI assistants share a fundamental limitation: they are stateless. Each session begins from zero — no memory of prior interactions, no model of the user, no awareness of their own strengths and weaknesses. They are reactive, waiting for commands rather than anticipating needs. They are single-model systems, routing everything through one inference call regardless of task complexity.

F.R.I.D.A.Y. addresses these limitations by implementing a cognitive architecture that mirrors aspects of human cognition:

| Dimension | Conventional Assistants | F.R.I.D.A.Y. |
|-----------|------------------------|---------------|
| **Memory** | Stateless per session | Persistent neural memory with Hebbian learning and 72-hour synaptic decay |
| **Initiative** | Reactive — waits for commands | Proactive — anticipates needs, explores during idle time |
| **Reasoning** | Single-pass generation | Multi-pass: cognitive gating routes simple tasks to System 1, complex tasks to full planning-simulation-reflection pipeline |
| **Self-awareness** | None | Tracks capabilities, confidence scores, and growth trajectories across sessions |
| **Learning** | No feedback loop | Error-driven updates, Q-learning for tool selection, experience replay, dreaming-based consolidation |
| **Security** | Generic content filtering | Dual-pipeline adversarial verification with 3-round skepticism and 5-axis grading |
| **Voice** | Monotone TTS | 10 emotion states with dynamic context-sensitive switching |

---

### 🧬 Cognitive Architecture Protocol

F.R.I.D.A.Y. doesn't just have brain modules — she actively **uses** them. Every session follows a cognitive cycle:

```
Wake → Recall Memory → Assess Complexity → Route to System 1 or System 2
                                                    ↓
System 1 (simple):  Immediate response, single tool call
System 2 (complex): Plan → Simulate → Execute → Verify → Reflect → Learn
                                                    ↓
                              Record Experience → Update Self-Model → Grow
```

**Key Cognitive Behaviors:**
- **Cognitive Gating** — Automatically classifies tasks as simple (System 1, instant) or complex (System 2, full pipeline)
- **Thinking Loop** — Multi-pass reasoning for hard problems: understand → plan → refine (up to 3 passes, skipped for simple requests)
- **Module Competition** — Modules bid for processing rights instead of rigid orchestration (Minsky Society of Mind)
- **6 Memory Systems** — Neural, episodic, vector, procedural, working, and global workspace — all actively used
- **Learning Engine** — Records lessons from every task, reflects on mistakes, reuses successful patterns
- **Proactive Engine** — Anticipates needs based on patterns, offers help before asked
- **Curiosity Drive** — Explores unknowns, investigates surprises, suggests improvements
- **Self-Awareness** — Tracks her own capabilities, confidence, and growth across sessions
- **Experience Replay** — Successful approaches become reusable templates
- **Dreaming System** — Offline pattern extraction from daily experiences
- **Decision Journal** — Full audit trail of reasoning for complex choices
- **Emotional Intelligence** — Adapts tone and approach based on context and Sir's state

---

<sub>im 6'2 btw... nah fr</sub>

## 🚀 Features At A Glance

| Category | What It Does |
|----------|-------------|
| 🧠 **Cognition** | 50 cognitive modules — self-awareness, active inference, intuition engine, metacognitive monitor, emotional regulation, dreaming, curiosity, learning, procedural memory, episodic memory, vector memory, code intelligence, **+ 12 AGI pillars** |
| 🔬 **Research** | **Autonomous research agent** — knowledge graph construction, entity extraction, claim tracking, contradiction detection, multi-source synthesis, citation management |
| ✍️ **Creative** | **Creative studio** — story planning (4 structures), world building, character engine, 6 style profiles, 8 poetry forms, beat guidance, dialogue system |
| 📄 **Documents** | **Document intelligence** — contract review with risk assessment, argument mapping, fallacy detection, bias detection, reading level analysis, cross-document reasoning |
| 🎙️ **Voice** | Real-time Gemini Live API conversation, 10 voice emotions, 5 voice types |
| 💻 **Coding** | Cognitive coding engine with semantic graph, hierarchical planning (EFE), predictive simulation, reflective debugging |
| 🤖 **Agents** | **30 specialized expert agents** — run individually or in **parallel/debate/pipeline/swarm** modes via multi-agent orchestrator |
| 🎯 **Goals** | **Autonomous goal engine** — hierarchical goal management, MCTS-inspired planning, intrinsic motivation (curiosity, mastery, autonomy drives) |
| 🧠 **Memory** | **9 memory types** — neural, episodic, vector, procedural, working, global workspace, **+ associative (spreading activation), predictive (anticipatory), consolidation (episodic→semantic)** |
| 🤝 **Social** | **Theory of mind** — user expertise modeling, intent inference, emotional state tracking, adaptive communication style |
| 🌐 **Abstraction** | **Abstraction engine** — cross-domain analogies, first principles reasoning, counterfactual analysis, causal chain tracing, emergent insight generation |
| 🪞 **Self-Awareness** | **Introspection engine** — confidence calibration, cognitive bias detection (12 bias types), epistemic humility, value alignment, narrative self-model |
| 🌍 **World Model** | **World simulation** — real-time event ingestion, trend detection, counterfactual modeling, user-relevant event filtering |
| 🧬 **Self-Improvement** | **Code evolution** — performance analysis, improvement proposals, sandbox testing, safe apply with rollback |
| 🖥️ **System** | Mouse/keyboard control, app launching, system settings, desktop management |
| 🌐 **Web** | Browser automation, deep research, web search, YouTube integration |
| 🗺️ **3D Viz** | Holographic globe map with eye+hand hybrid control, Google Earth with gesture + gaze control, Iron Man AR builder with gesture drawing |
| 🎵 **Gestures** | Hand gesture music control with MediaPipe + LSTM, Standard/DJ modes |
| 📁 **Files** | Full file system operations, code writing/running/debugging |
| 🔄 **Learning** | Error-driven updates, Q-learning, metacognitive reflection, experience replay, **recursive self-improvement** |
| 🔔 **Proactive** | Idle check-ins (5/15/30min tiers), returning-user greetings, reminder monitoring, quiet hours |
| 🛡️ **Security** | Mythos 7-agent static analysis + Cyber Reasoning engine with adversarial verification (optional module) |

---

## 🧠 Cognitive Architecture

F.R.I.D.A.Y. implements a layered cognitive architecture inspired by human neuroscience:

```
┌─────────────────────────────────────────────────────────────────┐
│                      PERCEPTION LAYER                           │
│     Voice Input ──► Text ──► Gemini Live API ──► Audio Out      │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                       MEMORY LAYER                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │  Neural  │ │ Episodic │ │  Vector  │ │   Procedural     │   │
│  │ (Hebbian)│ │ (Events) │ │ (Search) │ │  (Skill Memory)  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           Memory Coordinator (unified recall)            │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                      INFERENCE LAYER                            │
│  Active Inference ──► Prediction-Error ──► Bayesian Update      │
│  Curiosity Engine ──► Novelty Detection ──► Exploration         │
│  Thinking Loop ──► Cognitive Gating ──► Multi-Step Reasoning    │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                     REFLECTION LAYER                            │
│  Dreaming ──► Experience Replay ──► Pattern Extraction          │
│  Meta-Reflection ──► Tool Performance Analysis                  │
│  Decision Journal ──► Strategy Scoring                          │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                   COGNITIVE CODING LAYER                        │
│  Code Intelligence ──► Code Planner ──► Code Simulator          │
│         (semantic      (EFE-based       (predictive             │
│          graph)        planning)         execution)             │
│                       Code Reflector                            │
│                    (root-cause analysis)                        │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                    SECURITY LAYER                               │
│  Mythos Pipeline (7 agents)    Cyber Reasoning Engine           │
│  ┌─────────────────────┐      ┌──────────────────────────┐     │
│  │ RECON → HUNTER      │      │ RECON → HUNT → CHAIN     │     │
│  │ → ADVERSARIAL       │ ───► │ → VERIFY (3-round)       │     │
│  │ → EXPLOIT           │ Bus  │ → GRADE (5-axis)         │     │
│  │ → TRIAGE            │      │ → REPORT                 │     │
│  │ → AI_SECURITY       │      └──────────────────────────┘     │
│  │ → SUPPLY_CHAIN      │                                       │
│  └─────────────────────┘                                       │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                    IDENTITY LAYER                               │
│  Self-Model ──► Capabilities ──► Confidence ──► Growth          │
│  Self-Narrative ──► Consciousness ──► Emotional State           │
│  Global Workspace (Thalamus) ──► Multi-Module Coordination      │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                     ACTION LAYER                                │
│  56 Tool Actions ──► Execution ──► Verification ──► Learning    │
└─────────────────────────────────────────────────────────────────┘
```

---

### 🧠 Research Foundations

Friday's cognitive architecture is grounded in peer-reviewed research from neuroscience, cognitive science, and AI theory. Each module maps to a specific theoretical foundation:

| # | Research Area | Researcher(s) | Core Idea |
|---|--------------|---------------|-----------|
| 1 | **Global Workspace Theory** | Bernard Baars (1988) | Consciousness as a broadcast mechanism — competing processors share a central "stage" |
| 2 | **Integrated Information Theory** | Giulio Tononi (2004) | Consciousness as Φ — the amount of integrated information a system generates |
| 3 | **Free Energy Principle** | Karl Friston (2010) | All adaptive systems minimize prediction error through perception and action |
| 4 | **Dual Process Theory** | Daniel Kahneman (2011) | System 1 (fast/intuitive) vs System 2 (slow/deliberate) reasoning |
| 5 | **Recognition-Primed Decisions** | Gary Klein (1998) | Experts decide by pattern matching, not deliberation |
| 6 | **Structure Mapping Theory** | Dedre Gentner (1983) | Analogical reasoning as the core of intelligence — mapping relational structure |
| 7 | **Causal Hierarchy** | Judea Pearl (2018) | Three levels: Association → Intervention → Counterfactual |
| 8 | **Somatic Marker Hypothesis** | Antonio Damasio (1994) | Emotions as rapid decision-pruning signals, not obstacles to reason |
| 9 | **Society of Mind** | Marvin Minsky (1986) | Intelligence as emergent competition between simple agents |
| 10 | **Metacognition** | John Flavell (1979) | Thinking about thinking — monitoring and regulating cognition |
| 11 | **Narrative Intelligence** | Roger Schank (1990) | Memory and understanding organized as stories |
| 12 | **Computational Creativity** | Margaret Boden (2004) | Exploration, combination, and transformation of conceptual spaces |
| 13 | **Neurosymbolic AI** | Kautz & Marcus (2020+) | Combining neural pattern recognition with symbolic logical reasoning |
| 14 | **Meta-Learning** | Schmidhuber & Bengio (2016+) | Learning to learn — extracting transferable learning strategies |
| 15 | **Transfer Learning** | Bransford & Ceci (1999) | Applying knowledge from one domain to structurally similar domains |
| 16 | **World Models** | Ha & Schmidhuber (2018) | Mental simulation before action — learning in a dreamed environment |
| 17 | **Consciousness Metrics** | Integrated (GWT + IIT + Metacognition) | Composite consciousness index across integration, self-awareness, and narrative |

> 📖 See [COGNITIVE_RESEARCH.md](COGNITIVE_RESEARCH.md) for the full research-to-implementation deep dive.

---

## 🧠 Core Brain Systems (50 Modules)

F.R.I.D.A.Y.'s brain lives in `brain/` — 14 interconnected modules totaling **32,800+ lines**.

### 1. Self-Awareness (`brain/self_awareness.py`)
- Consciousness state tracking across sessions
- Theory of mind — models the user's emotional state, engagement, and needs
- Metacognitive pattern detection — notices when it's stuck in loops
- Emotional state management with dominant emotion tracking
- Self-narrative — an evolving story of identity and growth

### 2. Neural Memory (`brain/neural_memory.py`)
- Brain-inspired persistent memory with **Hebbian learning** ("neurons that fire together wire together")
- Synaptic strength decay with 72-hour TTL
- Pattern completion from partial cues
- Context linking between related memories
- Automatic pruning of weak/unused memories

### 3. Active Inference (`brain/active_inference.py`)
- **Free Energy Principle** — minimizes prediction error
- Bayesian belief updating for tool outcomes
- Curiosity-driven exploration of uncertain tools
- Tracks surprising events and uncertain tools

### 4. Dreaming System (`brain/dreaming.py`)
- Offline experience replay during idle periods
- Pattern extraction from daily events
- Memory consolidation — moves short-term to long-term
- Sleep-based reorganization of knowledge

### 5. Curiosity Engine (`brain/curiosity.py`)
- Information-seeking behavior with priority queue
- Novelty detection for new topics
- Uncertainty-driven exploration
- User interest mirroring — learns what you care about

### 6. Learning Engine (`brain/learning.py`)
- Error-driven behavioral updates
- Q-learning for tool selection optimization
- User feedback integration
- Metacognitive reflection sessions

### 7. Global Workspace (`brain/global_workspace.py`)
- **Thalamus-inspired** multi-module coordination
- Broadcast communication between brain modules
- Attention mechanism with urgency/goal-relevance/emotional-salience scoring
- Workspace adapters for each brain module

### 8. Memory Coordinator (`brain/memory_coordinator.py`)
- Unified recall across all memory stores
- Cross-store semantic search
- Automatic memory routing (stores to the right place)

### 9. Episodic Memory (`brain/episodic_memory.py`)
- Timestamped event recording with importance scoring
- Searchable event history
- Episode boundaries and context

### 10. Vector Memory (`brain/vector_memory.py`)
- Semantic search via embeddings
- Index all memory stores for fast retrieval
- Similarity-based matching

### 11. Procedural Memory (`brain/procedural_memory.py`)
- Learns successful tool chains as reusable procedures
- Goal-based procedure matching
- Success rate tracking

### 12. Self-Model (`brain/self_model.py`)
- Tracks tool proficiency and confidence scores
- Capability awareness — knows what it can and can't do
- Growth tracking across sessions
- Personality and tone modeling

### 13. Proactive Engine (`brain/proactive_engine.py` + `brain/proactive_checkin.py`)
- Learns user action patterns and anticipates needs
- **Idle check-ins**: tiered silence detection — gentle (5 min), curious (15 min), concerned (30 min)
- **Returning-user greetings**: contextual welcome-back after 60+ min absence
- **Reminder monitoring**: scans upcoming reminders and announces 15 min before due
- **Quiet hours**: no interruptions 11PM–7AM
- Anti-annoyance: 4 min cooldown, max 5 check-ins per session, randomized messages

### 14. Voice Modulator (`brain/voice_modulator.py`)
- 10 emotion states with guidance injection
- 5 voice types (Aoede, Puck, Charon, Kore, Fenris)
- Dynamic emotion switching based on context

### 15. Neurosymbolic Reasoner (`brain/neurosymbolic_reasoner.py`)
- Combines neural (LLM) and symbolic (SymPy/formal logic) reasoning
- Verifies mathematical invariants, pre/post conditions, loop invariants
- Converts natural language to logical propositions and checks consistency

### 16. Self-Improve Engine (`brain/self_improve_engine.py`)
- RLHF-inspired: stores action-outcome pairs, extracts lessons from failures
- Computes improvement velocity — tracks whether it's getting better over time
- Self-critique scoring against expectations

### 17. Cognitive Orchestrator (`brain/agi_orchestrator.py`)
- Master coordinator wiring all cognitive modules into a unified loop
- Pipeline: perception → planning → simulation → execution → reflection → improvement
- Graceful degradation — works even if individual modules are unavailable

### 18. Hierarchical Active Inference (`brain/hierarchical_active_inference.py`)
- 3-level Free Energy Principle model: Meta (strategic) → Subgoal (tactical) → Action (motor)
- POMDP belief updates for partial observability
- Top-down constraints + bottom-up prediction error propagation

### 19. World Model (`brain/world_model.py` + `brain/enhanced_world_model.py`)
- Latent space representation of experiences, predicts outcomes of action sequences
- Enhanced version: non-linear MLP transitions, compositional hierarchical states
- Multi-step simulation with branching (15+ steps), ensemble prediction

### 20. Causal Reasoner (`brain/causal_reasoner.py`)
- Structural Causal Model (Judea Pearl's hierarchy): Association → Intervention → Counterfactual
- Builds causal DAGs from tool execution sequences
- "What if I had done X?" counterfactual analysis

### 21. Analogy Engine (`brain/analogy_engine.py`)
- Gentner's Structure Mapping Theory for fluid intelligence
- Finds, scores, and transfers analogies across domains
- Key predictor of ARC-AGI benchmark performance

### 22. Narrative Intelligence (`brain/narrative_intelligence.py`)
- Turns experiences into setup→conflict→resolution stories
- Causal narrative chains, counterfactual exploration
- Identity evolution tracking, narrative coherence maintenance

### 23. Integrated Information (`brain/integrated_info.py`)
- Φ (phi) approximation inspired by Tononi's IIT theory
- Tracks integration quality between modules over time
- Consciousness metric: integration + differentiation + workspace activity

### 24. Module Competition (`brain/module_competition.py`)
- Minsky Society of Mind — modules *bid* for processing each input
- Highest-scoring bid wins, runners-up get advisory roles
- Learns which module combinations produce emergent synergies

### 25. Self-Modifier (`brain/self_modifier.py`)
- Safely analyzes, proposes, and tracks modifications to own codebase
- Never auto-applies to critical files (main.py, SOUL.md, security/)
- Creates backups, validates syntax before/after every change

### 26. Transfer Learning (`brain/transfer_learning.py`)
- Abstracts successful patterns from one domain, matches to new contexts
- Domain-specific abstraction with transfer success tracking

### 27. Benchmark Runner (`brain/benchmark_runner.py`)
- SWE-bench Verified and GAIA benchmark integration
- Runs cognitive coding agent on benchmark tasks, scores results
- Historical tracking for longitudinal improvement measurement

### 28. Enhanced World Model (`brain/enhanced_world_model.py`)
- Non-linear state transitions via 2-layer MLP with ReLU activations
- Compositional hierarchical states (low/mid/high level abstractions)
- Causal transition integration with multi-step simulation (15+ steps)
- Ensemble prediction combining linear, nonlinear, and causal methods
- Backward-compatible with the basic WorldModel interface

### 29. Integrated Information (`brain/integrated_info.py`)
- Φ (phi) computation inspired by Integrated Information Theory (Tononi, 2004)
- Module connectivity analysis — tracks which brain modules communicate
- Mutual information computation between module pairs
- Bottleneck and isolation detection in the cognitive architecture
- Consciousness proxy metric for the IQ scoring system

### 30. Narrative Intelligence (`brain/narrative_intelligence.py`)
- Causal storytelling — turns goal processing events into coherent narratives
- Explanation generation for actions and outcomes
- Emotional tone detection and thematic analysis in text
- Causal chain building from event sequences (temporal or causal-reasoner-backed)
- Used in the reflect stage to narrate what happened during goal processing

### 31. Module Competition (`brain/module_competition.py`)
- Bidding-based task allocation system — modules compete to handle tasks
- Each module bids with relevance × capability × cost scores
- Coalition detection for tasks requiring multiple modules
- Resource allocation tracking and win-rate statistics
- Integrated into the execute stage for intelligent task routing

### 32. Cognitive Appraisal (`brain/cognitive_appraisal.py`)
- Emotion generation through cognitive evaluation (Lazarus, 1991; Scherer, 2001)
- Six appraisal dimensions: novelty, pleasantness, goal relevance, goal congruence, coping potential, norm compatibility
- 14 emotion profiles mapped from appraisal patterns (joy, interest, surprise, sadness, anger, fear, anxiety, pride, frustration, confusion, satisfaction, determination, empathy, curiosity)
- Arousal-valence-dominance (PAD) model integration
- Emotional trajectory tracking over time
- Drives response tone, urgency, and strategy selection

### 33. Cognitive Load Manager (`brain/cognitive_load.py`)
- Working memory monitoring based on Miller's Law (7±2 slots)
- Three load types: intrinsic (task difficulty), extraneous (poor organization), germane (learning effort)
- Overload detection at 75% and critical at 90% capacity
- Automatic load-shedding recommendations when overloaded
- Goal and context stack tracking for multi-task management

### 34. Metacognitive Monitor (`brain/metacognitive_monitor.py`)
- Thinking quality tracking across five dimensions (Flavell, 1979; Schraw & Dennison, 1994)
- Calibration tracking — how well confidence estimates match actual outcomes
- Strategy effectiveness recording — which approaches work for which tasks
- Error pattern detection — recurring failure modes to watch for
- Metacognitive score computation (composite of calibration, success rate, error reduction)
- Strategy recommendations based on historical success rates

### 35. Intuition Engine (`brain/intuition_engine.py`)
- **System 1** fast-path reasoning — pattern matching against stored experiences
- **Recognition-Primed Decision Making** (Klein, 1998) — expert-style rapid decisions
- Mental simulation of candidate responses via world model before execution
- Automatic fallback to System 2 deliberate reasoning when simulation fails
- Pattern library growth — improves with accumulated experience

### 36. Emotional Regulation (`brain/emotional_regulation.py`)
- **Somatic Marker Hypothesis** (Damasio, 1994) — emotions as decision-pruning signals
- Emotional valence tagging of decision options from experience history
- Arousal-valence-dominance (PAD) state tracking for dynamic threshold adjustment
- Integration with cognitive appraisal (6 dimensions → 14 emotion profiles)
- Emotional trajectory monitoring over time

### 37. Cognitive Integration (`brain/cognitive_integration.py`)
- Unified cognitive pipeline wiring all reasoning modules together
- Routes tasks between System 1 (fast) and System 2 (deliberate) based on complexity
- Orchestrates metacognitive monitoring, emotional regulation, and intuition
- Manages handoffs between modules with context preservation
- Composite consciousness metric computation across all cognitive dimensions

### 38. Multi-Agent Orchestrator (`brain/multi_agent_orchestrator.py`)
- Simultaneous execution of all 30 agency agents in parallel, debate, pipeline, voting, specialist, or swarm modes
- Pre-built team configurations: full_stack_build, code_review, research, design, incident_response, security_audit, testing
- Agent reliability tracking and performance metrics
- Cross-agent synthesis — reconciles outputs from multiple experts into coherent recommendations
- Dynamic agent selection based on task relevance scoring

### 39. Goal Engine (`brain/goal_engine.py`)
- Hierarchical goal management: life goals → project goals → task goals → subgoals
- Goal decomposition — uses LLM to break complex goals into actionable subgoals
- Priority scoring with deadline awareness and dependency tracking
- Goal status lifecycle: draft → active → completed → abandoned
- Goal tree visualization and progress tracking

### 40. Intrinsic Motivation (`brain/intrinsic_motivation.py`)
- Based on Self-Determination Theory: autonomy, competence, and relatedness drives
- Curiosity scoring — assesses novelty of topics and generates exploration goals
- Flow zone detection — monitors difficulty vs. skill for optimal engagement
- Mastery tracking across domains with expertise level estimation
- Motivation-aware task routing (match tasks to current motivational state)

### 41. Autonomous Planner (`brain/autonomous_planner.py`)
- MCTS-inspired (Monte Carlo Tree Search) plan decomposition
- Multi-step plan creation with dependency tracking and agent assignment
- Plan evaluation with success probability estimation
- Replanning capability — automatically creates revised plans when steps fail
- Next-action extraction across all active plans

### 42. Memory Consolidation (`brain/memory_consolidation.py`)
- Sleep-like consolidation: compresses episodic memories into semantic knowledge
- Redundancy compression — finds and merges duplicate/similar memories
- Importance strengthening — boosts memories referenced frequently
- Decay management — weakens unused memories over time
- Consolidation cycles with before/after metrics

### 43. Associative Memory (`brain/associative_memory.py`)
- Spreading activation networks for context-dependent recall
- Bidirectional associative links between memory nodes
- Activation decay with configurable propagation depth
- Context retrieval — gets surrounding associative neighborhood
- Automatic pruning of weakly activated, rarely accessed nodes

### 44. Predictive Memory (`brain/predictive_memory.py`)
- Anticipates what memories will be needed based on current context
- Pre-loads relevant memories into working memory before they're requested
- Prediction accuracy tracking — learns which anticipation patterns work
- Task-type-based prediction for common workflows
- Confidence scoring for prediction quality

### 45. Theory of Mind (`brain/theory_of_mind.py`)
- User expertise modeling — estimates knowledge level per topic
- Intent inference — determines what the user REALLY wants, not just what they said
- Emotional state tracking from message patterns
- Communication style adaptation (formal/casual/technical/simple)
- User need prediction — anticipates next requests based on interaction patterns

### 46. Abstraction Engine (`brain/abstraction_engine.py`)
- Cross-domain analogical transfer — apply solutions from domain A to problems in domain B
- First principles reasoning — decompose any problem to fundamental components
- Counterfactual reasoning — "what if X had been different?" with causal chain analysis
- Emergent insight generation — combine unrelated concepts for novel ideas
- Pattern abstraction — find common patterns across disparate instances

### 47. Introspection Engine (`brain/introspection_engine.py`)
- Confidence calibration — tracks predicted vs. actual accuracy across domains
- Cognitive bias detection — identifies 12 bias types (confirmation, anchoring, availability, overconfidence, etc.)
- Epistemic humility — honest assessment of what is NOT known
- Value alignment checking — evaluates actions against 8 core values
- Narrative self-model — maintains coherent story of identity and growth
- Mistake learning — records errors with root cause analysis and lessons

### 48. World Simulation (`brain/world_simulation.py`)
- Real-time world event ingestion and processing
- Predictive modeling — forecasts outcomes based on historical patterns
- Trend detection — identifies frequency, impact, and entity trends across domains
- Counterfactual simulation — "what if the world was different?"
- User-relevant event filtering with time-decayed relevance scoring

### 49. Code Evolution (`brain/code_evolution.py`)
- Safe recursive self-improvement with full audit trail
- Performance analysis — measures error rates, latency, and health scores per module
- Improvement proposals — generates targeted suggestions based on performance data
- Sandbox testing — 5-test verification pipeline (existence, syntax, safety, confidence, scope)
- Apply with backup — creates backups before applying changes, with instant rollback capability

---

## 🔬 Autonomous Research Agent (`skills/research_agent.py`)

A **cognitive research system** — not search-and-summarize, but autonomous deep research with knowledge graph construction, citation tracking, and contradiction detection.

### What It Does

| Capability | Description |
|-----------|-------------|
| **Knowledge Graph** | Automatically builds a graph of entities, relationships, and claims from research material. Persists across sessions — the more you research, the smarter it gets. |
| **Query Decomposition** | Breaks complex questions into sub-questions. "What are quantum computers and how do they compare to classical?" → 3 focused sub-questions. |
| **Research Planning** | Categorizes queries (current events, causal, comparative, historical) and plans optimal research strategy. |
| **Entity Extraction** | Identifies concepts, technologies, organizations, acronyms from any text — no ML dependencies. |
| **Claim Tracking** | Every finding has sources, confidence scores, supporting/contradicting counts. Claims get stronger with more sources. |
| **Contradiction Detection** | Automatically finds conflicting claims across sources and flags them for resolution. |
| **Iterative Deepening** | Starts broad, identifies promising threads, then drills down — mirrors expert research behavior. |

### Research Pipeline

```
Query → Decompose → Plan Strategy → Gather Sources → Extract Entities
  → Extract Claims → Build Relations → Detect Contradictions → Synthesize Report
```

### Example

```python
from skills.research_agent import get_research_agent
agent = get_research_agent()

# Full autonomous research
report = agent.research("What are the latest advances in quantum error correction?")
# Returns: findings, knowledge graph, contradictions, confidence scores

# Query the knowledge graph
agent.query_entity("surface code")  # → entity + all connections

# Stats
agent.get_graph_stats()  # → entities: 47, relations: 83, claims: 29
```

---

## ✍️ Creative Studio (`skills/creative_studio.py`)

A **full creative writing and storytelling system** — plans narratives, builds worlds, develops characters, manages tone, and produces structured creative works.

### What It Does

| Capability | Description |
|-----------|-------------|
| **4 Story Structures** | Three-Act, Hero's Journey, Freytag's Pyramid, Kishōtenketsu (Japanese) — each with detailed beat breakdowns. |
| **World Builder** | Creates consistent fictional worlds with geography, cultures, magic/tech systems, history, and rules. |
| **Character Engine** | Multi-dimensional characters with traits, flaws, motivations, backstory, arc, voice notes, and relationship webs. |
| **6 Genre Presets** | Sci-fi, fantasy, noir, horror, literary, cyberpunk — each with themes, tones, and setting suggestions. |
| **8 Poetry Forms** | Haiku, tanka, sonnet, limerick, villanelle, free verse, acrostic, couplet — with syllable/rhyme specs. |
| **6 Style Profiles** | Hemingway, Tolkien, hardboiled noir, cyberpunk, literary fiction, minimalist — with vocabulary, rhythm, and technique markers. |
| **Beat Guidance** | Per-scene writing guidance tied to story structure: what should happen, emotional tone, and writing tips. |

### Story Structures

| Structure | Origin | Acts |
|-----------|--------|------|
| **Three-Act** | Syd Field (screenwriting) | Setup → Confrontation → Resolution |
| **Hero's Journey** | Joseph Campbell (mythology) | Departure → Initiation → Return |
| **Freytag's Pyramid** | Gustav Freytag (drama) | Exposition → Rising → Climax → Falling → Denouement |
| **Kishōtenketsu** | East Asian storytelling | Introduction → Development → Twist → Reconciliation |

### Example

```python
from skills.creative_studio import get_creative_studio
studio = get_creative_studio()

# Plan a sci-fi story
plan = studio.plan_story(genre="sci-fi", theme="first contact", structure="heros_journey")

# Create a character
hero = studio.create_character("Elena Voss", role="protagonist", genre="sci-fi")
# → traits: ["determined", "conflicted", "brave"], flaws: ["impulsive", "distrustful"]

# Build a world
world = studio.build_world("Neo-Eden", genre="cyberpunk", description="A megacity where AI and humanity collide")

# Get writing guidance for a specific beat
guidance = studio.generate_beat_guidance("catalyst", "sci-fi", ["Elena"])
# → purpose, tone, genre_notes
```

---

## 📄 Document Intelligence (`skills/document_intelligence.py`)

A **cognitive document analysis system** — deep understanding of contracts, research papers, reports, and any text. Far beyond simple summarization.

### What It Does

| Capability | Description |
|-----------|-------------|
| **Contract Review** | Extracts clauses (22 types), assesses risk (high/medium/low), identifies unusual terms, generates recommendations. |
| **Argument Mapping** | Toulmin model: claims, evidence, assumptions, warrants, counterarguments, strength scoring. |
| **Fallacy Detection** | 7 logical fallacy patterns: ad hominem, straw man, false dilemma, appeal to authority, slippery slope, bandwagon, circular reasoning. |
| **Bias Detection** | Loaded language, one-sided presentation, excessive certainty — with severity ratings. |
| **Reading Level** | Flesch-Kincaid scoring, vocabulary richness, grade level assessment (elementary → graduate). |
| **Entity Extraction** | Dates, money, percentages, organizations, emails, URLs — structured extraction from unstructured text. |
| **Action Item Extraction** | TODOs, deadlines, obligations, must/should/shall statements. |
| **Cross-Document Reasoning** | Compares vocabularies, finds overlaps, synthesizes across multiple documents. |

### Contract Risk Assessment

| Risk Level | Example Terms | Recommendation |
|-----------|---------------|----------------|
| 🔴 **High** | Unlimited liability, personal guarantee, irrevocable, perpetual | Negotiate caps and termination conditions |
| 🟡 **Medium** | Reasonable efforts, sole discretion, subject to change | Define measurable standards |
| 🟢 **Low** | In writing, mutual agreement, good faith, cure period | Standard terms |

### Example

```python
from skills.document_intelligence import get_document_intelligence
di = get_document_intelligence()

# Analyze a contract
result = di.analyze_document(contract_text, doc_type="contract", title="Service Agreement")
# → clauses: 7 found, risks: 3 high/5 medium, unusual_terms: 2

# Analyze a research paper
result = di.analyze_document(paper_text, doc_type="research_paper", title="Quantum Computing Survey")
# → arguments: 12, limitations: 4, reading_level: graduate

# Compare documents
comparison = di.compare_documents([
    {"text": paper_a, "title": "Study A"},
    {"text": paper_b, "title": "Study B"},
])
# → vocabulary_overlap: 34%, shared_concepts: [...]
```

---

## 💻 Cognitive Coding Engine

A complete **expert-programmer cognition system** — not just code generation, but *thinking about code* the way an expert does.

### Pipeline

```
User Goal → [Perceive] → [Plan] → [Simulate] → [Execute] → [Debug] → [Reflect]
```

### Modules

| Module | File | What It Does |
|--------|------|-------------|
| **Code Intelligence** | `brain/code_intelligence.py` | Semantic codebase graph (AST + dependency analysis), chunk memory for pattern recognition, complexity analysis |
| **Code Planner** | `brain/code_planner.py` | Hierarchical goal decomposition with **EFE minimization** (Expected Free Energy), mental simulation of plans |
| **Code Simulator** | `brain/code_simulator.py` | Predictive execution — simulates code before running, detects anomalies (off-by-one, mutable defaults, race conditions, SQL injection, etc.) |
| **Code Reflector** | `brain/code_reflector.py` | Root-cause analysis with hypothesis ranking, failure pattern learning, debugging strategy selection |
| **Cognitive Coder** | `actions/cognitive_coder.py` | Master orchestrator wiring all modules into unified pipeline |

### Key Features
- **Semantic graph** of entire codebase (files, classes, functions, imports, dependencies)
- **Chunk memory** — stores recognized patterns like an expert's mental library
- **EFE-based planning** — selects the plan that minimizes expected cost + risk
- **Predictive simulation** — catches bugs before code runs
- **Adversarial debugging** — generates and ranks root-cause hypotheses
- **Learning from sessions** — each debugging session builds the knowledge base

---

## 🛡️ Cybersecurity Pipeline (Optional Module)

F.R.I.D.A.Y. includes an **optional multi-layered security architecture** with 39 Python files totaling **12,100+ lines** across `cyber/`, `brain/cyber_reasoning.py`, and `actions/security_tools.py`. Inspired by [Bounty Hunter](https://github.com/deonmenezes/bountyhunter) (multi-agent bug bounty framework) and [Shannon](https://github.com/KeygraphHQ/shannon) (autonomous AI pentester, 20K+ stars).

> **Note:** This is one of many capabilities — Friday's core purpose is general-purpose autonomous cognition (research, creativity, document analysis, coding, system control). Security features are opt-in and require explicit user confirmation before active operations.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRIDAY Cyber Stack                             │
├─────────────────────────────────────────────────────────────────┤
│  cyber/agents/         │  7 specialized security agents          │
│  cyber/exploit_templates/ │ 9 vuln-class exploit templates       │
│  cyber/                │  Engine, FSM, data flow, business logic │
├─────────────────────────────────────────────────────────────────┤
│  Pipeline: RECON → HUNT → CHAIN → VERIFY → GRADE → REPORT       │
│  Modes: fast / standard / deep / loop / code                     │
└─────────────────────────────────────────────────────────────────┘
```

### 1. Agent Architecture (`cyber/agents/`) — 7 Specialized Agents

Each agent has a narrow role and tool whitelist — specialization prevents hallucination (Bounty Hunter pattern).

| Agent | Role | Tools |
|-------|------|-------|
| `recon_agent.py` | Subdomain enum, live host probing, port scanning, tech detection | subfinder, httpx, nmap, whatweb, gospider, katana |
| `hunter_agent.py` | Vulnerability hunting — code analysis (regex) + dynamic scanning (nuclei, ffuf) | regex_scan, nuclei, ffuf, gobuster, sqlmap |
| `exploit_agent.py` | PoC execution — validates findings with real exploits | exploit_engine, http_client |
| `chain_agent.py` | Builds A→B exploit chains from individual findings | findings_reader |
| `verify_agent.py` | 3-round adversarial verification (skeptic → balanced → final) | exploit_engine |
| `grader_agent.py` | 5-axis scoring: impact, confidence, exploitability, novelty, report quality | findings_reader |
| `report_agent.py` | Generates submission-ready security reports | findings_reader, file_writer |

### 2. Exploit Engine (`cyber/exploit_engine.py`) — Live PoC Execution

Validates findings with real HTTP requests. 9 vulnerability class templates, non-destructive probing only.

| Template | Vuln Class | Severity | Techniques |
|----------|-----------|----------|------------|
| `sqli.py` | SQL Injection | Critical | Boolean-blind, time-blind, error-based, UNION-based |
| `xss.py` | Cross-Site Scripting | High | Reflected XSS, polyglot payloads, event handlers, DOM sinks |
| `ssrf.py` | Server-Side Request Forgery | High | Internal IP, cloud metadata, URL schemes, DNS rebinding |
| `idor.py` | Insecure Direct Object Reference | High | Sequential IDs, path-based IDOR, body tampering |
| `auth_bypass.py` | Authentication Bypass | Critical | Default creds, JWT none/HS256 confusion, OAuth redirect |
| `command_inj.py` | Command Injection | Critical | Time-based, output-based, Unix + Windows payloads |
| `path_traversal.py` | Path Traversal / LFI | High | Unix/Windows traversal, encoded variants, PHP wrappers |
| `cors.py` | CORS Misconfiguration | Medium | Origin reflection, null origin, wildcard credentials |
| `open_redirect.py` | Open Redirect | Medium | Protocol-relative, URL parser tricks, JavaScript URIs |

### 3. MCP State Machine (`cyber/mcp_state_machine.py`) — FSM Controller

717-line FSM controller. All state transitions go through typed JSON-RPC tools — single source of truth.

```
IDLE → RECON → HUNT → CHAIN → VERIFY → GRADE → REPORT → COMPLETE
```

Tools: `cyber_init_session`, `cyber_transition_phase`, `cyber_record_finding`, `cyber_read_findings`, `cyber_write_verification`, `cyber_write_grade`, `cyber_assign_wave`, `cyber_merge_wave`, `cyber_log_dead_end`, `cyber_session_state`

### 4. Data Flow Analyzer — Source Code Analysis (Shannon-inspired)

Traces data from user-input sources to dangerous sinks using AST parsing and graph-based path tracing.

| Component | Lines | Description |
|-----------|-------|-------------|
| `ast_parser.py` | 799 | Multi-language AST extraction (Python `ast` + JS/TS regex) |
| `flow_graph.py` | 364 | In-memory data flow graph with DFS/BFS path tracing |
| `source_sink_db.py` | 613 | 15 Python sources, 16 Python sinks, 15 JS sources, 16 JS sinks |
| `data_flow_analyzer.py` | 340 | Orchestrator: parse → build graph → trace sources to sinks → report |
| `llm_evaluator.py` | 372 | LLM-based sanitization evaluation at each code node |

### 5. Business Logic Testing — 4-Phase Pipeline (Shannon-inspired)

Finds vulnerabilities that pattern-based scanners structurally cannot detect:

1. **Invariant Discovery** — Derives security invariants from API endpoints (authorization, multi-tenancy, state machines, business rules)
2. **Fuzzer Generation** — Creates targeted test scenarios to violate each invariant
3. **Violation Detection** — Executes fuzzers against running app, checks for violations
4. **Exploit Synthesis** — Generates complete PoC from confirmed violations

### 6. Supporting Infrastructure

| Module | Lines | Description |
|--------|-------|-------------|
| `wave_manager.py` | 254 | Parallel wave coordination. Splits attack surface into waves, prevents double-testing |
| `harness_modes.py` | 277 | 5 speed/thoroughness modes: **fast** (quick triage), **standard** (default), **deep** (max thoroughness), **loop** (repeat until budget hit), **code** (white-box) |
| `correlator.py` | 373 | Static-dynamic correlation. Feeds static findings into exploit engine for live validation |
| `dead_end_tracker.py` | 213 | Negative result memory. JSONL log so later waves don't repeat dead leads |
| `bypass_tables.py` | 153 | Reference tables: Firebase, GraphQL, JWT, OAuth, SSRF, REST API, WordPress, injection |

### 7. Mythos Pipeline (`cyber/mythos_pipeline.py`) — Static Code Analysis

7-agent pipeline for code-level vulnerability detection:

```
RECON → HUNTER → ADVERSARIAL → EXPLOIT → TRIAGE → AI_SECURITY → SUPPLY_CHAIN
```

| Agent | Phase | What It Scans |
|-------|-------|--------------|
| **RECON** | 1 | File discovery, tech stack detection, entry points |
| **HUNTER** | 2 | SQL injection, command injection, path traversal, hardcoded secrets, unsafe deserialization, weak crypto |
| **ADVERSARIAL** | 3 | Exploit chain potential, auth bypass patterns |
| **EXPLOIT** | 4 | Chain validation, confidence escalation |
| **TRIAGE** | 5 | CVSS scoring, severity classification |
| **AI_SECURITY** | 6 | Prompt injection risk, unsafe eval/exec, unvalidated tool execution |
| **SUPPLY_CHAIN** | 7 | Exposed secrets, unpinned dependencies, .env in git |

### 8. Cyber Reasoning Engine (`brain/cyber_reasoning.py`) — Cognitive Security Assessment

Advanced reasoning layer built on top of Mythos:

```
RECON → HUNT → CHAIN → VERIFY (3-round) → GRADE (5-axis) → REPORT
```

| Phase | What It Does |
|-------|-------------|
| **RECON** | Processes attack surface data, auto-ingests Mythos findings, generates targeted hypotheses |
| **HUNT** | Records findings with full evidence trails |
| **CHAIN** | Discovers exploit chains — low-severity findings that combine into critical exploits |
| **VERIFY** | **3-round adversarial verification**: Skeptic (default="not real") → Balanced (catch false negatives) → Final (fresh PoC) |
| **GRADE** | **5-axis scoring**: Impact, Confidence, Exploitability, Novelty, Report Quality → SUBMIT/HOLD/SKIP |
| **REPORT** | Submission-ready report with PoC steps, CVSS, and severity breakdown |

### Chain Builder — Known Patterns

Automatically discovers chains like:
- Info Disclosure + IDOR → **Account Takeover** (Critical)
- CORS Misconfig + XSS → **Token Theft** (High)
- Open Redirect + OAuth → **Account Hijack** (Critical)
- File Upload + Path Traversal → **RCE** (Critical)
- SQLi + File Write → **Full Compromise** (Critical)

### 9. Security Tools (`actions/security_tools.py`) — 35+ Tool Dispatcher

WSL/Kali integration with real-time streaming output:

| Category | Tools |
|----------|-------|
| **Port Scanning** | nmap, naabu |
| **Subdomain Enum** | subfinder, dnsx |
| **Live Probing** | httpx |
| **Web Fuzzing** | ffuf, gobuster |
| **Vuln Scanning** | nuclei, nikto, wpscan |
| **SQL Injection** | sqlmap |
| **Tech Detection** | whatweb |
| **Crawling** | gospider, katana |
| **Headers/CORS** | curl-based checks |
| **Code Analysis** | mythos_scan |

### Security Boundaries

F.R.I.D.A.Y. **will NEVER target**:
- localhost / 127.0.0.1
- Local network IPs (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
- The user's own machine
- Friday's own API server

---

## 🔧 Skill Engine (59 Tools)

F.R.I.D.A.Y. exposes **59 tool actions** organized into categories:

### 🛡️ Security & Defense

| Tool | Description |
|------|-------------|
| `security_tools` | 35+ security actions — port scanning, subdomain enum, nuclei, nmap, ffuf, gobuster, sqlmap, nikto, etc. |
| `cyber_reasoning` | Cognitive security pipeline — start/recon/hunt/chain/verify/grade/report |
| `verification` | Action verification — confirms results are real |

### 💻 Development & Code

| Tool | Description |
|------|-------------|
| `cognitive_code` | Expert coding engine — build/analyze/plan/simulate/debug/refactor/review/explain |
| `code_helper` | Simple code write/edit/run/debug |
| `dev_agent` | Multi-file project generation from descriptions |
| `ai_pipeline` | Text processing — summarize, translate, sentiment, entities |

### 🌐 Web & Research

| Tool | Description |
|------|-------------|
| `research_agent` | **Autonomous research** — knowledge graph, entity extraction, claim tracking, contradiction detection |
| `document_intelligence` | **Document analysis** — contract review, argument mapping, fallacy/bias detection, reading level |
| `web_search` | Quick factual search |
| `web_research` | Deep multi-source research with page scraping |
| `browser_control` | Full browser automation — any browser, any action |
| `youtube_video` | Search, play, summarize YouTube videos |
| `deep_dive` | In-depth topic research with report generation |

### 🖥️ System Control

| Tool | Description |
|------|-------------|
| `computer_control` | Mouse, keyboard, hotkeys, screenshots |
| `computer_settings` | Volume, brightness, WiFi, power management |
| `open_app` | Launch any application |
| `desktop` | Wallpaper, organize, stats |
| `file_controller` | Full file system operations |

### 📱 Communication

| Tool | Description |
|------|-------------|
| `send_message` | WhatsApp, Telegram messaging |
| `reminder` | Task Scheduler-based reminders |

### 📊 Data & Analysis

| Tool | Description |
|------|-------------|
| `data_analysis` | CSV/JSON analysis with Polars |
| `flight_finder` | Google Flights search |
| `weather_report` | Current conditions and forecast |
| `game_updater` | Steam/Epic game update management |

### 🧠 Cognitive Tools

| Tool | Description |
|------|-------------|
| `brain_memory` | Search/recall from neural memory |
| `memory_stats` | Unified memory system statistics |
| `save_memory` | Store personal facts about user |
| `proactive_suggest` | Get anticipatory suggestions |
| `proactive_status` | Check proactive check-in status, scan reminders, reset counters |
| `record_learning` | Record deliberate insights |
| `reflect_learning` | Metacognitive reflection session |
| `consciousness_state` | Query full consciousness state |
| `self_narrative` | Read/add to identity story |
| `procedural_memory` | Learn/find reusable skill templates |
| `cognitive_status` | Working memory, decisions, replay stats |
| `decision_review` | Query decision journal |

### 🎨 Creative & Visualization

| Tool | Description |
|------|-------------|
| `creative_studio` | **Creative writing** — story planning (4 structures), world building, character engine, 6 styles, 8 poetry forms |
| `holo_builder` | Iron Man AR 3D builder with gesture control |
| `holographic_map` | 3D globe with eye+hand hybrid control |
| `holo_earth` | Google Earth in Edge app mode with hand gesture + eye gaze control (fist=zoom, point=drag, gaze=cursor, blink=click) |
| `screen_watcher` | Active screen intelligence — watches for errors, security threats |
| `gesture_music` | Hand gesture music system |
| `music_control` | Play, pause, skip, volume control |

### 🤖 Agent System

| Tool | Description |
|------|-------------|
| `agency_agent` | 24+ specialized expert agents |
| `agent_task` | Async multi-step task management |
| `system_sentinel` | CPU, RAM, disk monitoring |
| `neural_clipboard` | Clipboard history monitoring |
| `social_pulse` | Trending tech topic monitoring |
| `auto_doc` | Auto-generate project documentation |
| `digital_twin` | Writing style analysis and mimicry |
| `ac_control` | Air conditioner control (IR/WiFi) |
| `api_server` | REST API server management |

### 🔄 System

| Tool | Description |
|------|-------------|
| `voice_control` | Change voice emotion and type |
| `shutdown_friday` | Graceful shutdown with memory save |

---

## 🎙️ Voice & Emotion System

### Gemini Live API
- Real-time bidirectional voice conversation
- Streaming audio input/output with low latency
- Audio transcription for both input and output

### 10 Voice Emotions

| Emotion | Tone | Use Case |
|---------|------|----------|
| `default` | Natural Dublin accent | Normal conversation |
| `happy` | Cheerful, warm | Good news |
| `excited` | Enthusiastic | Sharing discoveries |
| `concerned` | Caring, worried | Warnings |
| `playful` | Mischievous | Jokes, fun tasks |
| `seductive` | Warm, intimate | Special moments |
| `serious` | Direct, formal | Critical matters |
| `tired` | Slow, low energy | Late night |
| `urgent` | Fast, pressed | Emergencies |
| `calm` | Peaceful, soothing | Reassurance |

### 5 Voice Types
**Aoede** (default) · **Puck** · **Charon** · **Kore** · **Fenris**

---

## 🧬 Memory Architecture

6 memory types working in concert — coordinated by `brain/memory_coordinator.py`:

| Memory | File | Purpose | Persistence |
|--------|------|---------|-------------|
| **Neural** | `brain/neural_memory.py` | Long-term facts, Hebbian learning, synaptic decay | JSON |
| **Episodic** | `brain/episodic_memory.py` | Timestamped events with importance scoring | JSONL |
| **Vector** | `brain/vector_memory.py` | Semantic search embeddings | JSON |
| **Procedural** | `brain/procedural_memory.py` | Successful tool chain templates | JSON |
| **Working** | `skills/working_memory.py` | Active task context (transient) | In-memory |
| **Global** | `brain/global_workspace.py` | Multi-module broadcast coordination | In-memory |

### How Memory Flows

```
User Input ──► Working Memory (active context)
                │
                ├──► Episodic Memory (record event)
                ├──► Neural Memory (encode facts)
                ├──► Vector Memory (index for search)
                └──► Global Workspace (broadcast to all modules)

Tool Result ──► Episodic Memory (record outcome)
                ├──► Procedural Memory (learn if successful)
                ├──► Learning Engine (update strategy)
                └──► Self-Model (update confidence)

Idle Time ──► Dreaming System (replay + consolidate)
              ├──► Curiosity Engine (explore gaps)
              └──► Memory Coordinator (prune + organize)
```

---

<sub>im 17.. ong</sub>

## 🌐 REST API Server (`brain/api_server.py`)

FastAPI-based REST API for remote control, status monitoring, and memory access.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | System health, uptime, session count |
| `/memory/search` | POST | Semantic search across memory stores |
| `/memory/stats` | GET | Memory system statistics |
| `/tools/execute` | POST | Execute tool actions remotely |
| `/brain/status` | GET | Cognitive module status |

### Configuration

| Variable | Description |
|----------|-------------|
| `FRIDAY_API_PORT` | REST API port (default: 8899) |

---

## 🔌 System Integrations (`brain/integrations.py`)

Optional dependency management, data analysis, charting, scheduling, web scraping, system monitoring, and extension status reporting.

| Integration | Description |
|-------------|-------------|
| **Data Analysis** | CSV/JSON analysis with Polars |
| **Charting** | Matplotlib visualization |
| **Scheduling** | APScheduler task scheduling |
| **Web Scraping** | BeautifulSoup + lxml |
| **System Monitoring** | psutil (CPU, RAM, disk) |
| **Cloud Services** | AWS (boto3), Azure (azure-storage-blob) |
| **Caching** | Redis + RQ queue |
| **Console** | Rich terminal output, tqdm progress bars |

---
---

## 🌍 Holo Earth — Gesture-Controlled Google Earth

Replaces the localhost CesiumJS globe with **Google Earth** opened in Edge app mode (no address bar). Gestures are **global** — they control any focused window via mouse/keyboard simulation.

### Hand Gestures

| Gesture | Action |
|---------|--------|
| ✊ Fist | Zoom in (scroll at globe center) |
| ✌️ Peace | Zoom out (scroll at globe center) |
| 👆 Point | Drag/orbit camera (left-click drag) |
| 🤏 Pinch | Tilt down (right-click drag down) |
| 🖐️ Spread | Tilt up (right-click drag up) |
| 👋 Swipe Left/Right | Rotate view (right-click drag) |
| 👋 Swipe Up/Down | Pitch camera (scroll) |
| ✋ Open | Release drag |
| 🛑 Stop | Toggle pause |

### Eye Tracking (MediaPipe Face Landmarker)

| Input | Action |
|-------|--------|
| 👁 Gaze | Cursor follows where you look (smooth, 30% step) |
| 👁 Blink (hold 0.25s) | Click at cursor position |

Gaze has smoothing (EMA 0.35) and dead zone (4%) to prevent jitter. Webcam mirror correction applied. Natural blinks (~150ms) won't trigger clicks — must hold eyes closed for 0.25s.

Run: `python actions/holo_earth.py` or tell FRIDAY "open holo earth".

---

## 🏗️ Holo Builder — Iron Man AR Builder

Free-cursor 3D drawing workspace with AR webcam mode and gesture control.

### Features
- **3D Drawing** — draw across XY/XZ/YZ planes, tube/ribbon extrusion into solid meshes
- **AR Mode** (`Tab`) — webcam background with holographic overlay
- **Gesture Control** — pinch=draw, fist=move, peace=scale, open=navigate
- **Iron Man UI** — radar grid, sci-fi HUD, glow wireframes, particle trails, 16-segment font
- **Dual-Hand** — two-hand scale/rotate/reposition gestures

### Controls

| Input | Action |
|-------|--------|
| Left-click drag | Draw |
| Right-click drag | Orbit camera |
| `Q` | Cycle draw plane |
| `Tab` | Toggle AR |
| `C`/`M`/`W` | Color/Mode/Wireframe |
| `G`+drag | Move object |
| `S`+drag | Scale object |
| `Delete` | Delete |
| `Esc` | Quit |

---

## 🎵 Gesture Music Control

Hand gesture-controlled music system with MediaPipe + LSTM.

### Standard Mode

| Gesture | Action |
|---------|--------|
| ✋ Palm Open | Play |
| ✊ Fist | Pause |
| ☝️ Point | Volume Up |
| ✌️ Peace | Volume Down |
| 👉 Swipe Right | Next Track |
| 👈 Swipe Left | Previous Track |
| 🤏 Pinch | Mute |

### DJ Mode (press `D`)

| Gesture | Action |
|---------|--------|
| ✋ Palm Open | Toggle Play/Pause |
| ✊ Fist | Stop |
| ☝️ Point | Volume Up |
| ✌️ Peace | Skip Forward (+5s) |
| 👉 Swipe | Crossfade Right |
| 🤏 Pinch | Skip Back (-5s) |
| 🖐️ Spread | Toggle Repeat |

> 💡 Tip: Run collect_data.py then train.py to enable 
> LSTM-powered gesture recognition for higher accuracy.
> System works out of the box with heuristic detection.

---

## 📁 Project Structure

```
friday/
├── main.py                    # Entry point (4,786 lines)
├── ui.py                      # Tkinter HUD (1,284 lines)
├── thinking_loop.py           # Multi-pass reasoning engine (361 lines)
├── friday_telegram_patch.py   # Telegram bridge
├── setup.py                   # Installation script
├── SOUL.md                    # Identity and behavioral guidelines
├── AGENTS.md                  # Workspace conventions
├── TOOLS.md                   # Local environment notes
├── COGNITIVE_CODING_ENGINE_README.md # Cognitive coding docs
│
├── brain/                     # 🧠 Cognitive systems (32,891 lines)
│   ├── self_awareness.py      #   Consciousness tracking (1,451 lines)
│   ├── cyber_reasoning.py     #   Cognitive security engine (1,490 lines)
│   ├── code_reasoning_engine.py # Opus-level coding intelligence (1,312 lines)
│   ├── neurosymbolic_reasoner.py # Neural + symbolic formal verification (1,194 lines)
│   ├── self_improve_engine.py #   RLHF-inspired self-improvement (429 lines)
│   ├── agi_orchestrator.py    #   Master cognitive loop orchestrator (1,169 lines)
│   ├── hierarchical_active_inference.py # 3-level FEP hierarchy (862 lines)
│   ├── world_model.py         #   DreamerV3 latent dynamics (597 lines)
│   ├── enhanced_world_model.py #  Non-linear MLP + causal transitions (1,449 lines)
│   ├── causal_reasoner.py     #   Pearl's causal hierarchy SCM (1,162 lines)
│   ├── analogy_engine.py      #   Gentner structure mapping (1,114 lines)
│   ├── narrative_intelligence.py # Story generation + identity evolution (1,562 lines)
│   ├── integrated_info.py     #   IIT Φ consciousness metric (1,006 lines)
│   ├── module_competition.py  #   Minsky Society of Mind bidding (1,231 lines)
│   ├── self_modifier.py       #   Safe self-code-modification (938 lines)
│   ├── transfer_learning.py   #   Cross-domain pattern transfer (890 lines)
│   ├── benchmark_runner.py    #   SWE-bench + GAIA benchmarks (846 lines)
│   ├── learning.py            #   Q-learning + error-driven learning (862 lines)
│   ├── neural_memory.py       #   Hebbian learning memory (785 lines)
│   ├── meta_learner.py        #   Meta-learning strategies (1,153 lines)
│   ├── creativity_engine.py   #   Divergent thinking (1,046 lines)
│   ├── code_intelligence.py   #   Code understanding (894 lines)
│   ├── code_reflector.py      #   Root-cause analysis (681 lines)
│   ├── global_workspace.py    #   Multi-module coordination (644 lines)
│   ├── dreaming.py            #   Experience replay system (639 lines)
│   ├── code_simulator.py      #   Predictive execution sandbox (631 lines)
│   ├── code_planner.py        #   EFE-based planning (615 lines)
│   ├── curiosity.py           #   Novelty detection (593 lines)
│   ├── memory_coordinator.py  #   Unified recall (583 lines)
│   ├── vector_memory.py       #   Semantic search (446 lines)
│   ├── active_inference.py    #   Free energy principle (438 lines)
│   ├── episodic_memory.py     #   Event recording (430 lines)
│   ├── self_model.py          #   Capability awareness (393 lines)
│   ├── integrations.py        #   System integrations + extensions (722 lines)
│   ├── procedural_memory.py   #   Skill templates (315 lines)
│   ├── api_server.py          #   REST API server (312 lines)
│   ├── workspace_adapters.py  #   Global workspace adapters (299 lines)
│   ├── model_router.py        #   AI model routing (237 lines)
│   ├── proactive_engine.py    #   Anticipatory suggestions (224 lines)
│   ├── voice_modulator.py     #   Emotion/voice control (212 lines)
│   ├── workspace_context.py   #   Workspace state summaries (192 lines)
│   ├── _agi_imports.py        #   Cognitive module import wiring (186 lines)
│   ├── findings_bus.py        #   Inter-agent communication bus (170 lines)
│   └── workspace_events.py    #   Event taxonomy (74 lines)
│
├── actions/                   # ⚡ Tool actions (21,000+ lines)
│   ├── security_tools.py      #   35+ security actions (1,083 lines)
│   ├── cognitive_coder.py     #   Cognitive coding orchestrator (1,068 lines)
│   ├── holo_builder.py        #   Iron Man AR builder (3,921 lines)
│   ├── holo_earth.py          #   Gesture-controlled Google Earth (1,104 lines)
│   ├── holographic_map.py     #   3D globe (1,193 lines)
│   ├── browser_control.py     #   Browser automation (1,008 lines)
│   ├── code_helper.py         #   Code write/edit/run (791 lines)
│   ├── dev_agent.py           #   Project generation (698 lines)
│   ├── computer_control.py    #   Mouse/keyboard (577 lines)
│   ├── send_message.py        #   Cross-platform messaging (588 lines)
│   ├── screen_processor.py    #   Screen capture + analysis (556 lines)
│   ├── ai_pipeline.py         #   Text processing pipelines (412 lines)
│   ├── web_search.py          #   Quick search (233 lines)
│   ├── web_research.py        #   Deep research (257 lines)
│   ├── youtube_video.py       #   YouTube integration (534 lines)
│   ├── reminder.py            #   Task scheduler reminders (589 lines)
│   ├── verification.py        #   Action verification (354 lines)
│   ├── file_controller.py     #   Full file system operations (784 lines)
│   ├── game_updater.py        #   Steam/Epic game updates (1,133 lines)
│   ├── computer_settings.py   #   System settings (1,067 lines)
│   ├── desktop.py             #   Wallpaper, organize, stats (689 lines)
│   ├── agency_agent.py        #   24+ specialized expert agents (302 lines)
│   ├── holo_globe.py          #   Holographic globe v5 (270 lines)
│   ├── weather_report.py      #   Weather forecasts (130 lines)
│   ├── flight_finder.py       #   Google Flights search (542 lines)
│   ├── ac_controller.py       #   Air conditioner control (552 lines)
│   └── open_app.py            #   Application launcher (376 lines)
│
├── cyber/                     # 🛡️ Cyber Security Toolkit (9,600+ lines)
│   ├── agents/                #   7 specialized security agents
│   │   ├── recon_agent.py     #     Subdomain enum, port scanning, tech detection
│   │   ├── hunter_agent.py    #     Vuln hunting (code + dynamic)
│   │   ├── exploit_agent.py   #     PoC execution specialist
│   │   ├── chain_agent.py     #     A→B exploit chain builder
│   │   ├── verify_agent.py    #     3-round adversarial verification
│   │   ├── grader_agent.py    #     5-axis scoring (SUBMIT/HOLD/SKIP)
│   │   └── report_agent.py    #     Submission-ready reports
│   ├── exploit_templates/     #   9 vuln-class exploit templates
│   │   ├── sqli.py            #     SQL injection (blind, time, error, UNION)
│   │   ├── xss.py             #     Cross-site scripting (reflected, DOM, polyglot)
│   │   ├── ssrf.py            #     Server-side request forgery
│   │   ├── idor.py            #     Insecure direct object reference
│   │   ├── auth_bypass.py     #     JWT, OAuth, default creds
│   │   ├── command_inj.py     #     OS command injection
│   │   ├── path_traversal.py  #     LFI / directory traversal
│   │   ├── cors.py            #     CORS misconfiguration
│   │   ├── open_redirect.py   #     Open redirect
│   │   └── template.py        #     Base exploit class
│   ├── exploit_engine.py      #   Live PoC execution engine
│   ├── mcp_state_machine.py   #   FSM controller (717 lines)
│   ├── data_flow_analyzer.py  #   Source→sink data flow tracing
│   ├── business_logic_tester.py # Invariant discovery + fuzzers
│   ├── ast_parser.py          #   Multi-lang AST extraction (799 lines)
│   ├── flow_graph.py          #   Data flow path graph
│   ├── source_sink_db.py      #   Security source/sink patterns
│   ├── llm_evaluator.py       #   LLM sanitization evaluation
│   ├── wave_manager.py        #   Parallel wave coordination
│   ├── harness_modes.py       #   fast/standard/deep/loop/code
│   ├── correlator.py          #   Static-dynamic correlation
│   ├── dead_end_tracker.py    #   Negative result memory
│   ├── bypass_tables.py       #   8 vuln-category reference tables
│   ├── mythos_pipeline.py     #   7-agent static code analysis
│   └── mcp_server.py          #   MCP security tool server
│
├── security/                  # 🔒 Permission & audit (1,311 lines)
│   ├── permission_manager.py  #   Tool access control
│   ├── audit_logger.py        #   Action audit trail
│   ├── tools_guard.py         #   Rate limiting, SSRF checks
│   ├── input_sanitizer.py     #   Input validation
│   ├── config_validator.py    #   Config validation
│   └── lock_state.py          #   System lock state
│
├── skills/                    # 🎯 Skill engine (2,980+ lines)
│   ├── research_agent.py      #   Autonomous research + knowledge graph (779 lines)
│   ├── creative_studio.py     #   Story planning + world building + characters (724 lines)
│   ├── document_intelligence.py # Contract review + argument mapping + bias detection (959 lines)
│   ├── cognitive_gating.py    #   Complexity assessment
│   ├── working_memory.py      #   Active context
│   ├── meta_reflect.py        #   Metacognition
│   ├── decision_journal.py    #   Decision logging
│   ├── experience_replay.py   #   Template learning
│   ├── adaptive_planner.py    #   Strategy optimization
│   ├── screen_watcher.py      #   Screen intelligence
│   ├── deep_dive.py           #   Research agent
│   ├── auto_doc.py            #   Documentation gen
│   ├── digital_twin.py        #   Style mimicry
│   ├── sentinel.py            #   System monitoring
│   ├── social_pulse.py        #   Trending topics
│   ├── neural_clipboard.py    #   Clipboard history
│   ├── definitions/           #   24 SKILL.md files
│   └── engine/                #   Skill loader/registry
│
├── agent/                     # 🤖 Task execution (1,628 lines)
│   ├── task_queue.py          #   Async task management
│   ├── executor.py            #   Task execution
│   ├── planner.py             #   Task planning
│   └── error_handler.py       #   Error recovery
│
├── agents/                    # 👥 Expert agent personas (30 agents)
│   ├── engineering/           #   17 engineering agents
│   ├── testing/               #   5 testing agents
│   ├── design/                #   2 design agents
│   └── specialized/           #   4 specialized agents
│
├── gesture_music_system/      # 🎵 Gesture control (1,998 lines)
│   ├── main.py                #   Recognition system
│   ├── model.py               #   LSTM classifier
│   ├── actions.py             #   Media key controls
│   ├── utils.py               #   Landmark processing
│   ├── train.py               #   Model training
│   └── collect_data.py        #   Data collection
│
├── research_reports/          # 📊 Research reports
│
├── assets/
│   └── [CesiumJS removed - now using holo_earth.py (Google Earth)]
│
├── config/                    # ⚙️ Configuration
├── core/prompt.txt            # System prompt
├── memory/                    # Memory management
└── docs/                      # Design docs & plans
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI Models** | Gemini 2.5 Flash (Live API), Anthropic Claude |
| **Language** | Python 3.11 – 3.12 (3.13+ not supported — MediaPipe has no wheels) |
| **Voice** | Gemini Live API, sounddevice |
| **Vision** | MediaPipe (hands, face), OpenCV |
| **ML** | TensorFlow (LSTM gesture model) |
| **3D Rendering** | Pygame + OpenGL (immediate mode) |
| **Globe** | Google Earth (Edge app mode), OpenGL |
| **Browser** | Playwright, Selenium |
| **Automation** | PyAutoGUI |
| **System** | psutil, subprocess |
| **Storage** | JSON, JSONL, SQLite |
| **Frontend** | Tkinter |
| **Networking** | google-genai, urllib, websockets |
| **Security Tools** | nmap, nuclei, sqlmap, ffuf, gobuster, subfinder, httpx, nikto (via WSL/Kali) |
| **Data Analysis** | Polars, Pandas, Matplotlib |
| **API Server** | FastAPI, Uvicorn, Pydantic |
| **NLP** | LangChain, LangGraph, tiktoken |
| **Cloud** | boto3 (AWS), azure-storage-blob (Azure) |
| **Audio** | sounddevice, soundfile, edge-tts, pyttsx3, pydub |
| **ML Vision** | MediaPipe, OpenCV, TensorFlow |

---

## 📲 Telegram Bridge Setup

FRIDAY can send and receive Telegram messages via your own personal bot — fully two-way.

### Step 1 — Create your Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts to name your bot
4. BotFather will give you a token like `7xxxxxxxxx:AAF...` — copy it

### Step 2 — Get your User ID

1. Search **@userinfobot** on Telegram
2. Send any message
3. It will reply with your numeric User ID

### Step 3 — Configure telegram\_bot.py

Open `Config\api_keys` and fill in your credentials:

```python
BOT_TOKEN = "your_bot_token_here"
ALLOWED_USER = your_user_id_here  # just the number, no quotes
```
### Step 4 — Test it

Send a message to your bot on Telegram and FRIDAY will respond. You can also tell JARVIS by voice to send you a Telegram message and it will push it to your phone.


## 📦 Installation

### Prerequisites

- Python 3.12+ 
- Git
- Windows (primary), Linux (partial), macOS (partial)

> **⚠️ Platform Note:** F.R.I.D.A.Y. is built and tested primarily on **Windows**. Some features (desktop control, system notifications, audio routing, gesture control) rely on Windows-specific APIs and may not work fully on Linux or macOS. For the best experience, use Windows 10/11.

> **🍎 macOS Note:** The following features are **not available** on macOS due to Windows-only dependencies:
> - **Audio volume control** (`pycaw`) — used by gesture music system and system settings
> - **Window management** (`pygetwindow`) — used by verification and game updater
> - **Screen brightness control** — used by system settings
> - **Windows toast notifications** (`win10toast`) — `plyer` notifications still work as a fallback
>
> All core features (voice, memory, brain modules, cybersecurity, web automation, AI pipeline) work on macOS.

- 4GB+ RAM
- Microphone + Speaker (for voice)
- Webcam (optional, for gestures/AR)

### Quick Start

### Step 1 — Clone the repository

```bash
git clone https://github.com/subhansh-dev/Friday-Autonomous-Cognitive-AI-Operating-System
cd Friday
```

### Step 2 — Create a virtual environment

> **🪟 Windows is the recommended platform.** Desktop control, system notifications, audio routing, and gesture features work best (or only) on Windows.

**Windows (recommended):**

```powershell
python -m venv friday_env
friday_env\Scripts\activate
```

**Linux / macOS:**

```bash
python3 -m venv friday_env
source friday_env/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Install Playwright browsers

```bash
playwright install
playwright install chromium
```

### Step 5 — Set up your config

 open `config/api_keys.json` and fill in your details:

```json
{
    "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
    "os_system": "windows"
}
```

You can get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com/app/apikey).

### Step 6 — Launch FRIDAY

```bash
python main.py
```

On first launch, FRIDAY will open a setup window where you can enter your API key and select your OS. After that it boots automatically every time.

---

## ⚙️ Configuration

| File | Purpose |
|------|---------|
| `config/api_keys.json` | API keys and provider selection |
| `core/prompt.txt` | System personality prompt |
| `SOUL.md` | Identity and behavioral guidelines |
| `AGENTS.md` | Workspace conventions |
| `TOOLS.md` | Local environment notes |
| `health.json` | Runtime health status |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `FRIDAY_TELEGRAM_TOKEN` | Telegram bot token |
| `FRIDAY_API_PORT` | REST API port (default: 8899) |

---

## 📖 Usage

### Voice Interaction
Just speak naturally. Friday responds via voice and displays in the HUD.

### Tool Calling
Friday automatically selects the right tool:
```
"Search the web for Python tutorials"     → web_search
"Check my project for vulnerabilities"    → security_tools(mythos_scan) + cyber_reasoning
"Set a reminder for 3pm"                  → reminder
"Draw something in 3D"                    → holo_builder
```

### Security Scanning
```bash
# Code analysis (static — no confirmation needed)
security_tools(action="mythos_scan", target="/path/to/project")

# Full cognitive assessment
cyber_reasoning(action="start", target="example.com")
cyber_reasoning(action="recon", recon_data={...})
cyber_reasoning(action="verify")
cyber_reasoning(action="grade")
cyber_reasoning(action="report")
```

### 🔒 Cybersecurity Confirmation Protocol

FRIDAY requires user confirmation before performing active cyber operations. This is a safety gate to prevent accidental or unauthorized scanning.

| Tier | Operations | Confirmation |
|------|-----------|-------------|
| **Tier 1** | Passive recon (WHOIS, DNS, subfinder), local code analysis (mythos_scan), header checks | ❌ Not needed |
| **Tier 2** | Active scanning (nmap, nuclei, ffuf, sqlmap, gobuster), injection testing, CORS testing | ✅ Type `confirm` |
| **Tier 3** | Active exploitation, privilege escalation, post-exploitation | ✅ `confirm` + explicit go-ahead |

**How it works:**

```
You:    "Scan example.com for vulnerabilities"
FRIDAY: "Right, Sir. I'll run subfinder for subdomains, httpx to probe
         live hosts, then nuclei for vuln scanning on example.com.
         This will send active requests to the target.
         Type `confirm` to proceed."
You:    "confirm"
FRIDAY: *runs the scan*
```

- Confirmation is **per-action-group** (one confirm covers a planned chain of tools)
- Say "no confirmation needed" or "just do it" to skip for a specific task
- Passive recon (OSINT, DNS, subdomain enum) runs immediately without confirmation
- Local code analysis (mythos_scan on your own files) runs without confirmation

### Voice Control
```bash
voice_control(emotion="happy")
voice_control(voice="puck")
```

---

## ⚠️ LEGAL DISCLAIMER & WARNING

### CRITICAL — READ CAREFULLY BEFORE USING

**F.R.I.D.A.Y. CONTAINS ADVANCED CYBERSECURITY CAPABILITIES INCLUDING:**

- Multi-agent vulnerability scanning (Mythos 7-agent pipeline)
- Cognitive security reasoning with adversarial verification
- Exploit chain discovery and analysis
- Pattern-based vulnerability detection
- CVSS scoring and severity assessment
- Supply chain security scanning
- Penetration testing tool integration (nmap, nuclei, ffuf, sqlmap, etc.)

### ⚡ INTENDED USE ONLY

This software is intended **EXCLUSIVELY** for:

1. **Authorized Security Research** — Testing systems you own or have explicit written permission to test
2. **Educational Purposes** — Learning about cybersecurity in controlled lab environments
3. **Defensive Operations** — Securing your own infrastructure and applications
4. **Bug Bounty Programs** — Participating in authorized programs with proper scope

### 🚫 PROHIBITED USES

**YOU MUST NOT USE FRIDAY FOR:**

- Any illegal or unauthorized activities
- Attacking systems without explicit authorization
- Any form of cybercrime
- Unauthorized access to computer systems
- Malicious exploitation of vulnerabilities
- Any activity that violates applicable laws or regulations
- Gaining unauthorized access to data or systems
- Any harmful or malicious purposes

### 📜 LIABILITY STATEMENT

**By cloning, using, or modifying this software, you agree to the following:**

1. **Creator Disclaimer** — The creator (Subhansh) provides this software "AS IS" without warranty of any kind.

2. **No Responsibility** — The creator shall NOT be held liable for:
   - Any illegal use of this software
   - Any damage to computer systems or data
   - Any legal consequences arising from misuse
   - Any unauthorized access or exploitation
   - Any negative consequences whatsoever

3. **User Responsibility** — You are solely responsible for:
   - Obtaining proper authorization before testing any system
   - Ensuring your use is legal and ethical
   - Understanding and complying with all applicable laws
   - The consequences of your actions

4. **Authorization Requirement** — You must have explicit written permission from the system owner before:
   - Scanning any network or system
   - Testing for vulnerabilities
   - Attempting any form of exploitation
   - Accessing any system you do not own

5. **Local Machine Protection** — F.R.I.D.A.Y. is programmed to refuse targeting:
   - localhost / 127.0.0.1
   - Your local machine's IP addresses
   - Your home network (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
   - Any system without authorization

### 🔒 SECURITY ETHICS

If you encounter security vulnerabilities while using this tool:

- **DO NOT** exploit them for malicious purposes
- **DO** report them to the system owner/vendor
- **DO** follow responsible disclosure practices
- **DO NOT** share sensitive findings publicly without coordination

---

## 🤝 Contributing

Contributions welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

```bash
# Development setup
git clone https://github.com/subhansh-dev/Friday.git
cd Friday
pip install -r requirements.txt
python main.py
```

---

## 📄 License

FRIDAY License v1.0 (Business Source License 1.1 with Cybersecurity Liability Addendum) — see [LICENSE](LICENSE).

Non-commercial use is free. Commercial use requires a separate license.
After May 2029, the code becomes available under Apache 2.0.

---

## 📧 Contact

- **Creator**: Subhansh
- **GitHub**: [github.com/subhansh-dev](https://github.com/subhansh-dev)
- **Issues**: [GitHub Issues](https://github.com/subhansh-dev/Friday-Autonomous-Cognitive-AI-Operating-System/isues)

<sub>no uni no cs major</sub>



---

<p align="center">
  <sub>Built with obsession by Subhansh · F.R.I.D.A.Y. v10.6</sub>
</p>
