"""Command-line interface for DGentic."""
import asyncio
import click
from typing import Optional
from tabulate import tabulate
from core.orchestrator import get_orchestrator
from core.types import Task, AgentRole, PermissionLevel
from agents.agent import get_agent_pool
from memory.memory_system import get_memory_system
from tools.runtime import get_tool_registry, get_tool_runtime
from security.permissions import get_permission_engine
from integrations.ai_services import get_integration_manager
from config.settings import get_settings
from config.logging_config import configure_logging
from loguru import logger


# Configure logging
configure_logging()


@click.group()
def cli():
    """DGentic - Advanced Autonomous AI Agent Platform."""
    pass


# Task commands
@click.group()
def task():
    """Manage tasks."""
    pass


@task.command()
@click.argument("title")
@click.argument("description")
@click.option("--priority", default=0, help="Task priority")
@click.option("--constraint", multiple=True, help="Task constraints")
def execute(title: str, description: str, priority: int, constraint: tuple):
    """Execute a new task."""
    orchestrator = get_orchestrator()
    
    task_obj = Task(
        id="",
        title=title,
        description=description,
        priority=priority,
        constraints=list(constraint),
    )
    
    orchestrator.submit_task(task_obj)
    
    click.echo(f"✓ Task submitted: {task_obj.id}")
    click.echo(f"  Title: {title}")
    click.echo(f"  Status: {task_obj.status.value}")


@task.command()
@click.argument("task_id")
def status(task_id: str):
    """Get task status."""
    orchestrator = get_orchestrator()
    
    # Check in processing
    if task_id in orchestrator.task_queue.processing:
        task = orchestrator.task_queue.processing[task_id]
    elif task_id in orchestrator.task_queue.completed:
        task = orchestrator.task_queue.completed[task_id]
    else:
        click.echo(f"✗ Task not found: {task_id}")
        return
    
    click.echo(f"\nTask Details:")
    click.echo(f"  ID: {task.id}")
    click.echo(f"  Title: {task.title}")
    click.echo(f"  Status: {task.status.value}")
    click.echo(f"  Priority: {task.priority}")
    
    if task.assigned_agent:
        click.echo(f"  Assigned to: {task.assigned_agent}")
    
    if task.result:
        click.echo(f"  Result: {task.result}")
    
    if task.error:
        click.echo(f"  Error: {task.error}")


@task.command()
def list():
    """List all tasks."""
    orchestrator = get_orchestrator()
    status = orchestrator.task_queue.get_status()
    
    click.echo("\nTask Queue Status:")
    click.echo(f"  Pending: {status['pending']}")
    click.echo(f"  Processing: {status['processing']}")
    click.echo(f"  Completed: {status['completed']}")


# Agent commands
@click.group()
def agent():
    """Manage agents."""
    pass


@agent.command()
def list():
    """List all agents."""
    agent_pool = get_agent_pool()
    
    agents = []
    for a in agent_pool.list_agents():
        agents.append([
            a.id[:8],
            a.name,
            a.role.value,
            len(a.active_tasks),
            len(a.completed_tasks),
        ])
    
    headers = ["ID", "Name", "Role", "Active", "Completed"]
    click.echo("\n" + tabulate(agents, headers=headers, tablefmt="grid"))


@agent.command()
@click.argument("agent_id")
def info(agent_id: str):
    """Get agent information."""
    agent_pool = get_agent_pool()
    agent = agent_pool.get_agent(agent_id)
    
    if not agent:
        click.echo(f"✗ Agent not found: {agent_id}")
        return
    
    info_dict = agent.get_info()
    click.echo("\nAgent Information:")
    for key, value in info_dict.items():
        click.echo(f"  {key}: {value}")


# Memory commands
@click.group()
def memory():
    """Manage memory system."""
    pass


@memory.command()
@click.option("--tag", help="Filter by tag")
@click.option("--category", help="Filter by category")
@click.option("--limit", default=10, help="Number of results")
def search(tag: Optional[str], category: Optional[str], limit: int):
    """Search memory."""
    mem_sys = get_memory_system()
    
    if tag:
        results = mem_sys.search_by_tag(tag)[:limit]
        click.echo(f"\nMemories with tag '{tag}':")
    elif category:
        results = mem_sys.search_by_category(category)[:limit]
        click.echo(f"\nMemories in category '{category}':")
    else:
        results = list(mem_sys.memories.values())[:limit]
        click.echo("\nRecent memories:")
    
    for mem in results:
        click.echo(f"\n  ID: {mem.id[:8]}...")
        click.echo(f"  Content: {mem.content[:50]}...")
        click.echo(f"  Category: {mem.category}")
        click.echo(f"  Tags: {', '.join(mem.tags) or 'None'}")


