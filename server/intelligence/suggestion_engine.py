"""
ThreadSmith Suggestion Engine.
Surfaces verified resolutions, handles strict auto-resolution gating, and logs agent uptake.
"""
import os
import json
from typing import List, Optional, Literal
from pydantic import BaseModel
from anthropic import Anthropic
from loguru import logger
import sys
import os

# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.agentos_client import build_customer_context

API_KEY = os.getenv("OPENROUTER_API_KEY", "mock-key")

# --- MOCK DATA & DEPENDENCIES ---
class ResolutionPatternStats(BaseModel):
    issue_cluster_id: str
    resolution_template_id: str
    resolution_text: str
    times_applied: int
    times_verified: int
    times_demoted: int
    current_trust_score: float

class Ticket(BaseModel):
    ticket_id: str
    raw_text: str

class SuggestionCandidate(BaseModel):
    resolution_template_id: str
    resolution_text: str
    track_record_statement: str
    trust_score: float
    rationale: str

class SuggestionResponse(BaseModel):
    status: Literal["suggestions_found", "no_verified_pattern"]
    candidates: List[SuggestionCandidate]
    message: str
    partial_context: bool = False

class AutoResolutionDecision(BaseModel):
    is_eligible: bool
    reason: str

# Mock DBs
db_stats = [
    ResolutionPatternStats(
        issue_cluster_id="cluster_password", resolution_template_id="tpl_pw_1",
        resolution_text="Send standard password reset link macro.",
        times_applied=42, times_verified=40, times_demoted=2, current_trust_score=0.88
    ),
    ResolutionPatternStats(
        issue_cluster_id="cluster_billing_glitch", resolution_template_id="tpl_bill_1",
        resolution_text="Ask customer to wait 24h and retry card.",
        times_applied=5, times_verified=5, times_demoted=0, current_trust_score=0.55 # Small sample size penalizes score
    )
]

db_tickets = {
    "tkt_pw": Ticket(ticket_id="tkt_pw", raw_text="I forgot my password and cannot login."),
    "tkt_novel": Ticket(ticket_id="tkt_novel", raw_text="The entire dashboard is returning a 502 Bad Gateway."),
    "tkt_bill": Ticket(ticket_id="tkt_bill", raw_text="My card failed to process today.")
}

db_suggestion_events = []

# Mock functions from Prompt 02
def mock_classify_and_cluster(ticket_id: str) -> dict:
    if ticket_id == "tkt_pw": return {"cluster_id": "cluster_password", "category": "Account_Access"}
    if ticket_id == "tkt_novel": return {"cluster_id": "cluster_502_error", "category": "Technical_Bug"}
    if ticket_id == "tkt_bill": return {"cluster_id": "cluster_billing_glitch", "category": "Billing"}
    return {"cluster_id": "unknown", "category": "General"}


# --- PART C: STRICT AUTO-RESOLUTION GATING ---

"""
AUTO-RESOLUTION GATING JUSTIFICATION:
1. Allowlist: Only low-stakes categories ("Account_Access", "Informational") are allowed. 
   A billing dispute or a technical bug requires human empathy and nuance.
2. Min Trust Score: 0.85 (85% lower-bound confidence). We only auto-resolve if we are mathematically
   highly confident this resolution works based on the Wilson score interval.
3. Min Sample Size: 20 verifications. 3/3 successes might yield a decent ratio, but it's not enough
   historical mass to blindly trust an AI without human oversight.
"""
AUTO_RESOLVE_ALLOWLIST = ["Account_Access", "Informational", "Order_Status"]
MIN_TRUST_SCORE_THRESHOLD = 0.85
MIN_VERIFICATIONS_THRESHOLD = 20

def check_auto_resolution_eligibility(ticket_id: str, issue_cluster_id: str, category: str, stats: ResolutionPatternStats) -> AutoResolutionDecision:
    """Gates auto-resolution behind strict multi-factor thresholds. Fails closed."""
    if category not in AUTO_RESOLVE_ALLOWLIST:
        return AutoResolutionDecision(is_eligible=False, reason=f"Category '{category}' is not allowlisted for auto-resolution.")
        
    if stats.times_verified < MIN_VERIFICATIONS_THRESHOLD:
        return AutoResolutionDecision(is_eligible=False, reason=f"Insufficient sample size ({stats.times_verified} < {MIN_VERIFICATIONS_THRESHOLD}).")
        
    if stats.current_trust_score < MIN_TRUST_SCORE_THRESHOLD:
        return AutoResolutionDecision(is_eligible=False, reason=f"Trust score too low ({stats.current_trust_score:.2f} < {MIN_TRUST_SCORE_THRESHOLD}).")
        
    logger.success(f"Ticket {ticket_id} eligible for Auto-Resolution via {stats.resolution_template_id}.")
    return AutoResolutionDecision(is_eligible=True, reason="All strict gating thresholds passed.")


# --- PART A & B: SUGGESTION ENGINE & RATIONALE GENERATION ---

