"""Exceptions for DGentic."""


class DGenticException(Exception):
    """Base exception for DGentic."""
    pass


class ConfigurationError(DGenticException):
    """Configuration error."""
    pass


class AuthenticationError(DGenticException):
    """Authentication error."""
    pass


class AuthorizationError(DGenticException):
    """Authorization/permission error."""
    pass


class ModelError(DGenticException):
    """Model loading or execution error."""
    pass


class AgentError(DGenticException):
    """Agent execution error."""
    pass


class TaskError(DGenticException):
    """Task execution error."""
    pass


class MemoryError(DGenticException):
    """Memory system error."""
    pass


class ToolError(DGenticException):
    """Tool execution error."""
    pass


class SecurityError(DGenticException):
    """Security policy violation."""
    pass


class IntegrationError(DGenticException):
    """External integration error."""
    pass


class ValidationError(DGenticException):
    """Validation error."""
    pass
