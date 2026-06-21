"""
ThreadSmith Advanced Verification Loop.
The core engine: handles provisional logging, tiered windows, Wilson-score trust computation,
and sophisticated structural recurrence detection.
"""
import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, List, Dict
from pydantic import BaseModel
from loguru import logger

# --- DATA MODELS (Extended for Lineage & Confidence) ---

class ResolutionPatternStats(BaseModel):
    issue_cluster_id: str
    resolution_template_id: str
    times_applied: int = 0
    times_verified: int = 0
    times_demoted: int = 0
    recent_demotions_last_30d: int = 0
    current_trust_score: float = 0.0
    confidence_lower_bound: float = 0.0

class Resolution(BaseModel):
    resolution_id: str
    ticket_id: str
    issue_cluster_id: str
    resolution_template_id: str # Lineage tracking identifier
    resolution_text: str
    applied_by_agent_id: str
    applied_at: datetime
    verification_status: Literal["provisional", "verified", "demoted"]
    verification_window_ends_at: datetime
    demotion_reason: Optional[str] = None

class Ticket(BaseModel):
    ticket_id: str
    customer_id: str
    issue_cluster_id: str
    opened_at: datetime
    raw_text: str = ""

# Mock DBs
db_resolutions: Dict[str, Resolution] = {}
db_stats: Dict[str, ResolutionPatternStats] = {}
db_tickets: Dict[str, Ticket] = {}

# --- PART A: TIERED WINDOW MAPPING & PROVISIONAL LOGGING ---

"""
TIERED OBSERVATION WINDOW REASONING TABLE:
1. "Informational": 72 hours.
   - Example: "How do I reset my password?" "Where is my invoice?"
   - Reasoning: These are binary. If the answer is wrong or the link is broken, the customer 
     replies immediately. If they don't reply within 3 days, the problem is solved.
2. "Transactional/Billing": 5 days.
   - Example: "Refund my double charge." "Update my credit card."
   - Reasoning: Bank processing times can take 2-4 days to reflect. Customers will wait to check 
     their statement before complaining again that the refund didn't process.
3. "Technical_Bug": 14 days.
   - Example: "The API drops connection every few hours." "My SSO integration fails."
   - Reasoning: A "fix" might seem to work initially, but edge cases or intermittent bugs might 
     take up to two weeks to re-manifest and frustrate the customer into reopening a ticket.
4. "Hardware/Shipping": 21 days.
   - Example: "My replacement device never arrived."
   - Reasoning: Physical logistics. We cannot verify a resolution to a shipping issue until enough 
     time has passed for the physical item to arrive and be tested by the user.
"""
CATEGORY_WINDOW_MAP = {
    "Informational": timedelta(hours=72),
    "Transactional/Billing": timedelta(days=5),
    "Technical_Bug": timedelta(days=14),
    "Hardware/Shipping": timedelta(days=21)
}

def log_provisional_resolution(
    ticket_id: str, 
    resolution_text: str, 
    resolution_template_id: str,
    agent_id: str, 
    issue_cluster_id: str,
    category: str,
    current_time: datetime
) -> Resolution:
    """Logs a resolution provisionally and assigns the correct observation window."""
    window = CATEGORY_WINDOW_MAP.get(category, timedelta(days=7)) # Default 7 days
    
    res = Resolution(
        resolution_id=f"res_{uuid.uuid4().hex[:8]}",
        ticket_id=ticket_id,
        issue_cluster_id=issue_cluster_id,
        resolution_template_id=resolution_template_id,
        resolution_text=resolution_text,
        applied_by_agent_id=agent_id,
        applied_at=current_time,
        verification_status="provisional",
        verification_window_ends_at=current_time + window
    )
    db_resolutions[res.resolution_id] = res
    logger.info(f"Provisional logging: {res.resolution_id} | Window: {window.days} days ({category})")
    return res


# --- PART B: RECURRENCE DETECTION (LITERAL & STRUCTURAL LINEAGE) ---

class RecurrenceCheckResult(BaseModel):
    has_recurred: bool
    recurrence_type: Optional[Literal["literal", "structural_lineage"]]
    recurring_ticket_id: Optional[str]

