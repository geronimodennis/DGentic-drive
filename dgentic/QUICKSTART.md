# DGentic Quick Start Guide

## Installation

### Prerequisites
- Python 3.10+
- pip or conda
- Git

### Setup

1. **Clone the repository (or navigate to the project)**
```bash
cd dgentic
```

2. **Create a Python virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your API keys and settings
```

5. **Initialize databases (optional)**
```bash
# If using PostgreSQL and Redis
createdb dgentic
redis-server
```

## Running DGentic

### Option 1: API Server

Start the FastAPI server:
```bash
python main.py server
```

The API will be available at `http://localhost:8000`

API Documentation: `http://localhost:8000/docs`

### Option 2: CLI Interface

Use the command-line interface:
```bash
python -m dgentic.cli --help
```

Examples:
```bash
# Submit a task
python -m dgentic.cli task execute "Write a Python function" "Create a fibonacci generator"

# List agents
python -m dgentic.cli agent list

# Search memory
python -m dgentic.cli memory search --tag "important"

# Create a tool
python -m dgentic.cli tool create my_tool "A custom tool" tool_code.py

# Check orchestrator status
python -m dgentic.cli orchestrator status
```

### Option 3: Quick Start Demo

Run the interactive demo:
```bash
python quick_start.py
```

This will showcase:
- Task execution
- Multi-agent collaboration
- Memory system
- Tool creation
- Agent pool management
- Orchestrator status

## API Endpoints

### Tasks
- `POST /tasks` - Submit a new task
- `GET /tasks/{task_id}` - Get task status
- `GET /tasks` - List all tasks

### Agents
- `GET /agents` - List all agents
- `GET /agents/{agent_id}` - Get agent details

### Memory
- `GET /memory/search` - Search memory
- `GET /memory/stats` - Get memory statistics

### Tools
- `POST /tools` - Create a new tool
- `GET /tools` - List all tools
- `GET /tools/{tool_name}` - Get tool details

### Orchestrator
- `GET /orchestrator/status` - Get orchestrator status
- `GET /orchestrator/queue` - Get queue status

### Integrations
- `GET /integrations` - List available integrations
- `POST /integrations/generate` - Generate from external service

### WebSocket
- `WS /ws/tasks` - Real-time task updates

## Example Usage

### Submit a Task via API

```bash
curl -X POST http://localhost:8000/tasks \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Write Python Function",
    "description": "Create a function to parse JSON files",
    "priority": 1,
    "constraints": ["Must handle errors", "Must be efficient"]
  }'
```

### Get Task Status

```bash
curl http://localhost:8000/tasks/{task_id}
```

### List Agents

```bash
curl http://localhost:8000/agents
```

### Search Memory

```bash
curl "http://localhost:8000/memory/search?tag=python"
```

## Creating Custom Tools

1. **Write tool code** (example_tools.py):
```python
def my_function(input_data):
    """Process input and return result."""
    result = input_data.upper()
    return {
        "success": True,
        "result": result
    }
```

2. **Register the tool**:
```python
from tools.runtime import get_tool_registry

registry = get_tool_registry()
tool = registry.create_tool(
    name="my_tool",
    description="My custom tool description",
    source_code=open("my_tool.py").read()
)
```

Or via CLI:
```bash
python -m dgentic.cli tool create my_tool "Tool description" my_tool.py
```

## Creating Workflows

```python
from core.types import Workflow, WorkflowStep, AgentRole

steps = [
    WorkflowStep(
        id="step1",
        name="Plan",
        description="Plan the task",
        agent_role=AgentRole.PLANNER,
    ),
    WorkflowStep(
        id="step2",
        name="Execute",
        description="Execute the plan",
        agent_role=AgentRole.CODER,
        previous_steps=["step1"],
    ),
]

workflow = Workflow(
    id="my_workflow",
    name="My Workflow",
    description="My workflow description",
    steps=steps,
)

orchestrator = get_orchestrator()
orchestrator.submit_workflow(workflow)
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                        │
│              (API / CLI / WebSocket)                    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Orchestrator                           │
│        (Task Planning & Routing)                        │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
    ┌───▼───┐    ┌───▼───┐   ┌───▼───┐
    │ Agents│    │ Models│   │ Tools │
    └───┬───┘    └───┬───┘   └───┬───┘
        │            │            │
    ┌───▼────────────▼────────────▼───┐
    │    Memory System & Vector DB    │
    │      (FAISS + Metadata)         │
    └────────────────────────────────┘
```

## Key Components

- **Orchestrator**: Manages task queue and agent coordination
- **Agents**: Specialized workers (Planner, Coder, Researcher, Validator)
- **Model Router**: Intelligently routes tasks to local or external AI models
- **Memory System**: Vector database for semantic search with O(log n) retrieval
- **Tool Runtime**: Safe execution sandbox for tools
- **Security Layer**: Permission-based action system

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL
psql -U postgres -d dgentic -c "SELECT 1;"

# Check Redis
redis-cli ping
```

### Missing Dependencies
```bash
pip install -r requirements.txt
# Or for specific packages:
pip install faiss-cpu openai pydantic fastapi
```

### Permission Errors
- Check file permissions in root_directory
- Ensure logs_directory is writable
- Verify localmcp_directory exists

### API Not Starting
- Check port 8000 is available
- Verify .env configuration
- Check logs in logs/ directory

## Next Steps

1. **Read the full specification**: `docs/DGentic.md`
2. **Explore examples**: `dgentic/examples/`
3. **Run tests**: `pytest tests/`
4. **Check API docs**: `http://localhost:8000/docs` (when running)
5. **Create custom tools**: See tool creation section
6. **Build workflows**: Combine agents into complex workflows

## Performance Tips

- Use local models for common tasks (faster, free)
- Use external models for complex reasoning
- Batch similar tasks together
- Monitor memory usage with `memory/stats`
- Compress memory regularly

## Support & Resources

- **Documentation**: Read `docs/DGentic.md`
- **Examples**: Check `dgentic/examples/`
- **Tests**: See `tests/` for usage patterns
- **API Docs**: Swagger UI at `/docs`

---

**Version**: 0.1.0  
**Last Updated**: May 2026
