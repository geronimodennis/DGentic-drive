"""Security and permission management for DGentic."""
import uuid
from typing import Dict, List, Optional, Set
from datetime import datetime
from pydantic import BaseModel
from enum import Enum
from core.types import ActionType, PermissionLevel, Agent
from core.exceptions import SecurityError, AuthorizationError
from loguru import logger


class Permission(BaseModel):
    """Permission definition."""
    id: str
    agent_id: str
    action_type: ActionType
    resource_pattern: str  # glob pattern or regex
    permission_level: PermissionLevel
    created_at: datetime
    expires_at: Optional[datetime] = None


class PermissionEngine:
    """Manages permissions and enforces security policies."""
    
    def __init__(self):
        """Initialize permission engine."""
        self.permissions: Dict[str, List[Permission]] = {}
        self.action_log: List[Dict] = []
    
    def grant_permission(
        self,
        agent_id: str,
        action_type: ActionType,
        resource_pattern: str,
        permission_level: PermissionLevel,
        expires_at: Optional[datetime] = None,
    ) -> Permission:
        """Grant permission to an agent."""
        perm = Permission(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            action_type=action_type,
            resource_pattern=resource_pattern,
            permission_level=permission_level,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        
        if agent_id not in self.permissions:
            self.permissions[agent_id] = []
        
        self.permissions[agent_id].append(perm)
        logger.info(
            f"Permission granted: {agent_id} - {action_type.value} on {resource_pattern}"
        )
        return perm
    
    def revoke_permission(self, permission_id: str) -> bool:
        """Revoke a permission."""
        for perms in self.permissions.values():
            for i, perm in enumerate(perms):
                if perm.id == permission_id:
                    perms.pop(i)
                    logger.info(f"Permission revoked: {permission_id}")
                    return True
        return False
    
    def check_permission(
        self,
        agent_id: str,
        action_type: ActionType,
        resource: str,
    ) -> PermissionLevel:
        """
        Check if agent has permission for action.
        
        Returns:
            PermissionLevel if allowed, raises SecurityError if denied.
        """
        if agent_id not in self.permissions:
            raise AuthorizationError(
                f"Agent {agent_id} has no permissions"
            )
        
        matching_perms = [
            p for p in self.permissions[agent_id]
            if p.action_type == action_type
            and self._matches_pattern(p.resource_pattern, resource)
            and (p.expires_at is None or p.expires_at > datetime.utcnow())
        ]
        
        if not matching_perms:
            raise AuthorizationError(
                f"Agent {agent_id} not authorized for {action_type.value} on {resource}"
            )
        
        # Return highest permission level
        levels = [p.permission_level for p in matching_perms]
        if PermissionLevel.AUTOPILOT in levels:
            return PermissionLevel.AUTOPILOT
        return PermissionLevel.APPROVAL_REQUIRED
    
    def _matches_pattern(self, pattern: str, target: str) -> bool:
        """Check if target matches pattern."""
        import fnmatch
        return fnmatch.fnmatch(target, pattern)
    
    def log_action(
        self,
        agent_id: str,
        action_type: ActionType,
        resource: str,
        status: str,
        details: Optional[Dict] = None,
    ) -> None:
        """Log an action."""
        log_entry = {
            "timestamp": datetime.utcnow(),
            "agent_id": agent_id,
            "action_type": action_type.value,
            "resource": resource,
            "status": status,
            "details": details or {},
        }
        self.action_log.append(log_entry)
        
        log_level = "INFO" if status == "success" else "WARNING"
        logger.log(
            log_level,
            f"Action: {action_type.value} on {resource} - {status}"
        )
    
    def get_audit_log(
        self,
        agent_id: Optional[str] = None,
        action_type: Optional[ActionType] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Get audit log entries."""
        logs = self.action_log
        
        if agent_id:
            logs = [l for l in logs if l["agent_id"] == agent_id]
        
        if action_type:
            logs = [l for l in logs if l["action_type"] == action_type.value]
        
        return logs[-limit:]


class Sandbox:
    """Sandbox for safe code execution."""
    
    def __init__(self, max_memory_mb: int = 512, timeout_seconds: int = 60):
        """Initialize sandbox."""
        self.max_memory_mb = max_memory_mb
        self.timeout_seconds = timeout_seconds
    
    def execute(self, code: str, globals_dict: Optional[Dict] = None) -> Dict:
        """
        Execute code safely in sandbox.
        
        Args:
            code: Python code to execute
            globals_dict: Global variables for execution
            
        Returns:
            Dict with output, errors, and metadata
        """
        import subprocess
        import tempfile
        import json
        
        globals_dict = globals_dict or {}
        
        # Create a wrapper script
        wrapper = f"""
import sys
import json
import io
from contextlib import redirect_stdout, redirect_stderr

globals_dict = {json.dumps(str(globals_dict))}

stdout_capture = io.StringIO()
stderr_capture = io.StringIO()
result = None
error = None

try:
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        exec('''
{code}
''', globals_dict)
    result = stdout_capture.getvalue()
except Exception as e:
    error = str(e)
    import traceback
    error = traceback.format_exc()

output = {{
    "result": result,
    "error": error,
    "stdout": stdout_capture.getvalue(),
    "stderr": stderr_capture.getvalue(),
}}
print(json.dumps(output))
"""
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(wrapper)
                f.flush()
                
                result = subprocess.run(
                    ['python', f.name],
                    timeout=self.timeout_seconds,
                    capture_output=True,
                    text=True,
                )
                
                if result.returncode == 0:
                    try:
                        output = json.loads(result.stdout)
                    except json.JSONDecodeError:
                        output = {
                            "result": result.stdout,
                            "error": None,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                        }
                else:
                    output = {
                        "result": None,
                        "error": result.stderr,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                
                return output
        
        except subprocess.TimeoutExpired:
            raise SecurityError(
                f"Code execution exceeded timeout of {self.timeout_seconds}s"
            )
        except Exception as e:
            raise SecurityError(f"Sandbox execution failed: {str(e)}")


# Global permission engine instance
_permission_engine: Optional[PermissionEngine] = None


def get_permission_engine() -> PermissionEngine:
    """Get global permission engine."""
    global _permission_engine
    if _permission_engine is None:
        _permission_engine = PermissionEngine()
    return _permission_engine
