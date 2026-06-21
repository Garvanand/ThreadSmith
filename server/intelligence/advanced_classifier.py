"""
ThreadSmith Advanced Structural Classification & Clustering Node.
Handles context-aware intent extraction, three-zone clustering, and cluster splitting.
"""
import os
import json
import uuid
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel
from anthropic import Anthropic
from loguru import logger
import sys
import os

# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.agentos_client import build_customer_context

API_KEY = os.getenv("OPENROUTER_API_KEY", "mock-key")

# --- DATA MODELS ---

class IssueStructure(BaseModel):
    normalized_problem_statement: str
    affected_entities: dict
    severity_signal: Literal["low", "medium", "high", "critical"]
    prior_resolution_attempts: List[str]

class ClusterMatchResult(BaseModel):
    cluster_id: str
    match_type: Literal["auto_merge", "disambiguated_merge", "new_cluster"]

class IssueCluster(BaseModel):
    cluster_id: str
    representative_description: str
    embedding: List[float] # Mock representation
    ticket_count: int
    resolution_verification_rate: float # Used for cluster cohesion analysis

class CohesionReport(BaseModel):
    is_contaminated: bool
    proposed_split_clusters: List[dict] # {new_cluster_id: str, new_description: str, reassigned_tickets: list}
    reasoning: str

# Removed mock get_customer_context

# --- PART A & D: STRUCTURAL EXTRACTION & CONTEXT AWARENESS ---

def extract_issue_structure(raw_ticket_text: str, customer_context: Optional[dict] = None) -> IssueStructure:
    """
    Strips away customer emotion and surface syntax to identify the true structural issue.
    Integrates AgentOS GhostCFO/ForgeSign context to influence classification.
    """
    logger.info(f"Extracting structure. Context available: {bool(customer_context)}")
    
    prompt = f"""
    You are the ThreadSmith structural classification engine.
    Analyze the following customer support ticket and extract the true underlying issue.
    Ignore emotional language.
    
    If Customer Context is provided, use it to accurately diagnose the root cause.
    For example, a "payment failed" ticket with context showing "ARREARS" is a different 
    structural issue than a payment failure for a healthy account (which implies a processing glitch).
    
    Ticket Text: "{raw_ticket_text}"
    Customer Context: {customer_context or "None"}
    
    Output JSON strictly matching this schema:
    {{
        "normalized_problem_statement": "Concise root cause description",
        "affected_entities": {{"feature": "...", "method": "..."}},
        "severity_signal": "low|medium|high|critical",
        "prior_resolution_attempts": ["List any explicit mentions of things the user already tried, or empty list"]
    }}
    """
    
    if "mock" in API_KEY.lower():
        # Synthetic handling
        if "arrears" in str(customer_context).lower():
            return IssueStructure(
                normalized_problem_statement="payment_failure_due_to_account_arrears",
                affected_entities={"method": "card"},
                severity_signal="medium",
                prior_resolution_attempts=[]
            )
        else:
            return IssueStructure(
                normalized_problem_statement="transient_payment_processor_glitch",
                affected_entities={"method": "card"},
                severity_signal="medium",
                prior_resolution_attempts=["I tried re-entering my card details"]
            )
            
    client = Anthropic(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")
    response = client.messages.create(
        model="anthropic/claude-3-opus",
        max_tokens=300,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}]
    )
    data = json.loads(response.content[0].text)
    return IssueStructure(**data)

# --- PART B: THREE-ZONE CLUSTERING ---

