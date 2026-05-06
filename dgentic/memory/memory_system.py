"""Memory system with vector database and indexing."""
import uuid
import os
import json
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import numpy as np
from core.types import Memory
from core.exceptions import MemoryError
from loguru import logger


class MemoryIndex:
    """Metadata index for fast lookup and filtering."""
    
    def __init__(self):
        """Initialize memory index."""
        self.index: Dict[str, Memory] = {}
        self.tag_index: Dict[str, List[str]] = {}  # tag -> memory_ids
        self.category_index: Dict[str, List[str]] = {}  # category -> memory_ids
    
    def add(self, memory: Memory) -> None:
        """Add memory to index."""
        self.index[memory.id] = memory
        
        # Index by tags
        for tag in memory.tags:
            if tag not in self.tag_index:
                self.tag_index[tag] = []
            self.tag_index[tag].append(memory.id)
        
        # Index by category
        if memory.category not in self.category_index:
            self.category_index[memory.category] = []
        self.category_index[memory.category].append(memory.id)
    
    def search_by_tag(self, tag: str) -> List[Memory]:
        """Search memories by tag. O(1) lookup."""
        memory_ids = self.tag_index.get(tag, [])
        return [self.index[mid] for mid in memory_ids if mid in self.index]
    
    def search_by_category(self, category: str) -> List[Memory]:
        """Search memories by category. O(1) lookup."""
        memory_ids = self.category_index.get(category, [])
        return [self.index[mid] for mid in memory_ids if mid in self.index]
    
    def get(self, memory_id: str) -> Optional[Memory]:
        """Get memory by ID. O(1) lookup."""
        return self.index.get(memory_id)
    
    def delete(self, memory_id: str) -> bool:
        """Delete memory from index."""
        if memory_id not in self.index:
            return False
        
        memory = self.index[memory_id]
        
        # Remove from tag index
        for tag in memory.tags:
            if tag in self.tag_index:
                self.tag_index[tag] = [
                    mid for mid in self.tag_index[tag] if mid != memory_id
                ]
        
        # Remove from category index
        if memory.category in self.category_index:
            self.category_index[memory.category] = [
                mid for mid in self.category_index[memory.category]
                if mid != memory_id
            ]
        
        del self.index[memory_id]
        return True


class VectorMemory:
    """Vector database for semantic search (FAISS)."""
    
    def __init__(
        self,
        dimension: int = 1536,
        index_path: str = "faiss_index.idx",
    ):
        """Initialize vector memory."""
        try:
            import faiss
        except ImportError:
            raise MemoryError("FAISS not installed. Install with: pip install faiss-cpu")
        
        self.dimension = dimension
        self.index_path = index_path
        self.faiss = faiss
        self.embeddings: Dict[str, np.ndarray] = {}
        self.id_map: Dict[int, str] = {}  # faiss index -> memory id
        self.next_id = 0
        
        # Create or load index
        if os.path.exists(index_path):
            self.index = faiss.read_index(index_path)
        else:
            self.index = faiss.IndexFlatL2(dimension)
    
    def add(self, memory_id: str, embedding: List[float]) -> None:
        """Add embedding to vector index."""
        embedding = np.array([embedding], dtype=np.float32)
        self.index.add(embedding)
        self.id_map[self.next_id] = memory_id
        self.next_id += 1
    
    def search(
        self,
        query_embedding: List[float],
        k: int = 10,
    ) -> List[Tuple[str, float]]:
        """
        Search for similar embeddings.
        
        Returns:
            List of (memory_id, distance) tuples. O(log n) with FAISS indexing.
        """
        query = np.array([query_embedding], dtype=np.float32)
        distances, indices = self.index.search(query, min(k, self.index.ntotal))
        
        results = []
        for idx, distance in zip(indices[0], distances):
            if idx in self.id_map:
                results.append((self.id_map[idx], float(distance)))
        
        return results
    
    def save(self) -> None:
        """Persist index to disk."""
        self.faiss.write_index(self.index, self.index_path)
        logger.info(f"Vector index saved to {self.index_path}")