def check_for_recurrence(resolution_id: str, current_time: datetime) -> RecurrenceCheckResult:
    """
    Checks for recurrence across two channels:
    1. Literal: Did THIS customer reopen THIS ticket or a new ticket in the SAME cluster?
    2. Structural Lineage: Did ANY customer who received THIS resolution template for THIS cluster 
       open a new ticket in the cluster recently?
    """
    target_res = db_resolutions.get(resolution_id)
    if not target_res:
        return RecurrenceCheckResult(has_recurred=False, recurrence_type=None, recurring_ticket_id=None)
        
    target_ticket = db_tickets.get(target_res.ticket_id)
    if not target_ticket:
        return RecurrenceCheckResult(has_recurred=False, recurrence_type=None, recurring_ticket_id=None)

    # 1. Literal Channel (Same customer, same cluster, opened AFTER resolution applied)
    for t_id, t in db_tickets.items():
        if t.customer_id == target_ticket.customer_id and t.issue_cluster_id == target_res.issue_cluster_id:
            if t.opened_at > target_res.applied_at:
                logger.warning(f"LITERAL RECURRENCE: Customer {t.customer_id} reopened structural issue {t.issue_cluster_id}")
                return RecurrenceCheckResult(has_recurred=True, recurrence_type="literal", recurring_ticket_id=t_id)

    # 2. Structural Lineage Channel (Different customer, same resolution template, same cluster)
    # If agent A used template X on cust A, and it failed for cust A... we want to flag if
    # agent B used template X on cust B.
    for r_id, r in db_resolutions.items():
        if r.resolution_template_id == target_res.resolution_template_id and r.issue_cluster_id == target_res.issue_cluster_id:
            if r.verification_status == "demoted" and (current_time - r.applied_at).days <= 7:
                # If the lineage failed recently for someone else, we preemptively flag this pattern.
                logger.warning(f"STRUCTURAL LINEAGE RECURRENCE: Resolution template {r.resolution_template_id} recently failed elsewhere.")
                return RecurrenceCheckResult(has_recurred=True, recurrence_type="structural_lineage", recurring_ticket_id=r.ticket_id)

    return RecurrenceCheckResult(has_recurred=False, recurrence_type=None, recurring_ticket_id=None)


# --- PART C & D: WINDOW RESOLUTION & WILSON SCORE COMPUTATION ---

def compute_trust_score(stat: ResolutionPatternStats) -> float:
    """
    Calculates a Wilson Score Interval lower bound, adjusted for recent demotions.
    Why Wilson? 2/2 success shouldn't outrank 38/40 success. Wilson inherently penalizes 
    small sample sizes.
    """
    n = stat.times_verified + stat.times_demoted
    if n == 0:
        stat.current_trust_score = 0.0
        stat.confidence_lower_bound = 0.0
        return 0.0
        
    z = 1.96 # 95% confidence interval
    phat = stat.times_verified / n
    
    # Wilson score interval lower bound
    denominator = 1 + z**2/n
    numerator = phat + z**2/(2*n) - z * math.sqrt((phat*(1-phat) + z**2/(4*n))/n)
    wilson_lower_bound = numerator / denominator
    
    # Recency Weighting: Heavy penalty if demoted recently (last 30d)
    # Systems change. Old fixes stop working.
    recency_penalty = 0.15 * stat.recent_demotions_last_30d
    
    final_score = max(0.0, wilson_lower_bound - recency_penalty)
    
    stat.current_trust_score = final_score
    stat.confidence_lower_bound = wilson_lower_bound
    return final_score

