"""
ThreadSmith Test Suite
Covers the core intelligence nodes, the Verification Loop, and AgentOS integrations.
"""
import sys
import os
import pytest
from datetime import datetime, timedelta, timezone

# Ensure we can import from server
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))

from intelligence.advanced_classifier import (
    extract_issue_structure, match_or_create_issue_cluster, evaluate_cluster_cohesion,
    IssueStructure, IssueCluster
)
from worker.advanced_verification import (
    log_provisional_resolution, check_for_recurrence, resolve_verification_window, 
    compute_trust_score, db_resolutions, db_tickets, db_stats, Ticket, ResolutionPatternStats
)
from intelligence.suggestion_engine import check_auto_resolution_eligibility
from api.agentos_client import build_customer_context

# --- FIXTURES ---
@pytest.fixture(autouse=True)
def reset_mock_dbs():
    db_resolutions.clear()
    db_tickets.clear()
    db_stats.clear()

@pytest.fixture
def time_travel_current_time():
    """Simulates the current execution time moving forward."""
    return datetime.now(timezone.utc)

# --- 1. CLASSIFICATION & CLUSTERING ---
def test_root_cause_disambiguation():
    """Verify that similar symptoms (login fails) but different root causes (SSO vs Password) are NOT clustered."""
    existing_cluster = IssueCluster(
        cluster_id="c_sso", representative_description="SSO Integration Down", 
        embedding=[0.0], ticket_count=50, resolution_verification_rate=0.85
    )
    new_issue = IssueStructure(
        normalized_problem_statement="password_reset_login_failure",
        affected_entities={}, severity_signal="medium", prior_resolution_attempts=[]
    )
    # The mock Anthropic handler explicitly rejects SSO vs Password merges
    match_result = match_or_create_issue_cluster(new_issue, [existing_cluster])
    assert match_result.match_type == "new_cluster"
    assert match_result.cluster_id != "c_sso"

def test_cluster_cohesion_split():
    """Verify that a contaminated cluster is split correctly."""
    bad_cluster = IssueCluster(
        cluster_id="c_mixed", representative_description="Generic Login Failures",
        embedding=[0.0], ticket_count=100, resolution_verification_rate=0.20
    )
    tickets = ["I can't login via okta", "forgot my password"]
    report = evaluate_cluster_cohesion(bad_cluster, tickets)
    
    assert report is not None
    assert report.is_contaminated is True
    assert len(report.proposed_split_clusters) == 2
    assert report.proposed_split_clusters[0]["new_cluster_id"] == "c_sso"
    assert report.proposed_split_clusters[1]["new_cluster_id"] == "c_pw"

# --- 2. VERIFICATION WINDOW LOGIC ---
def test_verification_promotion(time_travel_current_time):
    """Clean promotion after window expires with no recurrence."""
    t0 = time_travel_current_time
    # Informational tickets get 3-day windows
    res = log_provisional_resolution("t1", "Fix", "tpl1", "agt1", "c_info", "Informational", t0)
    
    t_plus_4_days = t0 + timedelta(days=4)
    resolve_verification_window(t_plus_4_days)
    
    # Should be promoted
    assert db_resolutions[res.resolution_id].verification_status == "verified"
    assert db_stats["c_info"].times_verified == 1

def test_verification_true_demotion(time_travel_current_time):
    """True demotion when the same structural issue recurs."""
    t0 = time_travel_current_time
    db_tickets["t_bug"] = Ticket(ticket_id="t_bug", customer_id="c1", issue_cluster_id="c_bug", opened_at=t0)
    res = log_provisional_resolution("t_bug", "Restart server", "tpl1", "agt1", "c_bug", "Technical_Bug", t0)
    
    # Recurrence 2 days later
    db_tickets["t_recur"] = Ticket(ticket_id="t_recur", customer_id="c1", issue_cluster_id="c_bug", opened_at=t0 + timedelta(days=2))
    
    resolve_verification_window(t0 + timedelta(days=15)) # Fast forward past the 14-day window
    
    assert db_resolutions[res.resolution_id].verification_status == "demoted"
    assert db_resolutions[res.resolution_id].demotion_reason == "resolution_failed_to_hold"