def disambiguate_root_cause(new_issue: IssueStructure, existing_cluster: IssueCluster) -> bool:
    """
    Claude-3-Opus disambiguation layer for the 'Ambiguous Zone'.
    Focuses specifically on Root Cause vs Surface Symptom.
    """
    prompt = f"""
    Determine if these two support issues share the SAME ROOT CAUSE.
    This is critical: support tickets often share surface symptoms but require completely different resolutions.
    For example: "Login fails" could be a forgotten password, OR a disabled SSO integration. 
    Those are NOT the same cluster.
    
    Issue A (Existing Cluster): {existing_cluster.representative_description}
    Issue B (New Ticket): {new_issue.normalized_problem_statement}
    
    Return JSON: {{"is_same_root_cause": true/false, "reasoning": "brief explanation"}}
    """
    if "mock" in API_KEY.lower():
        # Synthetic disambiguation
        # If one is SSO and one is Password, they are NOT the same.
        if "sso" in existing_cluster.representative_description.lower() and "password" in new_issue.normalized_problem_statement.lower():
            logger.info("Disambiguation: Symptom is similar, but root causes (SSO vs Password) differ. Rejected.")
            return False
        return True
        
    client = Anthropic(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")
    response = client.messages.create(
        model="anthropic/claude-3-opus",
        max_tokens=150,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.content[0].text).get("is_same_root_cause", False)

def match_or_create_issue_cluster(new_issue: IssueStructure, existing_clusters: List[IssueCluster]) -> ClusterMatchResult:
    """
    Implements the three-zone pattern: Auto-Merge, Ambiguous (LLM Check), New Cluster.
    """
    # Mocking vector distances for demonstration
    # In prod, this would query ChromaDB. We simulate the distances here.
    best_cluster = existing_clusters[0]
    
    # Let's mock a distance scenario
    if "sso" in best_cluster.representative_description.lower() and "sso" in new_issue.normalized_problem_statement.lower():
        distance = 0.05 # High Confidence
    elif "login" in best_cluster.representative_description.lower() and "password" in new_issue.normalized_problem_statement.lower():
        distance = 0.15 # Ambiguous Zone
    else:
        distance = 0.40 # Low Confidence
        
    AUTO_MERGE_THRESHOLD = 0.10
    NEW_CLUSTER_THRESHOLD = 0.25
    
    if distance <= AUTO_MERGE_THRESHOLD:
        logger.info(f"Auto-Merge Zone: Distance {distance:.2f} <= {AUTO_MERGE_THRESHOLD}")
        return ClusterMatchResult(cluster_id=best_cluster.cluster_id, match_type="auto_merge")
        
    elif distance <= NEW_CLUSTER_THRESHOLD:
        logger.info(f"Ambiguous Zone: Distance {distance:.2f}. Triggering LLM Disambiguation.")
        is_match = disambiguate_root_cause(new_issue, best_cluster)
        if is_match:
            return ClusterMatchResult(cluster_id=best_cluster.cluster_id, match_type="disambiguated_merge")
        else:
            new_id = f"cluster_{uuid.uuid4().hex[:8]}"
            return ClusterMatchResult(cluster_id=new_id, match_type="new_cluster")
            
    else:
        logger.info(f"New Cluster Zone: Distance {distance:.2f} > {NEW_CLUSTER_THRESHOLD}")
        new_id = f"cluster_{uuid.uuid4().hex[:8]}"
        return ClusterMatchResult(cluster_id=new_id, match_type="new_cluster")

# --- PART C: CLUSTER SPLITTING ---

def evaluate_cluster_cohesion(cluster: IssueCluster, raw_tickets_in_cluster: List[str]) -> Optional[CohesionReport]:
    """
    Background job triggered when a cluster's resolution verification rate drops suspiciously low.
    Analyzes ticket bodies to see if multiple root causes were accidentally merged.
    """
    if cluster.resolution_verification_rate > 0.60:
        logger.debug(f"Cluster {cluster.cluster_id} cohesion is healthy ({cluster.resolution_verification_rate:.2f} verification rate).")
        return None
        
    logger.warning(f"Evaluating cohesion for {cluster.cluster_id}. Verification rate critically low ({cluster.resolution_verification_rate:.2f}).")
    
    prompt = f"""
    The following support tickets were grouped under the cluster: "{cluster.representative_description}".
    However, resolutions are failing to verify, suggesting this cluster is contaminated with multiple distinct root causes.
    
    Tickets: {raw_tickets_in_cluster}
    
    Analyze the tickets and propose splitting the cluster into distinct structural root causes.
    
    Output JSON:
    {{
        "is_contaminated": true,
        "reasoning": "Explanation",
        "proposed_split_clusters": [
            {{"new_cluster_id": "subcluster_1", "new_description": "First distinct root cause", "reassigned_tickets": ["ticket_id"]}}
        ]
    }}
    """
    
    # Synthetic execution
    if "mock" in API_KEY.lower():
        logger.info("Splitting contaminated cluster into distinct root causes and resetting trust metrics.")
        return CohesionReport(
            is_contaminated=True,
            reasoning="Cluster contained both SSO outage reports and generic forgotten passwords. These require different fixes.",
            proposed_split_clusters=[
                {"new_cluster_id": "c_sso", "new_description": "SSO Provider Outage", "reassigned_tickets": ["t1", "t3"]},
                {"new_cluster_id": "c_pw", "new_description": "Forgotten Password", "reassigned_tickets": ["t2"]}
            ]
        )

# --- EXAMPLE INVOCATIONS ---

if __name__ == "__main__":
    print("\n--- ThreadSmith Structural Classification Engine ---")
    
    # 1. Customer Context-Aware Extraction
    print("\n[Part A/D: Context-Aware Extraction]")
    ticket_text = "My card was declined. I tried re-entering my card details but it still says failed. Fix this!"
    
    ctx_healthy = build_customer_context("cust_healthy").context
    res_healthy = extract_issue_structure(ticket_text, customer_context=ctx_healthy)
    print(f"Healthy Account Parse -> Problem: {res_healthy.normalized_problem_statement}")
    print(f"Prior Attempts Detected: {res_healthy.prior_resolution_attempts}")
    
    ctx_arrears = build_customer_context("cust_arrears").context
    res_arrears = extract_issue_structure(ticket_text, customer_context=ctx_arrears)
    print(f"Arrears Account Parse -> Problem: {res_arrears.normalized_problem_statement}")
    
    # 2. Three-Zone Clustering (Ambiguous Symptom vs Root Cause)
    print("\n[Part B: Three-Zone Clustering (Root Cause Disambiguation)]")
    existing = [IssueCluster(cluster_id="cluster_login_sso", representative_description="SSO Integration Login Failure", embedding=[0.0], ticket_count=50, resolution_verification_rate=0.85)]
    new_issue_ambiguous = IssueStructure(
        normalized_problem_statement="password_reset_login_failure", 
        affected_entities={}, severity_signal="medium", prior_resolution_attempts=[]
    )
    
    match_result = match_or_create_issue_cluster(new_issue_ambiguous, existing)
    print(f"Ambiguous Scenario Result: {match_result.match_type} -> Assigned to: {match_result.cluster_id}")
    
    # 3. Cluster Splitting
    print("\n[Part C: Cluster Cohesion & Splitting]")
    bad_cluster = IssueCluster(cluster_id="cluster_mixed_login", representative_description="Generic Login Failures", embedding=[0.0], ticket_count=100, resolution_verification_rate=0.20)
    tickets = ["I can't login via okta", "forgot my password", "SSO is down for our org"]
    split_report = evaluate_cluster_cohesion(bad_cluster, tickets)
    if split_report and split_report.is_contaminated:
        print(f"Contamination Detected: {split_report.reasoning}")
        for c in split_report.proposed_split_clusters:
            print(f"  -> Migrating to: {c['new_cluster_id']} ({c['new_description']})")
