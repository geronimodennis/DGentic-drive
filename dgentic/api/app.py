"""FastAPI application and endpoints."""
from fastapi import FastAPI, HTTPException, WebSocket, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
from datetime import datetime

from config.settings import get_settings
from config.logging_config import configure_logging
from core.orchestrator import get_orchestrator
from core.types import Task, TaskStatus
from agents.agent import get_agent_pool
from memory.memory_system import get_memory_system
from tools.runtime import get_tool_registry, get_tool_runtime
from integrations.ai_services import get_integration_manager
from loguru import logger

# Configure logging
configure_logging()

# Create FastAPI app
settings = get_settings()
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    debug=settings.debug,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class TaskRequest(BaseModel):
    """Task submission request."""
    title: str
    description: str
    priority: int = 0
    context: Optional[Dict[str, Any]] = None
    constraints: Optional[List[str]] = None


class ToolCreateRequest(BaseModel):
    """Tool creation request."""
    name: str
    description: str
    source_code: str


class AgentInfo(BaseModel):
    """Agent information."""
    id: str
    name: str
    role: str
    description: str
    active_tasks: int
    completed_tasks: int


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.api_version,
    }


# Task endpoints
@app.post("/tasks")
async def submit_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Submit a new task for processing."""
    orchestrator = get_orchestrator()
    
    task = Task(
        id="",  # Will be generated
        title=request.title,
        description=request.description,
        priority=request.priority,
        context=request.context or {},
        constraints=request.constraints or [],
    )
    
    orchestrator.submit_task(task)
    
    return {
        "task_id": task.id,
        "status": task.status.value,
        "message": "Task submitted for processing",
    }


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status and result."""
    orchestrator = get_orchestrator()
    
    # Search in queue
    queue_task = orchestrator.task_queue.processing.get(task_id)
    if queue_task:
        return queue_task.model_dump()
    
    # Search in completed
    completed_task = orchestrator.task_queue.completed.get(task_id)
    if completed_task:
        return completed_task.model_dump()
    
    raise HTTPException(status_code=404, detail="Task not found")


@app.get("/tasks")
async def list_tasks():
    """List all tasks."""
    orchestrator = get_orchestrator()
    
    return {
        "queue_status": orchestrator.task_queue.get_status(),
        "active_tasks": list(orchestrator.task_queue.processing.values()),
        "completed_tasks": list(orchestrator.task_queue.completed.values()),
    }


# Agent endpoints
@app.get("/agents")
async def list_agents() -> List[AgentInfo]:
    """List all available agents."""
    agent_pool = get_agent_pool()
    
    agents = []
    for agent in agent_pool.list_agents():
        agents.append(
            AgentInfo(
                id=agent.id,
                name=agent.name,
                role=agent.role.value,
                description=agent.description,
                active_tasks=len(agent.active_tasks),
                completed_tasks=len(agent.completed_tasks),
            )
        )
    
    return agents


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent details."""
    agent_pool = get_agent_pool()
    agent = agent_pool.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return agent.get_info()


# Memory endpoints
@app.get("/memory/search")
async def search_memory(query: Optional[str] = None, tag: Optional[str] = None):
    """Search memory system."""
    memory = get_memory_system()
    
    if tag:
        results = memory.search_by_tag(tag)
    else:
        results = list(memory.memories.values())
    
    return {
        "results": [m.model_dump() for m in results[:10]],
        "total": len(results),
    }


@app.get("/memory/stats")
async def get_memory_stats():
    """Get memory system statistics."""
    memory = get_memory_system()
    return memory.get_statistics()


# Tool endpoints
@app.post("/tools")
async def create_tool(request: ToolCreateRequest):
    """Create a new tool."""
    registry = get_tool_registry()
    
    tool = registry.create_tool(
        name=request.name,
        description=request.description,
        source_code=request.source_code,
    )
    
    return tool.model_dump()


@app.get("/tools")
async def list_tools():
    """List all available tools."""
    registry = get_tool_registry()
    
    return {
        "tools": [t.model_dump() for t in registry.list_tools()],
        "total": len(registry.tools),
    }


@app.get("/tools/{tool_name}")
async def get_tool(tool_name: str):
    """Get tool details."""
    registry = get_tool_registry()
    tool = registry.get_tool(tool_name)
    
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    return tool.model_dump()


# Orchestrator endpoints
@app.get("/orchestrator/status")
async def get_orchestrator_status():
    """Get orchestrator status."""
    orchestrator = get_orchestrator()
    return orchestrator.get_statistics()


@app.get("/orchestrator/queue")
async def get_queue_status():
    """Get queue status."""
    orchestrator = get_orchestrator()
    return orchestrator.get_queue_status()


# Integration endpoints
@app.get("/integrations")
async def list_integrations():
    """List available integrations."""
    manager = get_integration_manager()
    
    return {
        "services": manager.list_services(),
        "available": len(manager.list_services()),
    }


@app.post("/integrations/generate")
async def generate_from_service(
    service: str,
    prompt: str,
    model: Optional[str] = None,
):
    """Generate text from external service."""
    manager = get_integration_manager()
    
    try:
        kwargs = {"model": model} if model else {}
        response = await manager.generate(service, prompt, **kwargs)
        return {"service": service, "response": response}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# WebSocket for real-time updates
@app.websocket("/ws/tasks")
async def websocket_tasks(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates."""
    await websocket.accept()
    orchestrator = get_orchestrator()
    
    try:
        while True:
            # Send status updates every second
            status = orchestrator.get_statistics()
            await websocket.send_json(status)
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


@app.on_event("startup")
async def startup_event():
    """Startup event."""
    logger.info("DGentic API starting")
    
    # Start orchestrator in background
    orchestrator = get_orchestrator()
    # Note: In production, run orchestrator.start_processing_loop() in a separate task


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event."""
    logger.info("DGentic API shutting down")
    
    orchestrator = get_orchestrator()
    orchestrator.stop_processing()
    
    # Save persistent data
    memory = get_memory_system()
    memory.save()


# Error handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Generic exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
