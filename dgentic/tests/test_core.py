"""Basic tests for DGentic."""
import pytest
import asyncio
from core.types import Task, AgentRole, ModelType, PermissionLevel, ActionType
from core.orchestrator import Orchestrator
from agents.agent import PlannerAgent, CoderAgent, ResearcherAgent, ValidatorAgent
from memory.memory_system import MemorySystem
from models.router import ModelRouter
from security.permissions import PermissionEngine
from tools.runtime import ToolRegistry


class TestOrchestrator:
    """Test orchestrator functionality."""
    
    def test_orchestrator_initialization(self):
        """Test orchestrator initialization."""
        orch = Orchestrator()
        assert orch.id is not None
        assert orch.task_queue is not None
        assert len(orch.agent_pool.list_agents()) > 0
    
    def test_task_queue(self):
        """Test task queue operations."""
        orch = Orchestrator()
        
        task = Task(
            id="test_task",
            title="Test Task",
            description="A test task",
        )
        
        orch.task_queue.enqueue(task)
        assert orch.task_queue.get_status()["pending"] == 1
        
        dequeued = orch.task_queue.dequeue()
        assert dequeued.id == task.id
        assert orch.task_queue.get_status()["processing"] == 1


class TestAgents:
    """Test agent functionality."""
    
    @pytest.mark.asyncio
    async def test_planner_agent(self):
        """Test planner agent."""
        agent = PlannerAgent()
        
        task = Task(
            id="plan_task",
            title="Plan Complex Task",
            description="Create a plan for this",
            constraints=["constraint1", "constraint2"],
        )
        
        result = await agent.execute_task(task)
        
        assert result.status.value == "completed"
        assert len(result.subtasks) > 0
    
    @pytest.mark.asyncio
    async def test_coder_agent(self):
        """Test coder agent."""
        agent = CoderAgent()
        
        task = Task(
            id="code_task",
            title="Write Python Function",
            description="Create a function to parse JSON",
        )
        
        result = await agent.execute_task(task)
        
        assert result.status.value == "completed"
        assert result.result is not None
        assert "code" in result.result


class TestMemory:
    """Test memory system."""
    
    def test_memory_add_and_retrieve(self):
        """Test adding and retrieving memories."""
        memory = MemorySystem()
        
        mem = memory.add_memory(
            content="Test memory content",
            embedding=[0.5] * 1536,
            tags=["test", "example"],
            category="test",
        )
        
        assert mem.id is not None
        retrieved = memory.get_memory(mem.id)
        assert retrieved is not None
        assert retrieved.content == "Test memory content"
    
    def test_memory_search_by_tag(self):
        """Test tag-based search."""
        memory = MemorySystem()
        
        memory.add_memory(
            content="First memory",
            embedding=[0.1] * 1536,
            tags=["important"],
            category="notes",
        )
        
        memory.add_memory(
            content="Second memory",
            embedding=[0.2] * 1536,
            tags=["important"],
            category="notes",
        )
        
        results = memory.search_by_tag("important")
        assert len(results) == 2


class TestModelRouter:
    """Test model router."""
    
    def test_model_selection(self):
        """Test model selection."""
        router = ModelRouter()
        
        task = Task(
            id="router_test",
            title="Code Generation Task",
            description="Write Python code for data processing",
        )
        
        selected = router.select_model(task)
        assert selected is not None
        assert selected.model_type in [ModelType.LOCAL, ModelType.OPENAI]
    
    def test_model_scoring(self):
        """Test model scoring."""
        router = ModelRouter()
        
        task = Task(
            id="score_test",
            title="Simple Task",
            description="Do something",
        )
        
        scores = router.score_models(task)
        assert len(scores) > 0
        assert scores[0].recommended == True


class TestSecurity:
    """Test security functionality."""
    
    def test_permission_grant_and_check(self):
        """Test permission granting and checking."""
        engine = PermissionEngine()
        
        # Grant permission
        engine.grant_permission(
            agent_id="test_agent",
            action_type=ActionType.FILE_READ,
            resource_pattern="*.txt",
            permission_level=PermissionLevel.AUTOPILOT,
        )
        
        # Check permission
        level = engine.check_permission(
            agent_id="test_agent",
            action_type=ActionType.FILE_READ,
            resource="test.txt",
        )
        
        assert level == PermissionLevel.AUTOPILOT
    
    def test_action_logging(self):
        """Test action logging."""
        engine = PermissionEngine()
        
        engine.log_action(
            agent_id="test_agent",
            action_type=ActionType.CLI_EXECUTE,
            resource="echo test",
            status="success",
        )
        
        logs = engine.get_audit_log(agent_id="test_agent")
        assert len(logs) == 1
        assert logs[0]["status"] == "success"


class TestTools:
    """Test tool functionality."""
    
    def test_tool_creation(self):
        """Test tool creation."""
        registry = ToolRegistry()
        
        tool = registry.create_tool(
            name="test_tool",
            description="A test tool",
            source_code="def main(): return 'test'",
        )
        
        assert tool.name == "test_tool"
        assert tool.id is not None
    
    def test_tool_retrieval(self):
        """Test tool retrieval."""
        registry = ToolRegistry()
        
        tool = registry.create_tool(
            name="retrieve_test",
            description="Test retrieval",
            source_code="pass",
        )
        
        retrieved = registry.get_tool("retrieve_test")
        assert retrieved is not None
        assert retrieved.name == "retrieve_test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
