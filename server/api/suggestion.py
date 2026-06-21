"""
ThreadSmith Suggestion API
Surfaces verified resolutions to human agents and handles scoped auto-resolutions.
Integrates with AgentOS (GhostCFO, ForgeSign).
"""
import os
import json
from fastapi import APIRouter
from pydantic import BaseModel
from database.models import db_stats, db_resolutions
from anthropic import Anthropic

router = APIRouter(prefix="/api/v1/suggestions", tags=["Suggestions"])
API_KEY = os.getenv("OPENROUTER_API_KEY", "mock-key")

class SuggestionRequest(BaseModel):
    ticket_id: str
    customer_id: str
    issue_cluster_id: str
    category: str

# SAFE CATEGORIES FOR AUTO-RESOLUTION (MVP Scope)
SAFE_CATEGORIES = ["Account_Password", "Order_Status"]

# MOCK AGENTOS INTEGRATION
def call_forgesign(customer_id: str, topic: str):
    # GET http://forgesign:8013/api/v1/contracts/{customer_id}/terms?topic={topic}
    return {"contract_clause": "Refunds are only eligible within 14 days of purchase."}

def call_ghostcfo(customer_id: str):
    # GET http://ghostcfo:8002/api/v1/accounts/{customer_id}/payment-health
    return {"status": "ARREARS", "days_overdue": 45}

def generate_reasoning_with_claude(resolution_text: str, context: dict) -> str:
    if "mock" in API_KEY.lower():
        return "This resolution worked 95% of the time for similar billing issues. Note: Customer is in arrears."
        
    client = Anthropic(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")
    prompt = f"""
    Explain to a human support agent why you are suggesting this resolution.
    Resolution: {resolution_text}
    Context: {context}
    Keep it under 3 sentences.
    """
    response = client.messages.create(
        model="anthropic/claude-3-opus",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

@router.post("/get_suggestion")
def get_suggestion(req: SuggestionRequest):
    """
    Evaluates the issue cluster and surfaces the highest-trust resolution.
    """
    # 1. Fetch highest-trust resolution for this cluster
    stat = db_stats.get(req.issue_cluster_id)
    if not stat or stat.current_trust_score < 0.70:
        return {"status": "no_verified_pattern", "action": "route_to_human"}
        
    # Find the actual text associated with this pattern
    resolution_text = "Standard macro text for this issue." # Simplified lookup
    
    # 2. AgentOS Integrations
    context = {}
    if req.category == "Billing":
        context["ghostcfo"] = call_ghostcfo(req.customer_id)
        context["forgesign"] = call_forgesign(req.customer_id, "refund")
        
    # 3. Auto-Resolution Check
    if req.category in SAFE_CATEGORIES and stat.current_trust_score > 0.95:
        # High confidence, narrow safe zone.
        return {
            "status": "auto_resolved",
            "resolution_applied": resolution_text,
            "trust_score": stat.current_trust_score
        }
        
    # 4. Human Agent Suggestion
    reasoning = generate_reasoning_with_claude(resolution_text, context)
    
    return {
        "status": "suggested_to_agent",
        "suggestion": resolution_text,
        "trust_score": stat.current_trust_score,
        "agentos_context": context,
        "reasoning": reasoning
    }

if __name__ == "__main__":
    # Test Auto-Resolve
    print("\n--- Testing Suggestion Router ---")
    db_stats["cluster_pw"] = type('obj', (object,), {'current_trust_score': 0.98})
    r1 = get_suggestion(SuggestionRequest(ticket_id="t1", customer_id="c1", issue_cluster_id="cluster_pw", category="Account_Password"))
    print("Test Auto-Resolve (Password, High Trust):", r1)
    
    # Test Human Suggestion + AgentOS Integration
    db_stats["cluster_billing"] = type('obj', (object,), {'current_trust_score': 0.85})
    r2 = get_suggestion(SuggestionRequest(ticket_id="t2", customer_id="c2", issue_cluster_id="cluster_billing", category="Billing"))
    print("\nTest Human Suggestion (Billing, Med Trust):", json.dumps(r2, indent=2))