@memory.command()
def stats():
    """Get memory statistics."""
    mem_sys = get_memory_system()
    stats = mem_sys.get_statistics()
    
    click.echo("\nMemory System Statistics:")
    click.echo(f"  Total Memories: {stats['total_memories']}")
    click.echo(f"  Categories: {stats['categories']}")
    click.echo(f"  Tags: {stats['tags']}")
    click.echo(f"  Avg Relevance: {stats['avg_relevance']:.2f}")
    click.echo(f"  Total Accesses: {stats['total_accesses']}")


@memory.command()
def compress():
    """Compress memory system."""
    mem_sys = get_memory_system()
    result = mem_sys.compress_memory()
    
    click.echo("\nMemory Compression Result:")
    click.echo(f"  Entries Removed: {result['entries_removed']}")
    click.echo(f"  Remaining: {result['remaining_memories']}")


# Tool commands
@click.group()
def tool():
    """Manage tools."""
    pass


@tool.command()
def list():
    """List all tools."""
    registry = get_tool_registry()
    
    tools = []
    for t in registry.list_tools():
        tools.append([
            t.name,
            t.description[:30] + "..." if len(t.description) > 30 else t.description,
            t.version,
            t.permission_level.value,
            t.usage_count,
        ])
    
    headers = ["Name", "Description", "Version", "Permission", "Usage"]
    click.echo("\n" + tabulate(tools, headers=headers, tablefmt="grid"))


@tool.command()
@click.argument("name")
@click.argument("description")
@click.argument("code_file", type=click.File('r'))
def create(name: str, description: str, code_file):
    """Create a new tool."""
    registry = get_tool_registry()
    
    source_code = code_file.read()
    tool_def = registry.create_tool(
        name=name,
        description=description,
        source_code=source_code,
    )
    
    click.echo(f"✓ Tool created: {tool_def.name}")
    click.echo(f"  ID: {tool_def.id[:8]}...")
    click.echo(f"  Permission Level: {tool_def.permission_level.value}")


@tool.command()
@click.argument("name")
def info(name: str):
    """Get tool information."""
    registry = get_tool_registry()
    tool_def = registry.get_tool(name)
    
    if not tool_def:
        click.echo(f"✗ Tool not found: {name}")
        return
    
    click.echo(f"\nTool Information:")
    click.echo(f"  Name: {tool_def.name}")
    click.echo(f"  Description: {tool_def.description}")
    click.echo(f"  Version: {tool_def.version}")
    click.echo(f"  Permission: {tool_def.permission_level.value}")
    click.echo(f"  Safe: {tool_def.safe}")
    click.echo(f"  Reliability: {tool_def.reliability_score:.2f}")
    click.echo(f"  Usage: {tool_def.usage_count}")


# Orchestrator commands
@click.group()
def orchestrator():
    """Manage orchestrator."""
    pass


@orchestrator.command()
def status():
    """Get orchestrator status."""
    orch = get_orchestrator()
    stats = orch.get_statistics()
    
    click.echo("\nOrchestrator Status:")
    click.echo(f"  Active Tasks: {stats['active_tasks']}")
    click.echo(f"  Active Agents: {stats['active_agents']}")
    click.echo(f"  Queue Status:")
    click.echo(f"    Pending: {stats['queue_status']['pending']}")
    click.echo(f"    Processing: {stats['queue_status']['processing']}")
    click.echo(f"    Completed: {stats['queue_status']['completed']}")


# Integration commands
@click.group()
def integration():
    """Manage integrations."""
    pass


@integration.command()
def list():
    """List available integrations."""
    manager = get_integration_manager()
    services = manager.list_services()
    
    click.echo("\nAvailable Integrations:")
    for service in services:
        click.echo(f"  ✓ {service}")


# Server commands
@click.group()
def server():
    """Manage server."""
    pass


@server.command()
@click.option("--host", default="0.0.0.0", help="Server host")
@click.option("--port", default=8000, help="Server port")
def start(host: str, port: int):
    """Start the DGentic API server."""
    import uvicorn
    from api.app import app
    
    click.echo(f"Starting DGentic API on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


# Main entry point
@click.command()
@click.version_option()
def main():
    """DGentic - Advanced Autonomous AI Agent Platform."""
    pass


# Add command groups to main
cli.add_command(task)
cli.add_command(agent)
cli.add_command(memory)
cli.add_command(tool)
cli.add_command(orchestrator)
cli.add_command(integration)
cli.add_command(server)


if __name__ == "__main__":
    cli()