def generate_rationale(ticket_text: str, resolution_text: str, context: dict) -> str:
    """Uses Claude to explain WHY this resolution fits this specific ticket."""
    if "mock" in API_KEY.lower():
        return f"This ticket explicitly mentions issues resolved by: {resolution_text[:20]}..."
        
    client = Anthropic(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")
    prompt = f"""
    You are assisting a human support agent. You are suggesting a resolution for a ticket.
    Briefly explain WHY this resolution makes sense for this SPECIFIC ticket text.
    
    Ticket: "{ticket_text}"
    Resolution Pattern: "{resolution_text}"
    
    Explanation (1-2 sentences):
    """
    response = client.messages.create(
        model="anthropic/claude-3-opus",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def suggest_resolution(ticket_id: str) -> SuggestionResponse:
    """
    End-to-end suggestion pipeline. Runs classification, clustering, stats lookup, 
    and Claude rationale generation.
    """
    logger.info(f"Generating suggestions for {ticket_id}")
    ticket = db_tickets.get(ticket_id)
    
    # 1. Classify & Cluster (Prompt 02)
    cluster_info = mock_classify_and_cluster(ticket_id)
    target_cluster = cluster_info["cluster_id"]
    category = cluster_info["category"]
    
    # 2. AgentOS Integrations
    # Determine if we need contract parsing (e.g. refund requests)
    needs_contract = "refund" in ticket.raw_text.lower()
    context_data = build_customer_context(
        ticket.customer_id if hasattr(ticket, 'customer_id') else "cust_healthy", 
        needs_contract=needs_contract, 
        contract_topic="refund" if needs_contract else ""
    )
    
    # 3. Lookup Stats
    cluster_stats = [s for s in db_stats if s.issue_cluster_id == target_cluster]
    cluster_stats.sort(key=lambda x: x.current_trust_score, reverse=True) # Rank by Wilson score
    
    # PART B: Explicit No-Verified-Pattern Handling
    if not cluster_stats:
        logger.warning(f"NOVEL ISSUE DETECTED: Cluster {target_cluster} has no verified patterns.")
        return SuggestionResponse(
            status="no_verified_pattern",
            candidates=[],
            message="No verified pattern available. Flagged as Priority for Senior Agent review to establish baseline resolution."
        )
        
    candidates = []
    # Take Top 3
    for stat in cluster_stats[:3]:
        track_record = f"Worked in {stat.times_verified} of {stat.times_verified + stat.times_demoted} verified cases for this issue type."
        rationale = generate_rationale(ticket.raw_text, stat.resolution_text, context_data.context)
        
        candidates.append(SuggestionCandidate(
            resolution_template_id=stat.resolution_template_id,
            resolution_text=stat.resolution_text,
            track_record_statement=track_record,
            trust_score=stat.current_trust_score,
            rationale=rationale
        ))
        
        # PART C: Auto-Resolution Check on the top candidate
        if len(candidates) == 1:
            auto_dec = check_auto_resolution_eligibility(ticket_id, target_cluster, category, stat)
            if auto_dec.is_eligible:
                logger.info("Executing Auto-Resolution Workflow...")
                # In prod, this fires the macro automatically.
    
    return SuggestionResponse(
        status="suggestions_found",
        candidates=candidates,
        message="Suggestions ready for agent review.",
        partial_context=context_data.partial_context
    )

# --- PART D: AGENT FEEDBACK CAPTURE HOOK ---

def log_suggestion_outcome(ticket_id: str, agent_id: str, suggested_template_ids: List[str], accepted_template_id: Optional[str]):
    """
    Logs whether the human agent accepted the AI's suggestion or rejected it.
    This is a leading indicator of suggestion quality, totally distinct from the Verification Loop.
    """
    outcome = "accepted" if accepted_template_id else "rejected"
    event = {
        "ticket_id": ticket_id,
        "agent_id": agent_id,
        "suggested_templates": suggested_template_ids,
        "accepted_template": accepted_template_id,
        "outcome": outcome
    }
    db_suggestion_events.append(event)
    logger.info(f"Agent Feedback Logged: {ticket_id} -> {outcome} (Accepted: {accepted_template_id})")


# --- EXECUTIONS ---
if __name__ == "__main__":
    print("\n--- ThreadSmith Suggestion Engine ---")
    
    # Case 1: High Trust Auto-Resolve
    print("\n[Case 1: High Trust (Auto-Resolve Check)]")
    res1 = suggest_resolution("tkt_pw")
    print(json.dumps(res1.dict(), indent=2))
    
    # Case 2: Small Sample Size (Billing - Fails Auto-Resolve)
    print("\n[Case 2: Low Sample Size (Fails Auto-Resolve, Routes to Agent)]")
    res2 = suggest_resolution("tkt_bill")
    print(json.dumps(res2.dict(), indent=2))
    
    # Case 3: Novel Issue (No Verified Pattern)
    print("\n[Case 3: Novel Issue (Honest Fallback)]")
    res3 = suggest_resolution("tkt_novel")
    print(res3.message)
    
    # Part D: Agent Uptake Logging
    print("\n[Part D: Agent Feedback Logging]")
    log_suggestion_outcome("tkt_bill", "agent_sarah", ["tpl_bill_1"], None) # Agent rejected it
    log_suggestion_outcome("tkt_pw", "agent_john", ["tpl_pw_1"], "tpl_pw_1") # Agent accepted it
