"""Model router for hybrid workload orchestration."""
from typing import Optional, Dict, List, Any
from enum import Enum
from pydantic import BaseModel
from core.types import ModelType, Task
from core.exceptions import ModelError
from loguru import logger


class ModelScore(BaseModel):
    """Score for model routing decision."""
    model_type: ModelType
    model_name: str
    score: float
    reasoning: Dict[str, float]  # Components of the score
    recommended: bool = False


class ModelRouter:
    """Intelligently routes tasks to local or external models."""
    
    def __init__(
        self,
        cost_weight: float = 0.25,
        latency_weight: float = 0.25,
        reliability_weight: float = 0.25,
        capability_weight: float = 0.25,
    ):
        """Initialize model router."""
        self.cost_weight = cost_weight
        self.latency_weight = latency_weight
        self.reliability_weight = reliability_weight
        self.capability_weight = capability_weight
        
        # Model characteristics
        self.models: Dict[str, Dict[str, Any]] = {
            # Local models
            "llama2_7b": {
                "type": ModelType.LOCAL,
                "cost": 0,  # Free, just compute
                "latency": 2.0,  # seconds
                "reliability": 0.95,
                "capabilities": ["reasoning", "writing", "analysis"],
                "max_tokens": 2048,
            },
            "mistral_7b": {
                "type": ModelType.LOCAL,
                "cost": 0,
                "latency": 2.5,
                "reliability": 0.93,
                "capabilities": ["reasoning", "code", "writing"],
                "max_tokens": 4096,
            },
            # External models
            "gpt-4": {
                "type": ModelType.OPENAI,
                "cost": 0.03,  # per 1K tokens
                "latency": 3.0,
                "reliability": 0.99,
                "capabilities": ["reasoning", "code", "analysis", "research"],
                "max_tokens": 8192,
            },
            "gpt-3.5-turbo": {
                "type": ModelType.OPENAI,
                "cost": 0.0015,
                "latency": 1.0,
                "reliability": 0.98,
                "capabilities": ["reasoning", "code", "writing"],
                "max_tokens": 4096,
            },
            "gemini-pro": {
                "type": ModelType.GOOGLE,
                "cost": 0.005,
                "latency": 2.0,
                "reliability": 0.97,
                "capabilities": ["reasoning", "analysis", "multimodal"],
                "max_tokens": 32768,
            },
            "deepseek-coder": {
                "type": ModelType.DEEPSEEK,
                "cost": 0.001,
                "latency": 1.5,
                "reliability": 0.96,
                "capabilities": ["code", "reasoning"],
                "max_tokens": 4096,
            },
        }
    
    def score_models(self, task: Task) -> List[ModelScore]:
        """Score all available models for a task."""
        scores = []
        
        # Determine task complexity
        complexity = self._analyze_task_complexity(task)
        
        for model_name, model_info in self.models.items():
            score = self._score_model(model_name, model_info, task, complexity)
            scores.append(score)
        
        # Sort by score (descending)
        scores.sort(key=lambda x: x.score, reverse=True)
        
        # Mark top choice as recommended
        if scores:
            scores[0].recommended = True
        
        return scores
    
    def select_model(self, task: Task) -> ModelScore:
        """Select best model for task."""
        scores = self.score_models(task)
        if not scores:
            raise ModelError("No models available for task")
        
        best = scores[0]
        logger.info(
            f"Selected model: {best.model_name} "
            f"(score: {best.score:.3f}) for task: {task.title}"
        )
        
        return best
    
    def _analyze_task_complexity(self, task: Task) -> Dict[str, float]:
        """Analyze task complexity factors."""
        description_length = len(task.description)
        num_constraints = len(task.constraints)
        num_subtasks = len(task.subtasks)
        
        return {
            "description_complexity": min(description_length / 1000, 1.0),
            "constraint_complexity": min(num_constraints / 10, 1.0),
            "subtask_complexity": min(num_subtasks / 5, 1.0),
        }
    
    def _score_model(
        self,
        model_name: str,
        model_info: Dict[str, Any],
        task: Task,
        complexity: Dict[str, float],
    ) -> ModelScore:
        """Score a specific model for a task."""
        
        # Capability match (0-1)
        task_keywords = set(task.description.lower().split())
        model_capabilities = set(model_info.get("capabilities", []))
        capability_match = len(
            task_keywords & model_capabilities
        ) / max(len(task_keywords), 1)
        capability_score = capability_match * self.capability_weight
        
        # Cost score (lower is better, 0-1)
        cost_normalized = min(model_info["cost"] / 0.1, 1.0)  # Normalize
        cost_score = (1 - cost_normalized) * self.cost_weight
        
        # Latency score (lower is better, 0-1)
        latency_normalized = min(model_info["latency"] / 5.0, 1.0)  # Normalize
        latency_score = (1 - latency_normalized) * self.latency_weight
        
        # Reliability score
        reliability_score = model_info["reliability"] * self.reliability_weight
        
        # Total score
        total_score = (
            capability_score + cost_score + latency_score + reliability_score
        )
        
        return ModelScore(
            model_type=model_info["type"],
            model_name=model_name,
            score=total_score,
            reasoning={
                "capability": capability_score,
                "cost": cost_score,
                "latency": latency_score,
                "reliability": reliability_score,
            },
        )
    
    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a model."""
        return self.models.get(model_name)
    
    def add_model(
        self,
        name: str,
        model_type: ModelType,
        cost: float,
        latency: float,
        reliability: float,
        capabilities: List[str],
        max_tokens: int,
    ) -> None:
        """Add a custom model to the router."""
        self.models[name] = {
            "type": model_type,
            "cost": cost,
            "latency": latency,
            "reliability": reliability,
            "capabilities": capabilities,
            "max_tokens": max_tokens,
        }
        logger.info(f"Added model: {name} ({model_type.value})")


# Global model router instance
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get global model router."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router
