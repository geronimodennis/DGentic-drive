# DGentic --- Advanced Autonomous AI Agent Platform

Create **DGentic**, an advanced autonomous AI agent platform with the following capabilities:

---

## 1. Core Capabilities
- Load and run local AI models
- Natively load AI models or utilize Ollama and LLM Studio to load local models or cloud models
- Integrate with external AI services (Copilot, Google AI, GPT, DeepSeek), including authentication/login support and unified interface
- Hybrid workload orchestration (local vs external routing based on cost, latency, complexity, reliability)

### Dynamic Task Delegation & Agent Spawning
- Analyze workload and spawn sub-agents dynamically
- Use different local or external models per agent
- Provide each agent: Task brief, Context and constraints, Required data
- Validate outputs via cross-checking and reconciliation

---

## 2. System Interaction
### File System (Strictly Guarded)
- Read/write/delete files only within assigned root directory

### CLI Integration
- Execute and interpret command-line operations safely

### Internet Access
- Web search, retrieval, and summarization

---

## 3. Memory & Cognitive Optimization
### Compression
- Use TurboQuant or vector clustering to compress long-term memory

### Recursive Indexing
- All Skills and Memories must be indexed in metadata table
- Target performance: O(1) lookup, O(log n) retrieval
- Metadata: tags, category, relevance, usage, timestamps

### Persistence
- Maintain state file for full session resumption

### Retrieval System
- Hybrid: index + semantic vector search

### Continuity
- Maintain full cross-session reasoning context

---

## 4. Autonomy & Intelligence
- Task planning and decomposition
- Execution with adaptive correction
- Self-improvement via skills, agents, workflows
- Research and synthesis
- Clarification when ambiguous

---

## 5. Workflow, Multi-Agent System & Tooling
### Sub-agents & Skills
- Manage reusable skills/modules
- Parallel and sequential workflows

### Agent Coordination
- Cross-agent communication
- Output reconciliation

### Dynamic Tool Creation (Self-Extensibility)
- **Trigger Sources:** Main agent, Sub-agents, Skills/modules
- **Tool Generation:** Create tools (e.g., Python scripts like PDF generators) when needed
- **Storage:** `rootDir/localmcp/[tool_name]/` (Source code, Metadata, Interface wrapper)
- **Registration:** Tools stored in memory/skill index; reusable by all agents
- **Permission Model:** Tools inherit system permission levels (Autopilot-safe or Approval-required)
- **Governance:** Avoid duplication, version tools, track usage/reliability, deprecate unsafe tools

---

## 6. Security & Guardrails
- Permission-based action system: Autopilot mode and Approval-required mode
- Strict boundaries: File system sandboxing, CLI validation, API restrictions, Tool isolation
- Logging for all actions

---

## 7. Post-Session Behavior
- Summarize: actions, learned knowledge, created tools/skills
- Optimize memory: remove noise, compress and re-index

---

## 8. Interface Ecosystem & Platform Access
### A. Unified AI Chat Interface
- **Dynamic Threading:** View orchestrator reasoning alongside sub-agent task progress.
- **Rich Media Support:** Integrated rendering for Markdown, LaTeX, and code snippets.
- **Action Logs:** Collapsible side-panel for real-time CLI and File System logs.
- **Human-in-the-Loop:** Interactive prompts for "Approval-required" actions within the chat flow.

### B. VS Code Plugin (Extension)
- **Command Palette Integration:** Trigger DGentic tasks directly from the editor.
- **Inline Ghost Text:** AI-driven code completion and refactoring powered by the DGentic orchestrator.
- **Sidebar Workspace:** View active sub-agents, memory status, and current task decomposition.
- **Tool Execution:** Preview and run agent-generated tools from the `localmcp` directory directly in VS Code.

### C. Performance & Analytics Dashboard
- **Visual Dashboards:** Performance monitoring for latency, token usage, and memory health.
- **Usage Metrics:** "Hero Metrics" per skill/tool and per-model cost analysis.

---

## 9. DGentic System Architecture & Tech Stack
- **Orchestrator:** Python, FastAPI, Pydantic, Celery/Temporal
- **Multi-Agent System:** asyncio, Redis, optional Ray
- **Model Router:** Custom routing layer for local vs external decisions
- **Memory System:** Vector DB (FAISS/Qdrant), Metadata DB (PostgreSQL), Cache (Redis)
- **Tool Runtime:** Python tool execution system, Sandbox (Docker/subprocess)
- **UI/Frontend:** Next.js (Web Interface), TypeScript/Node.js (VS Code Extension API)

---

## 10. UI Configuration Settings (Extended)

### A. AI Providers & Routing
- **Local Runtimes:** Toggle/Port config for Ollama and LM Studio.
- **Cloud API Keys:** Encrypted vault for OpenAI, Google, DeepSeek, Anthropic.
- **Routing Rules:** Max-cost-per-task thresholds and role-to-model mapping.
- **Hardware Limits:** GPU VRAM/CPU thread caps for local models.

### B. VS Code Extension Configuration
- **Server Connection:** Set the API endpoint and authentication token for the DGentic backend.
- **Code Indexing:** Toggle local codebase embedding for improved context-aware coding.
- **Auto-Sync:** Option to automatically sync `localmcp` tools into the VS Code environment.

### C. Security & System Boundaries
- **FileSystem Jail:** Set and lock `rootDir` path.
- **CLI Guardrails:** Command blacklist management and execution mode toggle (Autopilot vs. Approval).
- **Network Policy:** Web search enable/disable and domain whitelisting.

### D. Memory & Cognitive Tuning
- **Vector DB Settings:** Backend selection (FAISS/Qdrant) and persistence toggles.
- **Compression Logic:** Adjust TurboQuant ratios and summarization triggers.
- **Session Continuity:** Enable/disable cross-session state resumption.

### E. Tooling & Orchestration
- **Skill Governance:** Auto-registration toggle and human-in-the-loop code review for new tools.
- **Agent Blueprints:** Default system prompt templates and constraint definitions.
- **Workflow Control:** Toggle between sequential and parallel agent execution.

## End of Specification