class MemorySystem:
    """Complete memory system with vector search and metadata indexing."""
    
    def __init__(
        self,
        vector_dimension: int = 1536,
        vector_index_path: str = "faiss_index.idx",
    ):
        """Initialize memory system."""
        self.metadata_index = MemoryIndex()
        self.vector_db = VectorMemory(
            dimension=vector_dimension,
            index_path=vector_index_path,
        )
        self.memories: Dict[str, Memory] = {}
    
    def add_memory(
        self,
        content: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        category: str = "general",
    ) -> Memory:
        """Add a memory entry."""
        memory = Memory(
            id=str(uuid.uuid4()),
            content=content,
            embedding=embedding,
            metadata=metadata or {},
            tags=tags or [],
            category=category,
        )
        
        self.memories[memory.id] = memory
        self.metadata_index.add(memory)
        self.vector_db.add(memory.id, embedding)
        
        logger.info(f"Memory added: {memory.id[:8]}... ({category})")
        return memory
    
    def semantic_search(
        self,
        query_embedding: List[float],
        k: int = 10,
        category: Optional[str] = None,
    ) -> List[Memory]:
        """
        Search memories semantically.
        
        Returns:
            List of Memory objects, ranked by similarity.
        """
        results = self.vector_db.search(query_embedding, k=k*2)  # Get extra for filtering
        
        memories = []
        for memory_id, distance in results:
            if memory_id in self.memories:
                memory = self.memories[memory_id]
                if category is None or memory.category == category:
                    memories.append(memory)
                    if len(memories) >= k:
                        break
        
        return memories
    
    def search_by_tag(self, tag: str) -> List[Memory]:
        """Search memories by tag. O(1) lookup."""
        return self.metadata_index.search_by_tag(tag)
    
    def search_by_category(self, category: str) -> List[Memory]:
        """Search memories by category. O(1) lookup."""
        return self.metadata_index.search_by_category(category)
    
    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Get memory by ID. O(1) lookup."""
        memory = self.metadata_index.get(memory_id)
        if memory:
            memory.accessed_at = datetime.utcnow()
            memory.usage_count += 1
        return memory
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        if self.metadata_index.delete(memory_id):
            if memory_id in self.memories:
                del self.memories[memory_id]
            logger.info(f"Memory deleted: {memory_id}")
            return True
        return False
    
    def compress_memory(self) -> Dict[str, Any]:
        """Compress memory for storage optimization."""
        # Remove low-relevance entries
        to_delete = [
            mid for mid, mem in self.memories.items()
            if mem.relevance_score < 0.1 and mem.usage_count < 2
        ]
        
        for mid in to_delete:
            self.delete_memory(mid)
        
        return {
            "entries_removed": len(to_delete),
            "remaining_memories": len(self.memories),
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def save(self) -> None:
        """Persist memory system to disk."""
        self.vector_db.save()
        
        # Save metadata
        metadata_path = "memory_metadata.json"
        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "memory_count": len(self.memories),
            "memories": [m.model_dump() for m in self.memories.values()],
        }
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, default=str)
        
        logger.info(f"Memory system persisted (count: {len(self.memories)})")
    
    def load_from_disk(self, metadata_path: str = "memory_metadata.json") -> None:
        """Load memory system from disk."""
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                data = json.load(f)
                for mem_data in data.get("memories", []):
                    memory = Memory(**mem_data)
                    self.memories[memory.id] = memory
                    self.metadata_index.add(memory)
            
            logger.info(f"Loaded {len(self.memories)} memories from disk")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        return {
            "total_memories": len(self.memories),
            "categories": len(self.metadata_index.category_index),
            "tags": len(self.metadata_index.tag_index),
            "avg_relevance": np.mean([m.relevance_score for m in self.memories.values()]),
            "total_accesses": sum(m.usage_count for m in self.memories.values()),
        }


# Global memory system instance
_memory_system: Optional[MemorySystem] = None


def get_memory_system() -> MemorySystem:
    """Get global memory system."""
    global _memory_system
    if _memory_system is None:
        _memory_system = MemorySystem()
    return _memory_system
