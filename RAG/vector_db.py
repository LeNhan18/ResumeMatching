import os
import math
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

# =====================================================================
# 1. Embedding Service (Generates Dense and Sparse Representations)
# =====================================================================

class EmbeddingService:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
        self.dimensions = 1536  # Default dimension for text-embedding-3-small
        
        # Check if local sentence transformers can be imported (optional local BGE-M3)
        self.local_model = None
        if os.getenv("USE_LOCAL_EMBEDDING", "false").lower() == "true":
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading local SentenceTransformer model (BGE-M3)...")
                self.local_model = SentenceTransformer('BAAI/bge-m3')
                self.dimensions = 1024  # BGE-M3 dimensions
                logger.info("Local BGE-M3 loaded successfully.")
            except ImportError:
                logger.warning("sentence-transformers not installed. Falling back to API/Mock embedding.")

    def get_dense_embedding(self, text: str) -> List[float]:
        """Generates dense vector representation of text."""
        if not text.strip():
            return [0.0] * self.dimensions
            
        # 1. Try local sentence-transformers model if enabled
        if self.local_model:
            try:
                emb = self.local_model.encode(text, normalize_embeddings=True)
                return emb.tolist()
            except Exception as e:
                logger.error(f"Error generating local embedding: {e}")

        # 2. Try LLM Client API if available
        if self.llm_client and self.llm_client.is_configured():
            try:
                response = self.llm_client.client.embeddings.create(
                    model=self.embedding_model,
                    input=text
                )
                return response.data[0].embedding
            except Exception as e:
                logger.warning(f"Embedding API call failed ({e}). Using mock fallback.")

        # 3. Deterministic Mock Fallback
        return self._generate_mock_embedding(text)

    def _generate_mock_embedding(self, text: str) -> List[float]:
        """Generates unit-normalized mock embedding based on character hashes."""
        vector = []
        text_len = len(text)
        chunk_size = max(1, text_len // self.dimensions)
        
        for i in range(self.dimensions):
            sub = text[i * chunk_size : (i + 1) * chunk_size] or f"pad_{i}"
            h = int(hashlib.md5(sub.encode('utf-8', errors='ignore')).hexdigest(), 16)
            # Center values around 0
            val = float(h % 10000) - 5000.0
            vector.append(val)
            
        # Normalize to unit vector (magnitude = 1.0)
        magnitude = math.sqrt(sum(x * x for x in vector))
        if magnitude == 0:
            return [0.0] * self.dimensions
        return [x / magnitude for x in vector]

    def get_sparse_representation(self, text: str) -> Dict[str, float]:
        """
        Extracts lexical token weights.
        Returns a map of {token: weight} for sparse keyword indexing.
        """
        import re
        # Convert to lower, strip non-alphanumeric, tokenize
        tokens = re.findall(r'\b\w+\b', text.lower())
        if not tokens:
            return {}
            
        # Compute term frequency (TF)
        tf = {}
        for token in tokens:
            if len(token) > 1: # Ignore single characters
                tf[token] = tf.get(token, 0.0) + 1.0
                
        # Simple sublinear scaling for term frequencies
        max_tf = max(tf.values()) if tf else 1.0
        sparse_vec = {token: (0.5 + 0.5 * (val / max_tf)) for token, val in tf.items()}
        return sparse_vec


# =====================================================================
# 2. In-Memory Mock Vector Database (Fallback Mode)
# =====================================================================

class InMemoryVectorStore:
    """A lightweight in-memory alternative simulating Qdrant's payload and dense-sparse search."""
    def __init__(self):
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.vocab_idf: Dict[str, float] = {}

    def upsert(self, doc_id: str, dense_vector: List[float], sparse_vector: Dict[str, float], payload: Dict[str, Any]):
        self.documents[doc_id] = {
            "id": doc_id,
            "dense_vector": dense_vector,
            "sparse_vector": sparse_vector,
            "payload": payload
        }
        self._recalculate_idf()

    def _recalculate_idf(self):
        """Recalculates Inverse Document Frequency for vocabulary terms."""
        num_docs = len(self.documents)
        if num_docs == 0:
            return
            
        doc_counts = {}
        for doc in self.documents.values():
            for token in doc["sparse_vector"].keys():
                doc_counts[token] = doc_counts.get(token, 0) + 1
                
        for token, count in doc_counts.items():
            # Standard IDF formula: ln(1 + (N - n + 0.5) / (n + 0.5)) + 1
            self.vocab_idf[token] = math.log(1.0 + (num_docs - count + 0.5) / (count + 0.5)) + 1.0

    def search(self, dense_query: List[float], sparse_query: Dict[str, float], limit: int = 10, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        results = []
        
        # Calculate dense & sparse scores for all candidates matching metadata filters
        for doc_id, doc in self.documents.items():
            payload = doc["payload"]
            
            # Apply hard metadata matching (filter check)
            if metadata_filter:
                match = True
                for k, v in metadata_filter.items():
                    # Handle lists (e.g. skills filter) or direct equivalence
                    if k in payload:
                        if isinstance(payload[k], list) and isinstance(v, list):
                            if not set(v).intersection(set(payload[k])):
                                match = False
                                break
                        elif payload[k] != v:
                            match = False
                            break
                    else:
                        match = False
                        break
                if not match:
                    continue

            # 1. Compute Dense Cosine Similarity
            dense_score = 0.0
            doc_dense = doc["dense_vector"]
            # Cosine similarity for unit vectors is simply dot product
            if len(dense_query) == len(doc_dense):
                dense_score = sum(q * d for q, d in zip(dense_query, doc_dense))
            # Bound cosine similarity between 0 and 1 for scoring consistency
            dense_score = max(0.0, min(1.0, (dense_score + 1.0) / 2.0))

            # 2. Compute Sparse Dot Product (TF-IDF keyword score)
            sparse_score = 0.0
            doc_sparse = doc["sparse_vector"]
            for token, q_val in sparse_query.items():
                if token in doc_sparse:
                    idf = self.vocab_idf.get(token, 1.0)
                    sparse_score += q_val * doc_sparse[token] * idf
                    
            # Normalize sparse score between 0 and 1 using sigmoid
            sparse_score = 1.0 / (1.0 + math.exp(-sparse_score)) if sparse_score > 0 else 0.0

            results.append({
                "id": doc_id,
                "dense_score": dense_score,
                "sparse_score": sparse_score,
                "payload": payload
            })
            
        # Sort candidates. Let's return raw components; RRF fusion happens in matching.py
        # We sort by dense score initially
        results.sort(key=lambda x: x["dense_score"], reverse=True)
        return results[:limit]


# =====================================================================
# 3. Unified Vector DB Client
# =====================================================================

class VectorDBClient:
    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        self.qdrant_url = os.getenv("QDRANT_URL")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY")
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "cv_matcher")
        
        self.real_client = None
        self.local_store = None
        
        if self.qdrant_url:
            try:
                from qdrant_client import QdrantClient
                self.real_client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
                logger.info(f"Connected to Qdrant cluster at: {self.qdrant_url}")
                self._initialize_collection()
            except ImportError:
                logger.error("qdrant-client not installed. Falling back to In-Memory mode.")
                self.local_store = InMemoryVectorStore()
            except Exception as e:
                logger.error(f"Failed to connect to Qdrant ({e}). Falling back to In-Memory mode.")
                self.local_store = InMemoryVectorStore()
        else:
            logger.info("No QDRANT_URL specified. Initializing In-Memory Vector Store.")
            self.local_store = InMemoryVectorStore()

    def _initialize_collection(self):
        """Configures Qdrant collection for hybrid (dense + sparse) retrieval."""
        from qdrant_client.http import models
        try:
            # Check if collection exists
            collections = self.real_client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                logger.info(f"Creating Qdrant collection: {self.collection_name}")
                self.real_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        # Dense embedding configuration
                        "dense": models.VectorParams(
                            size=self.embedding_service.dimensions,
                            distance=models.Distance.COSINE
                        )
                    },
                    sparse_vectors_config={
                        # Sparse index configuration
                        "sparse": models.SparseVectorParams(
                            index=models.SparseIndexParams(
                                on_disk=True
                            )
                        )
                    }
                )
        except Exception as e:
            logger.error(f"Error initializing Qdrant collection: {e}")

    def upsert_cv(self, cv_id: str, text: str, payload: Dict[str, Any]):
        """Generates embeddings and inserts/updates a CV in the database."""
        dense_vec = self.embedding_service.get_dense_embedding(text)
        sparse_dict = self.embedding_service.get_sparse_representation(text)
        
        # Add source text to payload for retrieval display
        payload["extracted_text"] = text

        if self.real_client:
            from qdrant_client.http import models
            try:
                # Convert sparse dictionary to Qdrant SparseVector format
                # Qdrant client expectations: indices are hashed tokens or token identifiers.
                # In simple hybrid search, we can map tokens to integers or string indices if using custom Qdrant sparse indexing.
                # Standard practice: convert token strings to hashed indices.
                indices = []
                values = []
                for token, weight in sparse_dict.items():
                    # Map word hash into integer range
                    token_hash = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16) % 2147483647
                    indices.append(token_hash)
                    values.append(weight)
                
                self.real_client.upsert(
                    collection_name=self.collection_name,
                    points=[
                        models.PointStruct(
                            id=cv_id,
                            vector={
                                "dense": dense_vec,
                                "sparse": models.SparseVector(indices=indices, values=values)
                            },
                            payload=payload
                        )
                    ]
                )
                logger.info(f"Successfully indexed CV '{cv_id}' in Qdrant.")
            except Exception as e:
                logger.error(f"Qdrant upsert failed: {e}. Attempting in-memory fallback.")
                if not self.local_store:
                    self.local_store = InMemoryVectorStore()
                self.local_store.upsert(cv_id, dense_vec, sparse_dict, payload)
        else:
            self.local_store.upsert(cv_id, dense_vec, sparse_dict, payload)
            logger.info(f"Successfully indexed CV '{cv_id}' in-memory.")

    def search_cv(self, query: str, limit: int = 10, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Queries candidates using hybrid (dense + sparse) search parameters."""
        dense_query = self.embedding_service.get_dense_embedding(query)
        sparse_query = self.embedding_service.get_sparse_representation(query)

        if self.real_client:
            try:
                from qdrant_client.http import models
                
                # Setup metadata filter rules for Qdrant
                qdrant_filter = None
                if metadata_filter:
                    conditions = []
                    for k, v in metadata_filter.items():
                        if isinstance(v, list):
                            conditions.append(models.FieldCondition(key=f"payload.{k}", match=models.MatchAny(any=v)))
                        else:
                            conditions.append(models.FieldCondition(key=f"payload.{k}", match=models.MatchValue(value=v)))
                    qdrant_filter = models.Filter(must=conditions)

                # Format sparse query
                indices = []
                values = []
                for token, weight in sparse_query.items():
                    token_hash = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16) % 2147483647
                    indices.append(token_hash)
                    values.append(weight)
                
                # Fetch dense matches using query_points
                dense_response = self.real_client.query_points(
                    collection_name=self.collection_name,
                    query=dense_query,
                    using="dense",
                    query_filter=qdrant_filter,
                    limit=limit * 2,
                    with_payload=True
                )
                dense_results = dense_response.points
                
                # Fetch sparse matches using query_points
                sparse_response = self.real_client.query_points(
                    collection_name=self.collection_name,
                    query=models.SparseVector(indices=indices, values=values),
                    using="sparse",
                    query_filter=qdrant_filter,
                    limit=limit * 2,
                    with_payload=True
                )
                sparse_results = sparse_response.points

                # Collect and match items to compute individual score matrices
                candidates = {}
                for hit in dense_results:
                    candidates[hit.id] = {
                        "id": hit.id,
                        "dense_score": hit.score,
                        "sparse_score": 0.0,
                        "payload": hit.payload
                    }
                for hit in sparse_results:
                    if hit.id in candidates:
                        candidates[hit.id]["sparse_score"] = hit.score
                    else:
                        candidates[hit.id] = {
                            "id": hit.id,
                            "dense_score": 0.0,
                            "sparse_score": hit.score,
                            "payload": hit.payload
                        }
                        
                return list(candidates.values())[:limit]
            except Exception as e:
                logger.error(f"Qdrant search failed: {e}. Falling back to In-Memory search.")
                if not self.local_store:
                    return []
                return self.local_store.search(dense_query, sparse_query, limit, metadata_filter)
        else:
            return self.local_store.search(dense_query, sparse_query, limit, metadata_filter)

    def get_cv(self, cv_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves CV payload by ID from the database."""
        if self.real_client:
            try:
                res = self.real_client.retrieve(
                    collection_name=self.collection_name,
                    ids=[cv_id],
                    with_payload=True
                )
                if res:
                    return res[0].payload
            except Exception as e:
                logger.error(f"Error retrieving CV '{cv_id}' from Qdrant: {e}")
                
        if self.local_store and cv_id in self.local_store.documents:
            return self.local_store.documents[cv_id]["payload"]
            
        return None

    def list_all_cvs(self) -> List[Dict[str, Any]]:
        """Lists all indexed CV payloads from the database."""
        if self.real_client:
            try:
                res, _ = self.real_client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    with_payload=True,
                    with_vectors=False
                )
                results = []
                for point in res:
                    payload = dict(point.payload or {})
                    payload["id"] = point.id
                    results.append(payload)
                return results
            except Exception as e:
                logger.error(f"Error listing CVs from Qdrant: {e}")
                
        if self.local_store:
            results = []
            for doc in self.local_store.documents.values():
                payload = dict(doc["payload"] or {})
                payload["id"] = doc["id"]
                results.append(payload)
            return results
            
        return []

    def delete_cv(self, cv_id: str) -> bool:
        """Deletes a CV by ID from the database."""
        deleted = False
        if self.real_client:
            try:
                self.real_client.delete(
                    collection_name=self.collection_name,
                    points_selector=[cv_id]
                )
                logger.info(f"Deleted CV '{cv_id}' from Qdrant.")
                deleted = True
            except Exception as e:
                logger.error(f"Error deleting CV '{cv_id}' from Qdrant: {e}")
                
        if self.local_store and cv_id in self.local_store.documents:
            del self.local_store.documents[cv_id]
            self.local_store._recalculate_idf()
            logger.info(f"Deleted CV '{cv_id}' from in-memory store.")
            deleted = True
            
        return deleted
