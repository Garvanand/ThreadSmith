"""
ThreadSmith Clustering Node
Connects to ChromaDB to group extracted intents into Issue Clusters.
"""
import uuid
from typing import List, Dict
from loguru import logger
from database.models import db_clusters, IssueCluster
from datetime import datetime, timezone

# --- Mock Infrastructure ---
class MockEmbeddingModel:
    def encode(self, text: str) -> List[float]:
        # Simple mock: return vectors based on keywords
        if "payment" in text or "card" in text:
            return [0.9, 0.1, 0.0]
        elif "password" in text:
            return [0.1, 0.9, 0.0]
        return [0.0, 0.0, 0.9]

class MockChromaDB:
    def __init__(self):
        self.records = []
    
    def query(self, query_embeddings: List[List[float]], n_results: int = 1):
        if not self.records:
            return {"ids": [[]], "distances": [[]]}
        
        # Extremely simplified mock distance search
        q_emb = query_embeddings[0]
        best_dist = 999.0
        best_id = None
        for rec in self.records:
            dist = sum((a - b)**2 for a, b in zip(q_emb, rec['emb']))
            if dist < best_dist:
                best_dist = dist
                best_id = rec['id']
                
        if best_id and best_dist < 0.2: # Threshold for a match
            return {"ids": [[best_id]], "distances": [[best_dist]]}
        return {"ids": [[]], "distances": [[]]}
        
    def add(self, ids: List[str], embeddings: List[List[float]], metadatas: List[Dict]):
        for i in range(len(ids)):
            self.records.append({'id': ids[i], 'emb': embeddings[i], 'meta': metadatas[i]})

chroma_collection = MockChromaDB()
embed_model = MockEmbeddingModel()

def cluster_issue(structural_intent: dict, raw_text: str) -> str:
    """
    Takes the structured intent and attempts to merge it into an existing cluster via ChromaDB.
    If no match exceeds the threshold, creates a new cluster.
    Returns the cluster_id.
    """
    core_issue = structural_intent["core_issue"]
    logger.info(f"Clustering core issue: {core_issue}")
    
    # Generate embedding for the structural intent
    emb = embed_model.encode(core_issue)
    
    # Query ChromaDB 'threadsmith_issues'
    results = chroma_collection.query(query_embeddings=[emb], n_results=1)
    
    if results["ids"] and results["ids"][0]:
        matched_cluster_id = results["ids"][0][0]
        logger.info(f"Matched existing cluster: {matched_cluster_id}")
        
        # Update PG DB ticket count
        if matched_cluster_id in db_clusters:
            db_clusters[matched_cluster_id].ticket_count += 1
            
        return matched_cluster_id
        
    # No match -> Create New Cluster
    new_cluster_id = f"cluster_{uuid.uuid4().hex[:8]}"
    logger.info(f"No match found. Creating new cluster: {new_cluster_id}")
    
    chroma_collection.add(
        ids=[new_cluster_id],
        embeddings=[emb],
        metadatas=[{"core_issue": core_issue, "category": structural_intent["category"]}]
    )
    
    # Save to PG
    db_clusters[new_cluster_id] = IssueCluster(
        cluster_id=new_cluster_id,
        representative_description=core_issue,
        embedding_chroma_ref=new_cluster_id,
        first_seen_at=datetime.now(timezone.utc)
    )
    
    return new_cluster_id

if __name__ == "__main__":
    c1 = cluster_issue({"core_issue": "payment_failure_decline", "category": "Billing"}, "Card declined")
    c2 = cluster_issue({"core_issue": "payment_failure_decline", "category": "Billing"}, "Payment failed again")
    c3 = cluster_issue({"core_issue": "password_reset_request", "category": "Account"}, "Forgot password")
    
    print(f"Cluster 1: {c1}")
    print(f"Cluster 2: {c2}") # Should be identical to c1
    print(f"Cluster 3: {c3}") # Should be different
