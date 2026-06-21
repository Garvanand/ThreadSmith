"""
ThreadSmith -> AgentOS Client.
Handles cross-agent integrations with ForgeSign (Day 13) and GhostCFO (Day 02).
Implements graceful degradation.
"""
import requests
from loguru import logger
from typing import Dict, Any, Tuple

# In a real environment, these are actual microservice URLs
FORGESIGN_URL = "http://forgesign:8013"
GHOSTCFO_URL = "http://ghostcfo:8002"

class AgentOSContextResult:
    def __init__(self, context: Dict[str, Any], partial_context: bool):
        self.context = context
        self.partial_context = partial_context

def fetch_forgesign_terms(customer_id: str, topic: str) -> Tuple[Dict[str, Any], bool]:
    """
    Fetches actual contract clauses for a specific topic (e.g., 'refund').
    Returns (data, is_error).
    """
    try:
        # url = f"{FORGESIGN_URL}/api/v1/contracts/{customer_id}/terms?topic={topic}"
        # response = requests.get(url, timeout=2.0)
        # response.raise_for_status()
        # return response.json(), False
        
        # Simulated Network Call
        logger.info(f"Querying ForgeSign for {customer_id} on topic '{topic}'")
        if customer_id == "cust_timeout":
            raise requests.Timeout("Connection to ForgeSign timed out.")
        return {"contract_clause": "Refunds are only eligible within 14 days of purchase."}, False
    except requests.RequestException as e:
        logger.warning(f"ForgeSign unreachable: {e}. Gracefully degrading.")
        return {}, True

def fetch_ghostcfo_health(customer_id: str) -> Tuple[Dict[str, Any], bool]:
    """
    Reuses the Day 17 ClosedLoop endpoint.
    Fetches payment failure history and arrears status.
    Returns (data, is_error).
    """
    try:
        # url = f"{GHOSTCFO_URL}/api/v1/accounts/{customer_id}/payment-health"
        # response = requests.get(url, timeout=2.0)
        # response.raise_for_status()
        # return response.json(), False
        
        # Simulated Network Call
        logger.info(f"Querying GhostCFO for {customer_id}")
        if customer_id == "cust_timeout":
            raise requests.Timeout("Connection to GhostCFO timed out.")
        if customer_id == "cust_arrears":
            return {"status": "ARREARS", "failed_payments_last_30d": 3, "days_overdue": 45}, False
        return {"status": "HEALTHY", "failed_payments_last_30d": 0, "days_overdue": 0}, False
    except requests.RequestException as e:
        logger.warning(f"GhostCFO unreachable: {e}. Gracefully degrading.")
        return {}, True

def build_customer_context(customer_id: str, needs_contract: bool = False, contract_topic: str = "") -> AgentOSContextResult:
    """
    Aggregates available context from the AgentOS ecosystem.
    If any agent fails to respond, partial_context is set to True so the 
    human agent is warned to check manually.
    """
    context = {}
    partial = False
    
    # Always fetch billing health
    health_data, health_error = fetch_ghostcfo_health(customer_id)
    if health_error:
        partial = True
    elif health_data:
        context["ghostcfo"] = health_data
        
    # Fetch contract terms if requested
    if needs_contract and contract_topic:
        term_data, term_error = fetch_forgesign_terms(customer_id, contract_topic)
        if term_error:
            partial = True
        elif term_data:
            context["forgesign"] = term_data
            
    return AgentOSContextResult(context=context, partial_context=partial)

if __name__ == "__main__":
    print("\n--- Testing AgentOS Integration Client ---")
    
    print("\n1. Healthy Fetch")
    res1 = build_customer_context("cust_arrears", needs_contract=True, contract_topic="refund")
    print("Context:", res1.context)
    print("Partial Flag:", res1.partial_context)
    
    print("\n2. Degraded Fetch (Timeout)")
    res2 = build_customer_context("cust_timeout", needs_contract=True, contract_topic="refund")
    print("Context:", res2.context)
    print("Partial Flag:", res2.partial_context)
