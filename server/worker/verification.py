"""
ThreadSmith Verification Loop.
The core differentiator: resolving a ticket only counts if it survives the observation window.
"""
from datetime import datetime, timedelta, timezone
from loguru import logger
from database.models import db_resolutions, db_recurrence_events, db_stats

# Mock Redis TTL store
class MockRedis:
    def __init__(self):
        self.keys = {}
        
    def setex(self, key, ttl_seconds, value):
        expire_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self.keys[key] = {"value": value, "expire_at": expire_at}
        
    def check_expired(self, current_time):
        expired = []
        for k, v in list(self.keys.items()):
            if current_time >= v["expire_at"]:
                expired.append((k, v["value"]))
                del self.keys[k]
        return expired

redis_client = MockRedis()

def check_for_structural_recurrence(customer_id: str, new_issue_cluster_id: str, current_time: datetime) -> bool:
    """
    Checks if this new ticket cluster structurally matches any provisional resolutions 
    for this customer within their active window.
    """
    recurrence_detected = False
    
    # In prod, this is a Postgres query:
    # SELECT * FROM resolutions r JOIN tickets t ON r.ticket_id = t.ticket_id 
    # WHERE t.customer_id = customer_id AND r.issue_cluster_id = new_issue_cluster_id 
    # AND r.verification_status = 'provisional' AND r.verification_window_ends_at > current_time
    
    # Mock lookup
    for res_id, res in db_resolutions.items():
        if res.verification_status == "provisional" and res.issue_cluster_id == new_issue_cluster_id:
            # Matches! The 'fix' didn't hold.
            logger.warning(f"STRUCTURAL RECURRENCE DETECTED: Customer reopened issue matching cluster {new_issue_cluster_id}")
            recurrence_detected = True
            
            # Demote Resolution
            res.verification_status = "demoted"
            
            # Log Event
            db_recurrence_events[f"event_{res_id}"] = {
                "original_resolution_id": res_id,
                "detected_at": current_time
            }
            
            # Update Trust Score
            stat = db_stats.get(res.issue_cluster_id)
            if stat:
                stat.times_demoted += 1
                stat.current_trust_score = stat.times_verified / max(1, stat.times_applied)
                logger.info(f"Trust Score for {res.issue_cluster_id} plummeted to {stat.current_trust_score:.2f}")
                
    return recurrence_detected

def sweep_expired_provisional_windows(current_time: datetime):
    """
    Celery Beat background job.
    Finds provisional resolutions whose Redis TTL has expired without being demoted by a recurrence.
    """
    expired_keys = redis_client.check_expired(current_time)
    
    for key, res_id in expired_keys:
        res = db_resolutions.get(res_id)
        if res and res.verification_status == "provisional":
            logger.success(f"VERIFICATION PASSED: Resolution {res_id} survived observation window. Promoting.")
            res.verification_status = "verified"
            
            stat = db_stats.get(res.issue_cluster_id)
            if stat:
                stat.times_verified += 1
                stat.current_trust_score = stat.times_verified / max(1, stat.times_applied)
                logger.info(f"Trust Score for {res.issue_cluster_id} rose to {stat.current_trust_score:.2f}")
