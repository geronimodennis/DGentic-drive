# DGentic - Advanced Autonomous AI Agent Platform

An advanced, autonomous AI agent platform that orchestrates multiple specialized agents with hybrid workload distribution, dynamic tool creation, and comprehensive memory management.

## Features

- **Multi-Agent Orchestration**: Spawn and coordinate specialized agents (planner, coder, researcher, validator)
- **Hybrid Model Routing**: Intelligently route tasks to local or external AI services based on cost, latency, and complexity
- **Dynamic Tool Creation**: Agents can create tools on-the-fly with proper validation and sandboxing
- **Persistent Memory System**: Vector-based semantic search with metadata indexing for O(log n) retrieval
- **Security & Guardrails**: Permission-based action system with autopilot and approval-required modes
- **External Integrations**: Support for OpenAI, Google AI, DeepSeek, and custom AI services
- **CLI & API**: FastAPI-based REST API and command-line interface

## Quick Start

### Installation

```bash
pip install -e .
```

### Configuration

Create a `.env` file in the root directory:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dgentic
REDIS_URL=redis://localhost:6379

# External API Keys
OPENAI_API_KEY=your_key_here
GOOGLE_AI_API_KEY=your_key_here
DEEPSEEK_API_KEY=your_key_here

# Security
PERMISSION_MODE=approval_required  # or autopilot
JWT_SECRET_KEY=your_secret_key_here

# Storage
ROOT_DIRECTORY=/path/to/workspace
```

### Running the Server

```bash
dgentic server start
```

### Using the CLI

```bash
# Execute a task
dgentic task execute "Write a Python function to parse JSON"

# List available agents
dgentic agents list

# View memory index
dgentic memory index

# Create a tool
dgentic tool create --name=my_tool --description="My custom tool"
```

## Architecture

```
User/CLI/API
    ↓
API Gateway & Auth
    ↓
Orchestrator (Task Planning & Agent Spawning)
    ├─→ Planner Agent
    ├─→ Coder Agent
    ├─→ Researcher Agent
    └─→ Validator Agent
         ↓
    Model Router (Local vs External)
         ↓
    Tool Runtime (Python Sandbox)
         ↓
    Memory System (Vector DB + Metadata)
         ↓
    Security Layer (Permissions & Logging)
```

## Core Components

### 1. Orchestrator (`core/orchestrator.py`)
- Task planning and decomposition
- Agent spawning and coordination
- Output reconciliation

### 2. Agents (`agents/`)
- **Planner**: Breaks down complex tasks
- **Coder**: Writes and debugs code
- **Researcher**: Gathers and synthesizes information
- **Validator**: Verifies outputs and quality

### 3. Model Router (`models/router.py`)
- Analyzes task complexity
- Scores cost, latency, reliability
- Routes to optimal model (local or external)

### 4. Memory System (`memory/`)
- Vector database for semantic search
- Metadata indexing for fast lookup
- Recursive skill and memory indexing

### 5. Tool Runtime (`tools/runtime.py`)
- Safe Python code execution in sandbox
- Tool creation and registration
- Permission-based execution

### 6. Security Layer (`security/`)
- Permission engine
- Action logging and audit trails
- Policy enforcement

### 7. External Integrations (`integrations/`)
- OpenAI GPT models
- Google AI Gemini
- DeepSeek API
- Web scraping and search

## Project Structure

```
dgentic/
├── core/               # Orchestrator, task planning
├── agents/             # Agent implementations
├── memory/             # Memory system, indexing, retrieval
├── models/             # AI model interfaces and router
├── tools/              # Tool runtime and execution
├── security/           # Permission engine, logging
├── integrations/       # External API clients
├── localmcp/          # Local MCP tool storage
├── api/               # FastAPI endpoints
├── config/            # Configuration management
├── cli/               # CLI commands
└── tests/             # Test suite
```

## Development

### Running Tests

```bash
pytest -v
```

### Code Quality

```bash
black .
flake8 dgentic/
mypy dgentic/
```

## License

MIT

## Support

For issues and questions, visit the GitHub repository.
