"""External AI service integrations."""
import os
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
import asyncio
import httpx
from core.exceptions import IntegrationError
from loguru import logger


class AIServiceBase(ABC):
    """Base class for AI service integrations."""
    
    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate response from prompt."""
        pass
    
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Generate embeddings for text."""
        pass


class OpenAIIntegration(AIServiceBase):
    """OpenAI API integration."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize OpenAI integration."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise IntegrationError("OPENAI_API_KEY not set")
        
        self.base_url = "https://api.openai.com/v1"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
    
    async def generate(
        self,
        prompt: str,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> str:
        """Generate response using OpenAI."""
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise IntegrationError(f"OpenAI generation failed: {e}")
    
    async def embed(self, text: str, model: str = "text-embedding-3-small") -> List[float]:
        """Generate embeddings using OpenAI."""
        try:
            response = await self.client.post(
                f"{self.base_url}/embeddings",
                json={"model": model, "input": text},
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            raise IntegrationError(f"OpenAI embedding failed: {e}")


class GoogleAIIntegration(AIServiceBase):
    """Google AI (Gemini) integration."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Google AI integration."""
        self.api_key = api_key or os.getenv("GOOGLE_AI_API_KEY")
        if not self.api_key:
            raise IntegrationError("GOOGLE_AI_API_KEY not set")
        
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.client = httpx.AsyncClient()
    
    async def generate(
        self,
        prompt: str,
        model: str = "gemini-pro",
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Generate response using Google AI."""
        try:
            response = await self.client.post(
                f"{self.base_url}/{model}:generateContent",
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature, **kwargs},
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"Google AI generation failed: {e}")
            raise IntegrationError(f"Google AI generation failed: {e}")
    
    async def embed(self, text: str, model: str = "embedding-001") -> List[float]:
        """Generate embeddings using Google AI."""
        try:
            response = await self.client.post(
                f"{self.base_url}/{model}:embedContent",
                params={"key": self.api_key},
                json={"text": text},
            )
            response.raise_for_status()
            data = response.json()
            return data["embedding"]["values"]
        except Exception as e:
            logger.error(f"Google AI embedding failed: {e}")
            raise IntegrationError(f"Google AI embedding failed: {e}")


class DeepSeekIntegration(AIServiceBase):
    """DeepSeek API integration."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize DeepSeek integration."""
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise IntegrationError("DEEPSEEK_API_KEY not set")
        
        self.base_url = "https://api.deepseek.com/v1"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
    
    async def generate(
        self,
        prompt: str,
        model: str = "deepseek-coder",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Generate response using DeepSeek."""
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"DeepSeek generation failed: {e}")
            raise IntegrationError(f"DeepSeek generation failed: {e}")
    
    async def embed(self, text: str) -> List[float]:
        """Generate embeddings using DeepSeek."""
        try:
            response = await self.client.post(
                f"{self.base_url}/embeddings",
                json={"model": "deepseek-embed", "input": text},
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"DeepSeek embedding failed: {e}")
            raise IntegrationError(f"DeepSeek embedding failed: {e}")


class WebSearch:
    """Web search and scraping utilities."""
    
    def __init__(self):
        """Initialize web search."""
        self.client = httpx.AsyncClient()
    
    async def search(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """Search the web (requires search API)."""
        # Placeholder - would use actual search API
        logger.info(f"Web search: {query}")
        return [
            {
                "title": f"Result {i+1}",
                "url": f"https://example.com/{i}",
                "snippet": f"Search result for: {query}",
            }
            for i in range(min(limit, 3))
        ]
    
    async def scrape(self, url: str) -> Dict[str, str]:
        """Scrape webpage content."""
        try:
            response = await self.client.get(url, timeout=10)
            response.raise_for_status()
            
            # Simple HTML extraction (would use BeautifulSoup in production)
            return {
                "url": url,
                "status_code": response.status_code,
                "content_length": len(response.text),
                "content": response.text[:1000],  # First 1000 chars
            }
        except Exception as e:
            logger.error(f"Web scraping failed: {e}")
            return {"error": str(e)}


class IntegrationManager:
    """Manage all external integrations."""
    
    def __init__(self):
        """Initialize integration manager."""
        self.integrations: Dict[str, AIServiceBase] = {}
        self.web_search = WebSearch()
        
        # Initialize available services
        try:
            self.integrations["openai"] = OpenAIIntegration()
        except IntegrationError:
            logger.warning("OpenAI integration not available")
        
        try:
            self.integrations["google"] = GoogleAIIntegration()
        except IntegrationError:
            logger.warning("Google AI integration not available")
        
        try:
            self.integrations["deepseek"] = DeepSeekIntegration()
        except IntegrationError:
            logger.warning("DeepSeek integration not available")
    
    async def generate(
        self,
        service: str,
        prompt: str,
        **kwargs: Any,
    ) -> str:
        """Generate response from service."""
        if service not in self.integrations:
            raise IntegrationError(f"Service not available: {service}")
        
        return await self.integrations[service].generate(prompt, **kwargs)
    
    async def embed(self, service: str, text: str) -> List[float]:
        """Generate embeddings from service."""
        if service not in self.integrations:
            raise IntegrationError(f"Service not available: {service}")
        
        return await self.integrations[service].embed(text)
    
    def list_services(self) -> List[str]:
        """List available services."""
        return list(self.integrations.keys())


# Global integration manager instance
_integration_manager: Optional[IntegrationManager] = None


def get_integration_manager() -> IntegrationManager:
    """Get global integration manager."""
    global _integration_manager
    if _integration_manager is None:
        _integration_manager = IntegrationManager()
    return _integration_manager