def test_verification_false_demotion(time_travel_current_time):
    """Misclassification demotion routes to cohesion review instead of penalizing."""
    t0 = time_travel_current_time
    db_tickets["t_mis"] = Ticket(ticket_id="t_mis", customer_id="c1", issue_cluster_id="c_mis", opened_at=t0)
    res = log_provisional_resolution("t_mis", "Fixed billing", "tpl1", "agt1", "c_mis", "Informational", t0)
    
    # Recurrence, but text explicitly indicates it's unrelated
    t_recur = Ticket(ticket_id="t_recur", customer_id="c1", issue_cluster_id="c_mis", opened_at=t0 + timedelta(days=1))
    t_recur.raw_text = "unrelated"
    db_tickets["t_recur"] = t_recur
    
    resolve_verification_window(t0 + timedelta(days=4))
    
    assert db_resolutions[res.resolution_id].verification_status == "demoted"
    assert db_resolutions[res.resolution_id].demotion_reason == "cluster_contamination_detected"
    assert db_stats["c_mis"].times_demoted == 0 # NO penalty applied

# --- 3. TRUST SCORE COMPUTATION (Wilson Score) ---
def test_trust_score_computation():
    """Verify Wilson score logic: 2/2 should not outrank 38/40."""
    s_small = ResolutionPatternStats(issue_cluster_id="c1", resolution_template_id="t1", times_verified=2, times_demoted=0)
    s_large = ResolutionPatternStats(issue_cluster_id="c2", resolution_template_id="t2", times_verified=38, times_demoted=2)
    
    score_small = compute_trust_score(s_small)
    score_large = compute_trust_score(s_large)
    
    # 2/2 is 100% ratio, but Wilson lower bound is ~0.34
    # 38/40 is 95% ratio, but Wilson lower bound is ~0.83
    assert score_large > score_small
    assert round(score_small, 2) == 0.34
    assert round(score_large, 2) == 0.83

# --- 4. SCOPED AUTO-RESOLUTION GATING ---
def test_auto_resolution_gates():
    """Verify failing closed across near-miss thresholds."""
    # Allowlist categories: Account_Access, Informational, Order_Status
    # Thresholds: Score > 0.85, Sample > 20
    
    # 1. High trust, low sample size -> FAIL
    stat1 = ResolutionPatternStats(issue_cluster_id="c1", resolution_template_id="t1", current_trust_score=0.90, times_verified=5)
    assert not check_auto_resolution_eligibility("t1", "c1", "Account_Access", stat1).is_eligible
    
    # 2. High sample size, trust just below threshold -> FAIL
    stat2 = ResolutionPatternStats(issue_cluster_id="c2", resolution_template_id="t2", current_trust_score=0.84, times_verified=50)
    assert not check_auto_resolution_eligibility("t2", "c2", "Account_Access", stat2).is_eligible
    
    # 3. High trust & sample size, NOT on allowlist -> FAIL
    stat3 = ResolutionPatternStats(issue_cluster_id="c3", resolution_template_id="t3", current_trust_score=0.95, times_verified=50)
    assert not check_auto_resolution_eligibility("t3", "c3", "Technical_Bug", stat3).is_eligible
    
    # 4. Perfect Candidate -> PASS
    assert check_auto_resolution_eligibility("t4", "c4", "Account_Access", stat3).is_eligible

# --- 5. GRACEFUL DEGRADATION ---
def test_cross_agent_degradation():
    """Verify robust handling of cross-agent integration timeouts."""
    res = build_customer_context("cust_timeout", needs_contract=True, contract_topic="refund")
    assert res.partial_context is True
    assert res.context == {}
    
    # Verify healthy path
    res_healthy = build_customer_context("cust_healthy")
    assert res_healthy.partial_context is False
    assert res_healthy.context["ghostcfo"]["status"] == "HEALTHY"
