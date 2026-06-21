"""
ThreadSmith Structural Classification Node
Uses Claude-3-Opus to extract the underlying intent, separating it from surface wording.
"""
import os
import json
from loguru import logger
from pydantic import BaseModel
from anthropic import Anthropic

API_KEY = os.getenv("OPENROUTER_API_KEY", "mock-key")

class StructuredIntent(BaseModel):
    core_issue: str
    entities: dict
    category: str

def extract_structural_intent(raw_ticket_text: str) -> dict:
    """
    Given a ticket like "my card got declined again wtf",
    extracts the structural issue: "payment_failure_decline", category: "Billing".
    """
    logger.info(f"Extracting structural intent for: '{raw_ticket_text[:30]}...'")
    
    if "mock" in API_KEY.lower():
        # Synthetic fallback
        if "card" in raw_ticket_text.lower() or "payment" in raw_ticket_text.lower():
            return {"core_issue": "payment_failure_decline", "category": "Billing", "entities": {"method": "card"}}
        elif "password" in raw_ticket_text.lower():
            return {"core_issue": "password_reset_request", "category": "Account", "entities": {}}
        return {"core_issue": "unknown_inquiry", "category": "General", "entities": {}}

    client = Anthropic(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")
    prompt = f"""
    You are the ThreadSmith structural classification engine.
    Analyze the following support ticket. Strip away the user's specific wording, emotion, and frustration.
    Identify the underlying structural issue.
    
    Ticket: "{raw_ticket_text}"
    
    Output JSON:
    {{
        "core_issue": "A concise, snake_case descriptor of the fundamental problem (e.g., payment_failure_decline)",
        "category": "Broad category (e.g., Billing, Technical, Account)",
        "entities": {{"key": "value"}} // Any specific parameters mentioned
    }}
    """
    response = client.messages.create(
        model="anthropic/claude-3-opus",
        max_tokens=300,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.content[0].text)

if __name__ == "__main__":
    from pydantic import BaseModel
    # Quick Test
    intent1 = extract_structural_intent("My credit card was declined twice today.")
    intent2 = extract_structural_intent("why did my payment fail again wtf fix this")
    print("Intent 1:", intent1)
    print("Intent 2:", intent2)
    # Both should yield 'payment_failure_decline' despite different surface syntax.
