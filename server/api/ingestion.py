"""
ThreadSmith Ingestion Pipeline
Parses incoming webhooks using Groq's Llama-3-70b for speed.
"""
import os
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from anthropic import Anthropic # Used as OpenRouter client for Groq

from database.models import Ticket, db_tickets

router = APIRouter(prefix="/api/v1/ingestion", tags=["Ingestion"])
API_KEY = os.getenv("OPENROUTER_API_KEY", "mock-key")

class WebhookPayload(BaseModel):
    source: str # e.g. "zendesk"
    event_type: str # e.g. "ticket.created"
    ticket_id: str
    org_id: str
    customer_id: str
    content: str
    timestamp: str

def parse_with_groq(raw_content: str) -> dict:
    """
    Uses Groq Llama-3-70b to rapidly parse and normalize the ticket payload.
    We use Groq here because it's a high-frequency, low-stakes routing step.
    """
    if "mock" in API_KEY.lower():
        # Synthetic fallback
        return {
            "is_spam": False,
            "normalized_text": raw_content.strip()
        }
        
    client = Anthropic(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")
    prompt = f"""
    You are a fast ingestion parser for a customer support AI.
    Extract and normalize the core text of this ticket, ignoring email signatures and boilerplate.
    Determine if it is spam/automated bounce.
    
    Ticket: "{raw_content}"
    
    Output JSON:
    {{
        "is_spam": bool,
        "normalized_text": "Cleaned core issue text"
    }}
    """
    response = client.messages.create(
        model="groq/llama-3.3-70b-versatile",
        max_tokens=200,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.content[0].text)

@router.post("/webhook")
def receive_ticket(payload: WebhookPayload):
    """
    Ingests a raw ticket from a support platform and writes it to DB.
    """
    parsed_data = parse_with_groq(payload.content)
    
    if parsed_data.get("is_spam", False):
        return {"status": "ignored", "reason": "spam_detected"}
        
    # Standardize and save
    new_ticket = Ticket(
        ticket_id=payload.ticket_id,
        org_id=payload.org_id,
        customer_id=payload.customer_id,
        raw_text=parsed_data.get("normalized_text", payload.content),
        opened_at=datetime.now(timezone.utc),
        status="open"
    )
    
    db_tickets[new_ticket.ticket_id] = new_ticket
    
    # In a full pipeline, we would now trigger the LangGraph flow:
    # -> Structural Classification -> Clustering -> Suggestion
    
    return {"status": "ingested", "ticket_id": new_ticket.ticket_id}
