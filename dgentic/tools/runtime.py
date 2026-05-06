"""Tool runtime for dynamic tool creation and execution."""
import os
import json
import uuid
import shutil
from typing import Dict, Optional, Any, Callable
from datetime import datetime
from pathlib import Path
from core.types import ToolDefinition, PermissionLevel
from core.exceptions import ToolError, SecurityError
from security.permissions import get_permission_engine, Sandbox
from loguru import logger


class ToolRegistry:
    """Registry for managing tools."""
    
    def __init__(self, localmcp_dir: str = "localmcp"):
        """Initialize tool registry."""
        self.localmcp_dir = localmcp_dir
        self.tools: Dict[str, ToolDefinition] = {}
        self.tool_functions: Dict[str, Callable] = {}
        
        # Create localmcp directory if it doesn't exist
        os.makedirs(localmcp_dir, exist_ok=True)
        
        # Load existing tools
        self._load_tools()
    
    def _load_tools(self) -> None:
        """Load tools from localmcp directory."""
        for tool_name in os.listdir(self.localmcp_dir):
            tool_path = os.path.join(self.localmcp_dir, tool_name)
            if os.path.isdir(tool_path):
                metadata_file = os.path.join(tool_path, "metadata.json")
                if os.path.exists(metadata_file):
                    try:
                        with open(metadata_file, 'r') as f:
                            data = json.load(f)
                        tool_def = ToolDefinition(**data)
                        self.tools[tool_name] = tool_def
                        logger.info(f"Loaded tool: {tool_name}")
                    except Exception as e:
                        logger.error(f"Failed to load tool {tool_name}: {e}")
    
    def create_tool(
        self,
        name: str,
        description: str,
        source_code: str,
        permission_level: PermissionLevel = PermissionLevel.APPROVAL_REQUIRED,
        safe: bool = False,
    ) -> ToolDefinition:
        """Create a new tool."""
        if name in self.tools:
            raise ToolError(f"Tool {name} already exists")
        
        tool_id = str(uuid.uuid4())
        tool_dir = os.path.join(self.localmcp_dir, name)
        os.makedirs(tool_dir, exist_ok=True)
        
        # Save source code
        source_path = os.path.join(tool_dir, "tool.py")
        with open(source_path, 'w') as f:
            f.write(source_code)
        
        # Create metadata
        tool_def = ToolDefinition(
            id=tool_id,
            name=name,
            description=description,
            version="1.0.0",
            source_path=source_path,
            metadata_path=os.path.join(tool_dir, "metadata.json"),
            permission_level=permission_level,
            safe=safe,
            reliability_score=0.5,  # Start at 50%
            usage_count=0,
            created_at=datetime.utcnow(),
            deprecated=False,
        )
        
        # Save metadata
        with open(tool_def.metadata_path, 'w') as f:
            json.dump(tool_def.model_dump(default=str), f, indent=2)
        
        self.tools[name] = tool_def
        logger.info(f"Tool created: {name} (safe: {safe}, permission: {permission_level})")
        
        return tool_def
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition."""
        return self.tools.get(name)
    
    def list_tools(self) -> list[ToolDefinition]:
        """List all tools."""
        return list(self.tools.values())
    
    def delete_tool(self, name: str) -> bool:
        """Delete a tool."""
        if name not in self.tools:
            return False
        
        tool_dir = os.path.join(self.localmcp_dir, name)
        shutil.rmtree(tool_dir, ignore_errors=True)
        del self.tools[name]
        if name in self.tool_functions:
            del self.tool_functions[name]
        
        logger.info(f"Tool deleted: {name}")
        return True
    
    def mark_deprecated(self, name: str) -> bool:
        """Mark tool as deprecated."""
        if name not in self.tools:
            return False
        
        tool_def = self.tools[name]
        tool_def.deprecated = True
        
        # Update metadata
        with open(tool_def.metadata_path, 'w') as f:
            json.dump(tool_def.model_dump(default=str), f, indent=2)
        
        logger.warning(f"Tool deprecated: {name}")
        return True


class ToolRuntime:
    """Runtime for executing tools safely."""
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        max_memory_mb: int = 512,
        timeout_seconds: int = 60,
    ):
        """Initialize tool runtime."""
        self.registry = tool_registry
        self.sandbox = Sandbox(max_memory_mb=max_memory_mb, timeout_seconds=timeout_seconds)
        self.execution_log: list[Dict] = []
    
    def execute_tool(
        self,
        agent_id: str,
        tool_name: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute a tool safely.
        
        Args:
            agent_id: ID of the agent executing the tool
            tool_name: Name of the tool to execute
            **kwargs: Tool arguments
            
        Returns:
            Tool execution result
        """
        tool_def = self.registry.get_tool(tool_name)
        if not tool_def:
            raise ToolError(f"Tool not found: {tool_name}")
        
        if tool_def.deprecated:
            raise ToolError(f"Tool is deprecated: {tool_name}")
        
        try:
            # Load tool source
            with open(tool_def.source_path, 'r') as f:
                source_code = f.read()
            
            # Execute in sandbox
            result = self.sandbox.execute(source_code, kwargs)
            
            # Log execution
            self._log_execution(
                agent_id=agent_id,
                tool_name=tool_name,
                status="success",
                result=result,
            )
            
            # Update tool statistics
            tool_def.usage_count += 1
            tool_def.reliability_score = min(
                tool_def.reliability_score + 0.01,
                1.0
            )
            
            return result
        
        except Exception as e:
            self._log_execution(
                agent_id=agent_id,
                tool_name=tool_name,
                status="failed",
                error=str(e),
            )
            raise ToolError(f"Tool execution failed: {str(e)}")
    
    def _log_execution(
        self,
        agent_id: str,
        tool_name: str,
        status: str,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log tool execution."""
        log_entry = {
            "timestamp": datetime.utcnow(),
            "agent_id": agent_id,
            "tool_name": tool_name,
            "status": status,
            "result": result,
            "error": error,
        }
        self.execution_log.append(log_entry)
        
        level = "INFO" if status == "success" else "ERROR"
        logger.log(level, f"Tool execution ({tool_name}): {status}")
    
    def get_execution_log(self, tool_name: Optional[str] = None) -> list[Dict]:
        """Get execution log."""
        if tool_name:
            return [
                log for log in self.execution_log
                if log["tool_name"] == tool_name
            ]
        return self.execution_log


# Global instances
_tool_registry: Optional[ToolRegistry] = None
_tool_runtime: Optional[ToolRuntime] = None


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


def get_tool_runtime() -> ToolRuntime:
    """Get global tool runtime."""
    global _tool_runtime
    if _tool_runtime is None:
        registry = get_tool_registry()
        _tool_runtime = ToolRuntime(registry)
    return _tool_runtime
