"""Orchestrator for task coordination and agent management."""
import uuid
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from core.types import Task, TaskStatus, AgentRole, Workflow, WorkflowStep
from core.exceptions import TaskError
from agents.agent import get_agent_pool, BaseAgent
from models.router import get_model_router
from memory.memory_system import get_memory_system
from loguru import logger


class TaskQueue:
    """Queue for managing tasks."""
    
    def __init__(self):
        """Initialize task queue."""
        self.queue: List[Task] = []
        self.processing: Dict[str, Task] = {}
        self.completed: Dict[str, Task] = {}
    
    def enqueue(self, task: Task) -> None:
        """Add task to queue."""
        self.queue.append(task)
        logger.info(f"Task enqueued: {task.title}")
    
    def dequeue(self) -> Optional[Task]:
        """Remove and return highest priority task."""
        if not self.queue:
            return None
        
        # Sort by priority (higher first)
        self.queue.sort(key=lambda t: t.priority, reverse=True)
        task = self.queue.pop(0)
        self.processing[task.id] = task
        return task
    
    def mark_completed(self, task: Task) -> None:
        """Mark task as completed."""
        if task.id in self.processing:
            del self.processing[task.id]
        self.completed[task.id] = task
    
    def get_status(self) -> Dict[str, int]:
        """Get queue status."""
        return {
            "pending": len(self.queue),
            "processing": len(self.processing),
            "completed": len(self.completed),
        }


class Orchestrator:
    """Main orchestrator for task planning and agent coordination."""
    
    def __init__(self):
        """Initialize orchestrator."""
        self.id = str(uuid.uuid4())
        self.task_queue = TaskQueue()
        self.agent_pool = get_agent_pool()
        self.model_router = get_model_router()
        self.memory_system = get_memory_system()
        self.workflows: Dict[str, Workflow] = {}
        self.running = False
        self.max_concurrent_tasks = 10
        self.active_tasks: Dict[str, asyncio.Task] = {}
    
    async def process_task(self, task: Task) -> Task:
        """
        Process a task from start to finish.
        
        1. Analyze task complexity
        2. Create execution plan (subtasks)
        3. Assign to agents
        4. Execute and validate
        5. Store results in memory
        """
        logger.info(f"Processing task: {task.title}")
        
        # Step 1: Select planner agent
        planner = self.agent_pool.get_agents_by_role(AgentRole.PLANNER)[0]
        task = await planner.handle_task(task)
        
        # Step 2: Process subtasks with appropriate agents
        if task.subtasks:
            subtask_results = await asyncio.gather(
                *[self._process_subtask(st) for st in task.subtasks],
                return_exceptions=True,
            )
            
            # Check for errors
            errors = [r for r in subtask_results if isinstance(r, Exception)]
            if errors:
                task.status = TaskStatus.FAILED
                task.error = f"Subtask execution failed: {errors[0]}"
            else:
                task.status = TaskStatus.COMPLETED
                task.result = {
                    "subtasks_completed": len(task.subtasks),
                    "timestamp": datetime.utcnow().isoformat(),
                }
        
        # Step 3: Validate result
        if task.status == TaskStatus.COMPLETED:
            validator = self.agent_pool.get_agents_by_role(AgentRole.VALIDATOR)[0]
            task = await validator.handle_task(task)
        
        # Step 4: Store in memory
        if task.result:
            self.memory_system.add_memory(
                content=f"Task: {task.title}",
                embedding=[0.5] * 1536,  # Placeholder
                metadata={
                    "task_id": task.id,
                    "result": str(task.result),
                },
                tags=[task.title, task.role if hasattr(task, 'role') else 'task'],
                category="task_result",
            )
        
        self.task_queue.mark_completed(task)
        logger.info(f"Task completed: {task.title} - Status: {task.status.value}")
        
        return task
    
    async def _process_subtask(self, subtask: Task) -> Task:
        """Process a single subtask."""
        logger.info(f"Processing subtask: {subtask.title}")
        
        # Select best agent for subtask
        agent = self.agent_pool.select_agent_for_task(subtask)
        
        if not agent:
            subtask.status = TaskStatus.FAILED
            subtask.error = "No suitable agent available"
            return subtask
        
        # Route to appropriate model if external
        model_score = self.model_router.select_model(subtask)
        logger.info(f"Routed to model: {model_score.model_name}")
        
        # Execute with agent
        return await agent.handle_task(subtask)
    
    async def start_processing_loop(self) -> None:
        """Start the main task processing loop."""
        self.running = True
        logger.info("Orchestrator starting processing loop")
        
        while self.running:
            # Get next task from queue
            task = self.task_queue.dequeue()
            
            if task is None:
                # No tasks, sleep briefly
                await asyncio.sleep(0.5)
                continue
            
            # Check if we're at max concurrent tasks
            if len(self.active_tasks) >= self.max_concurrent_tasks:
                # Re-queue task
                self.task_queue.enqueue(task)
                await asyncio.sleep(0.5)
                continue
            
            # Create processing task
            processing_task = asyncio.create_task(self.process_task(task))
            self.active_tasks[task.id] = processing_task
            
            # Clean up completed tasks
            completed = [tid for tid, t in self.active_tasks.items() if t.done()]
            for tid in completed:
                del self.active_tasks[tid]
    
    def stop_processing(self) -> None:
        """Stop the processing loop."""
        self.running = False
        logger.info("Orchestrator stopping")
    
    def submit_task(self, task: Task) -> None:
        """Submit a task for processing."""
        if not task.id:
            task.id = str(uuid.uuid4())
        self.task_queue.enqueue(task)
    
    def submit_workflow(self, workflow: Workflow) -> None:
        """Submit a workflow for execution."""
        self.workflows[workflow.id] = workflow
        
        # Convert workflow steps to tasks and enqueue
        for step in workflow.steps:
            task = Task(
                id=f"{workflow.id}_{step.id}",
                title=step.name,
                description=step.description,
                context={"workflow_id": workflow.id, "step_id": step.id},
            )
            self.submit_task(task)
        
        logger.info(f"Workflow submitted: {workflow.name}")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        return {
            "queue": self.task_queue.get_status(),
            "active_tasks": len(self.active_tasks),
            "max_concurrent": self.max_concurrent_tasks,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def get_agent_status(self) -> List[Dict[str, Any]]:
        """Get status of all agents."""
        return [agent.get_info() for agent in self.agent_pool.list_agents()]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        return {
            "queue_status": self.task_queue.get_status(),
            "active_agents": len(self.agent_pool.list_agents()),
            "memory_stats": self.memory_system.get_statistics(),
            "active_tasks": len(self.active_tasks),
            "timestamp": datetime.utcnow().isoformat(),
        }


# Global orchestrator instance
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get global orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


async def run_orchestrator() -> None:
    """Run the orchestrator in a background loop."""
    orchestrator = get_orchestrator()
    try:
        await orchestrator.start_processing_loop()
    except KeyboardInterrupt:
        logger.info("Orchestrator interrupted")
    finally:
        orchestrator.stop_processing()
