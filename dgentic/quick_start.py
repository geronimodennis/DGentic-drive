"""Quick start guide and demo for DGentic."""
import asyncio
import sys
import os

# Add to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.types import Task, AgentRole
from core.orchestrator import get_orchestrator
from agents.agent import get_agent_pool
from memory.memory_system import get_memory_system
from tools.runtime import get_tool_registry
from loguru import logger

# Configure logging
from config.logging_config import configure_logging
configure_logging()


async def demo_task_execution():
    """Demo: Execute a simple task."""
    print("\\n" + "="*60)
    print("DEMO 1: Task Execution")
    print("="*60)
    
    orchestrator = get_orchestrator()
    
    # Create and submit a task
    task = Task(
        id="demo_task_1",
        title="Generate Python Function",
        description="Write a Python function to calculate fibonacci sequence",
        priority=1,
        constraints=["Must be efficient", "Must handle edge cases"],
    )
    
    print(f"\\nSubmitting task: {task.title}")
    orchestrator.submit_task(task)
    
    # Simulate processing
    print("Processing task...")
    result = await orchestrator.process_task(task)
    
    print(f"\\nTask Status: {result.status.value}")
    if result.result:
        print(f"Result: {result.result}")


async def demo_multi_agent_collaboration():
    """Demo: Multi-agent collaboration."""
    print("\\n" + "="*60)
    print("DEMO 2: Multi-Agent Collaboration")
    print("="*60)
    
    agent_pool = get_agent_pool()
    orchestrator = get_orchestrator()
    
    # Show available agents
    print("\\nAvailable Agents:")
    for agent in agent_pool.list_agents():
        print(f"  - {agent.name} ({agent.role.value})")
    
    # Create complex task
    task = Task(
        id="demo_task_2",
        title="Complex Data Processing Pipeline",
        description="Build a pipeline to process, analyze, and validate large datasets",
        priority=2,
        constraints=[
            "Must be scalable",
            "Must validate data quality",
            "Must generate report",
        ],
    )
    
    print(f"\\nSubmitting complex task: {task.title}")
    orchestrator.submit_task(task)
    
    result = await orchestrator.process_task(task)
    
    print(f"\\nTask completed with {len(result.subtasks)} subtasks")
    print(f"Final Status: {result.status.value}")


def demo_memory_system():
    """Demo: Memory system."""
    print("\\n" + "="*60)
    print("DEMO 3: Memory System")
    print("="*60)
    
    memory = get_memory_system()
    
    # Add memories
    print("\\nAdding memories...")
    memories = [
        {
            "content": "Python is a high-level programming language",
            "tags": ["python", "programming"],
            "category": "programming",
        },
        {
            "content": "Machine learning models require large datasets",
            "tags": ["ml", "data"],
            "category": "machine_learning",
        },
        {
            "content": "REST APIs use HTTP methods for operations",
            "tags": ["api", "rest"],
            "category": "web_development",
        },
    ]
    
    for i, mem_data in enumerate(memories):
        mem = memory.add_memory(
            content=mem_data["content"],
            embedding=[0.1 * (i+1)] * 1536,  # Placeholder embeddings
            tags=mem_data["tags"],
            category=mem_data["category"],
        )
        print(f"  ✓ Added memory: {mem_data['content'][:40]}...")
    
    # Search by tag
    print("\\nSearching by tag 'python':")
    results = memory.search_by_tag("python")
    for mem in results:
        print(f"  - {mem.content}")
    
    # Get statistics
    stats = memory.get_statistics()
    print(f"\\nMemory Statistics:")
    print(f"  Total Memories: {stats['total_memories']}")
    print(f"  Categories: {stats['categories']}")
    print(f"  Tags: {stats['tags']}")


def demo_tool_creation():
    """Demo: Create and manage tools."""
    print("\\n" + "="*60)
    print("DEMO 4: Tool Creation & Management")
    print("="*60)
    
    registry = get_tool_registry()
    
    # Create a simple tool
    print("\\nCreating a new tool...")
    tool_code = '''
def greet(name):
    return f"Hello, {name}!"

def add(a, b):
    return a + b

# Test
print(greet("User"))
print(f"2 + 2 = {add(2, 2)}")
'''
    
    tool = registry.create_tool(
        name="demo_tool",
        description="A simple demonstration tool with greeting and math functions",
        source_code=tool_code,
    )
    
    print(f"  ✓ Tool created: {tool.name}")
    print(f"    ID: {tool.id[:8]}...")
    print(f"    Permission Level: {tool.permission_level.value}")
    
    # List tools
    print(f"\\nAvailable Tools: {len(registry.list_tools())}")
    for t in registry.list_tools()[:5]:
        print(f"  - {t.name}: {t.description}")


def demo_agent_pool():
    """Demo: Agent pool management."""
    print("\\n" + "="*60)
    print("DEMO 5: Agent Pool Management")
    print("="*60)
    
    agent_pool = get_agent_pool()
    
    print("\\nAll Agents:")
    for agent in agent_pool.list_agents():
        info = agent.get_info()
        print(f"\\n  Name: {info['name']}")
        print(f"  Role: {info['role']}")
        print(f"  Model: {info['model_type']} / {info['model_name']}")
        print(f"  Description: {info['description']}")
    
    # Agents by role
    print("\\n\\nAgents by Role:")
    for role in AgentRole:
        agents = agent_pool.get_agents_by_role(role)
        print(f"  {role.value}: {len(agents)} agent(s)")
        for agent in agents:
            print(f"    - {agent.name}")


async def demo_orchestrator_status():
    """Demo: Check orchestrator status."""
    print("\\n" + "="*60)
    print("DEMO 6: Orchestrator Status")
    print("="*60)
    
    orchestrator = get_orchestrator()
    
    # Get status
    status = orchestrator.get_statistics()
    print(f"\\nOrchestrator Status:")
    print(f"  Active Tasks: {status['active_tasks']}")
    print(f"  Active Agents: {status['active_agents']}")
    print(f"  Queue:")
    print(f"    Pending: {status['queue_status']['pending']}")
    print(f"    Processing: {status['queue_status']['processing']}")
    print(f"    Completed: {status['queue_status']['completed']}")
    
    # Agent status
    print(f"\\nAgent Status:")
    for agent_info in orchestrator.get_agent_status():
        print(f"  {agent_info['name']}: {agent_info['active_tasks']} active, {agent_info['completed_tasks']} completed")


async def main():
    """Run all demos."""
    print("\\n" + "="*70)
    print(" " * 15 + "DGentic - Quick Start Demo")
    print("="*70)
    
    try:
        # Run demos
        await demo_task_execution()
        await demo_multi_agent_collaboration()
        demo_memory_system()
        demo_tool_creation()
        demo_agent_pool()
        await demo_orchestrator_status()
        
        print("\\n" + "="*70)
        print("✓ All demos completed successfully!")
        print("="*70)
        
        print("\\nNext Steps:")
        print("  1. Run the API server: python main.py server")
        print("  2. Check API at: http://localhost:8000/docs")
        print("  3. Use CLI: python -m dgentic.cli --help")
        print("  4. Read documentation: docs/DGentic.md")
        
    except Exception as e:
        logger.error(f"Demo error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
