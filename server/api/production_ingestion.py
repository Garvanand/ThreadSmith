"""
ThreadSmith Production Ingestion Layer.
Connects ThreadSmith to external platforms (Zendesk, Intercom) via adapter patterns.
Handles deduplication, provisional logging triggers, and reverse macro syncs.
"""
import time
import requests
from typing import Optional, Dict
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/threadsmith/api/v1/tickets", tags=["Ingestion"])

# --- DATA MODELS ---

class NormalizedTicket(BaseModel):
    platform: str
    ticket_id: str
    event_id: str
    event_timestamp: int
    customer_id: str
    agent_id: Optional[str] = None
    event_type: str # "ticket.created", "ticket.closed"
    content: str
    resolution_text: Optional[str] = None

# Mock Idempotency Store (Redis in prod)
PROCESSED_EVENTS = set()

# --- ADAPTERS ---

def normalize_zendesk_payload(raw: dict) -> NormalizedTicket:
    """Zendesk specific webhook parsing."""
    ticket = raw.get("ticket", {})
    event_type = "ticket.closed" if ticket.get("status") == "closed" else "ticket.created"
    
    # Extracting the resolution: Zendesk has custom fields, or we use last reply.
    resolution_text = None
    if event_type == "ticket.closed":
        # Check explicit custom 'Resolution Note' field first
        custom_fields = ticket.get("custom_fields", [])
        for cf in custom_fields:
            if cf.get("id") == "resolution_note_id" and cf.get("value"):
                resolution_text = cf.get("value")
                break
        
        # Fallback to the last agent comment
        if not resolution_text:
            comments = ticket.get("comments", [])
            agent_comments = [c for c in comments if c.get("author_id") != ticket.get("requester_id")]
            if agent_comments:
                resolution_text = agent_comments[-1].get("body")
                
    return NormalizedTicket(
        platform="zendesk",
        ticket_id=str(ticket.get("id")),
        event_id=raw.get("id", str(time.time())),
        event_timestamp=raw.get("timestamp", int(time.time())),
        customer_id=str(ticket.get("requester_id")),
        agent_id=str(ticket.get("assignee_id")),
        event_type=event_type,
        content=ticket.get("description", ""),
        resolution_text=resolution_text
    )

def normalize_intercom_payload(raw: dict) -> NormalizedTicket:
    """Stub for Intercom."""
    raise NotImplementedError("Intercom adapter pending.")

def normalize_freshdesk_payload(raw: dict) -> NormalizedTicket:
    """Stub for Freshdesk."""
    raise NotImplementedError("Freshdesk adapter pending.")

# --- REVERSE SYNC ---

def sync_macro_to_zendesk(suggested_text: str, title: str):
    """
    Posts a successfully accepted ThreadSmith resolution back to Zendesk 
    as a canned Macro for native agent use.
    """
    logger.info(f"Syncing macro to Zendesk: '{title}'")
    # In prod:
    # url = "https://your_domain.zendesk.com/api/v2/macros.json"
    # payload = {
    #     "macro": {
    #         "title": f"ThreadSmith: {title}",
    #         "actions": [{"field": "comment_value", "value": suggested_text}]
    #     }
    # }
    # requests.post(url, json=payload, auth=("user@email.com/token", "ZENDESK_TOKEN"))
    return True

# --- API ENDPOINT ---

@router.post("/webhook")
def process_webhook(payload: dict, x_platform: str = Header("zendesk")):
    """Generic entry point. Normalizes, deduplicates, and routes."""
    
    # 1. Normalize
    if x_platform == "zendesk":
        normalized = normalize_zendesk_payload(payload)
    elif x_platform == "intercom":
        normalized = normalize_intercom_payload(payload)
    else:
        raise HTTPException(status_code=400, detail="Unknown platform")
        
    # 2. Deduplicate
    idempotency_key = f"{normalized.platform}_{normalized.ticket_id}_{normalized.event_timestamp}"
    if idempotency_key in PROCESSED_EVENTS:
        logger.debug(f"Ignored duplicate event: {idempotency_key}")
        return {"status": "ignored", "reason": "duplicate"}
    PROCESSED_EVENTS.add(idempotency_key)
    
    # 3. Route
    if normalized.event_type == "ticket.created":
        logger.info(f"New ticket ingested: {normalized.ticket_id}. Triggering clustering.")
        # Trigger Prompt 02 structural classification here
        
    elif normalized.event_type == "ticket.closed":
        if normalized.resolution_text:
            logger.info(f"Ticket {normalized.ticket_id} closed. Triggering provisional logging.")
            # Trigger Prompt 03 Part A Provisional Logging
            # log_provisional_resolution(normalized.ticket_id, normalized.resolution_text, ...)
        else:
            logger.warning(f"Ticket {normalized.ticket_id} closed without resolution text.")
            
    return {"status": "processed", "idempotency_key": idempotency_key}

# --- TEST HARNESS ---

if __name__ == "__main__":
    print("\n--- ThreadSmith Ingestion Layer Tests ---")
    
    # 1. Zendesk Normalization & Deduplication
    mock_zd_payload = {
        "id": "evt_123",
        "timestamp": 1680000000,
        "ticket": {
            "id": 9991,
            "status": "closed",
            "requester_id": "cust_88",
            "assignee_id": "agt_1",
            "description": "My api key is broken.",
            "comments": [
                {"author_id": "cust_88", "body": "My api key is broken."},
                {"author_id": "agt_1", "body": "I have regenerated your key in the dashboard."}
            ]
        }
    }
    
    print("\n[Testing Webhook Processing]")
    res1 = process_webhook(mock_zd_payload, x_platform="zendesk")
    print("Initial processing:", res1)
    
    # Retry/Replay from Zendesk
    res2 = process_webhook(mock_zd_payload, x_platform="zendesk")
    print("Retry processing (Deduplication):", res2)
    
    # 2. Reverse Sync
    print("\n[Testing Reverse Macro Sync]")
    sync_macro_to_zendesk("I have regenerated your key in the dashboard.", "API Key Regen")
