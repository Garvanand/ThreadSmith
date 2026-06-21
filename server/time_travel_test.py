"""
Time-Travel Test Harness for ThreadSmith Verification Loop.
Simulates days passing to prove the promotion/demotion engine works.
"""
from datetime import datetime, timedelta, timezone
from database.models import Resolution, ResolutionPatternStats, db_resolutions, db_stats
from worker.verification import redis_client, check_for_structural_recurrence, sweep_expired_provisional_windows

def run_time_travel_test():
    print("\n--- ThreadSmith Time-Travel Verification Test ---")
    
    t0 = datetime.now(timezone.utc)
    
    # 1. Setup: Agent applies a 'fix' to a technical issue.
    # Tiered window: Technical issues get 7 days.
    res_id_1 = "res_001_tech"
    cluster_tech = "cluster_tech_api_failure"
    
    db_resolutions[res_id_1] = Resolution(
        resolution_id=res_id_1,
        ticket_id="ticket_1",
        issue_cluster_id=cluster_tech,
        resolution_text="Reset API key cache.",
        applied_by_agent_id="agent_smith",
        applied_at=t0,
        verification_status="provisional",
        verification_window_ends_at=t0 + timedelta(days=7)
    )
    
    db_stats[cluster_tech] = ResolutionPatternStats(
        issue_cluster_id=cluster_tech,
        resolution_template_id="macro_reset_cache",
        times_applied=1
    )
    
    redis_client.setex(f"obs_window_{res_id_1}", 7 * 86400, res_id_1)
    
    print(f"[{t0.strftime('%Y-%m-%d')}] Agent applied fix to {cluster_tech}. Status: PROVISIONAL. Window: 7 days.")
    
    # 2. Time Travel: 3 days pass. Customer opens a NEW ticket about the SAME structural issue.
    t_plus_3 = t0 + timedelta(days=3)
    print(f"\n[{t_plus_3.strftime('%Y-%m-%d')}] Customer submits new ticket: 'The API is broken again'")
    
    # The pipeline classifies it and hits the recurrence checker
    check_for_structural_recurrence("cust_123", cluster_tech, t_plus_3)
    
    print(f"Status of Resolution 1: {db_resolutions[res_id_1].verification_status}")
    
    # 3. Setup: Informational Issue (Password reset).
    # Tiered window: 72 hours.
    res_id_2 = "res_002_info"
    cluster_info = "cluster_info_password"
    
    db_resolutions[res_id_2] = Resolution(
        resolution_id=res_id_2,
        ticket_id="ticket_2",
        issue_cluster_id=cluster_info,
        resolution_text="Sent password reset link.",
        applied_by_agent_id="agent_smith",
        applied_at=t_plus_3,
        verification_status="provisional",
        verification_window_ends_at=t_plus_3 + timedelta(days=3)
    )
    
    db_stats[cluster_info] = ResolutionPatternStats(
        issue_cluster_id=cluster_info,
        resolution_template_id="macro_send_pw_link",
        times_applied=1
    )
    
    redis_client.setex(f"obs_window_{res_id_2}", 3 * 86400, res_id_2)
    print(f"\n[{t_plus_3.strftime('%Y-%m-%d')}] Agent applied fix to {cluster_info}. Status: PROVISIONAL. Window: 3 days.")
    
    # 4. Time Travel: Fast forward 4 days (Total 7 days from start).
    # The informational ticket had a 3-day window, so it should be expired safely.
    t_plus_7 = t0 + timedelta(days=7, hours=1)
    print(f"\n[{t_plus_7.strftime('%Y-%m-%d')}] Celery Beat Sweep executing...")
    
    sweep_expired_provisional_windows(t_plus_7)
    
    print(f"Status of Resolution 2: {db_resolutions[res_id_2].verification_status}")

if __name__ == "__main__":
    run_time_travel_test()