def resolve_verification_window(current_time: datetime):
    """
    Celery Beat job (runs hourly).
    Finds expired provisional windows and processes promotion/demotion.
    """
    logger.info("Starting hourly verification sweep...")
    for res_id, res in list(db_resolutions.items()):
        if res.verification_status == "provisional" and current_time >= res.verification_window_ends_at:
            
            recurrence = check_for_recurrence(res_id, current_time)
            stat = db_stats.get(res.issue_cluster_id)
            if not stat:
                stat = ResolutionPatternStats(issue_cluster_id=res.issue_cluster_id, resolution_template_id=res.resolution_template_id)
                db_stats[res.issue_cluster_id] = stat

            if not recurrence.has_recurred:
                # PROMOTION
                res.verification_status = "verified"
                stat.times_verified += 1
                logger.success(f"PROMOTED: {res_id} survived window. ({stat.times_verified} verifications)")
            else:
                # DEMOTION & ROOT CAUSE ANALYSIS
                res.verification_status = "demoted"
                stat.times_demoted += 1
                stat.recent_demotions_last_30d += 1
                
                # Mocking a call to Claude to determine WHY it recurred
                recurring_tkt = db_tickets.get(recurrence.recurring_ticket_id)
                if recurring_tkt and "unrelated" in getattr(recurring_tkt, "raw_text", "").lower():
                    # Customer reopened ticket, but it's actually a completely unrelated problem.
                    # This is a CLUSTER CONTAMINATION error, not a resolution failure!
                    res.demotion_reason = "cluster_contamination_detected"
                    logger.error(f"FALSE DEMOTION: Recurrence is unrelated. Routing cluster {res.issue_cluster_id} to Cohesion Review.")
                    # In prod: trigger_cohesion_review(res.issue_cluster_id)
                    # We do NOT penalize the resolution stats here.
                    stat.times_demoted -= 1
                    stat.recent_demotions_last_30d -= 1
                else:
                    res.demotion_reason = "resolution_failed_to_hold"
                    logger.warning(f"TRUE DEMOTION: Resolution {res_id} failed. Penalty applied.")
            
            compute_trust_score(stat)
            logger.info(f"Updated Trust Score for {res.issue_cluster_id}: {stat.current_trust_score:.2f} (n={stat.times_verified+stat.times_demoted})")


# --- EXAMPLE INVOCATIONS ---
if __name__ == "__main__":
    print("\n--- ThreadSmith Advanced Verification Loop ---")
    t0 = datetime.now(timezone.utc)
    
    # Setup base stats to show Wilson score in action
    # 2/2 Success vs 38/40 Success
    s_small = ResolutionPatternStats(issue_cluster_id="c_small", resolution_template_id="t1", times_verified=2, times_demoted=0)
    s_large = ResolutionPatternStats(issue_cluster_id="c_large", resolution_template_id="t2", times_verified=38, times_demoted=2)
    print(f"Trust Score (2/2 verified): {compute_trust_score(s_small):.2f}")
    print(f"Trust Score (38/40 verified): {compute_trust_score(s_large):.2f}")
    print("Notice how the Wilson lower-bound heavily penalizes the 2/2 sample size despite a 100% raw ratio.")
    
    # 1. Promotion Case (Informational)
    db_tickets["t_info"] = Ticket(ticket_id="t_info", customer_id="c1", issue_cluster_id="cluster_info", opened_at=t0)
    res_1 = log_provisional_resolution("t_info", "Reset link sent.", "temp_info", "agent_1", "cluster_info", "Informational", t0)
    
    # 2. True Demotion Case (Technical Bug)
    db_tickets["t_bug"] = Ticket(ticket_id="t_bug", customer_id="c2", issue_cluster_id="cluster_bug", opened_at=t0)
    res_2 = log_provisional_resolution("t_bug", "Restarted pod.", "temp_bug", "agent_2", "cluster_bug", "Technical_Bug", t0)
    # 5 days later, customer opens same issue
    db_tickets["t_bug_recur"] = Ticket(ticket_id="t_bug_recur", customer_id="c2", issue_cluster_id="cluster_bug", opened_at=t0 + timedelta(days=5))
    
    # 3. Misclassification-Driven False Demotion Case
    db_tickets["t_mis"] = Ticket(ticket_id="t_mis", customer_id="c3", issue_cluster_id="cluster_mis", opened_at=t0)
    res_3 = log_provisional_resolution("t_mis", "Fixed billing.", "temp_mis", "agent_3", "cluster_mis", "Transactional/Billing", t0)
    # 2 days later, customer opens ticket in same cluster but it's an UNRELATED issue
    t_mis_recur = Ticket(ticket_id="t_mis_recur", customer_id="c3", issue_cluster_id="cluster_mis", opened_at=t0 + timedelta(days=2))
    t_mis_recur.raw_text = "Actually this is totally unrelated to the last thing but..."
    db_tickets["t_mis_recur"] = t_mis_recur
    
    # Run Sweep (Fast forward 25 days to clear all windows)
    print("\n--- Running Celery Beat Sweep (Fast Forward 25 Days) ---")
    resolve_verification_window(t0 + timedelta(days=25))
