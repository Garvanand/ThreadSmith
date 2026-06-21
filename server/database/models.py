"""
ThreadSmith Data Models
Maps directly to the Day 21 Postgres MVP architecture.
"""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

class Ticket(BaseModel):
    ticket_id: str
    org_id: str
    customer_id: str
    raw_text: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    status: str = "open"

class IssueCluster(BaseModel):
    cluster_id: str
    representative_description: str
    embedding_chroma_ref: str
    first_seen_at: datetime
    ticket_count: int = 1

class Resolution(BaseModel):
    resolution_id: str
    ticket_id: str
    issue_cluster_id: str
    resolution_text: str
    applied_by_agent_id: str
    applied_at: datetime
    verification_status: str # "provisional", "verified", "demoted"
    verification_window_ends_at: datetime

class RecurrenceEvent(BaseModel):
    event_id: str
    original_resolution_id: str
    recurring_ticket_id: str
    detected_at: datetime

class ResolutionPatternStats(BaseModel):
    issue_cluster_id: str
    resolution_template_id: str
    times_applied: int = 0
    times_verified: int = 0
    times_demoted: int = 0
    current_trust_score: float = 0.0

# Mock DB for fast execution
db_tickets = {}
db_clusters = {}
db_resolutions = {}
db_recurrence_events = {}
db_stats = {}
