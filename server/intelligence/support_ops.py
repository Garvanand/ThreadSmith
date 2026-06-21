"""
ThreadSmith Support Ops & Gaming Resistance Engine.
Provides statistical outlier detection for agent performance, tracks resolution drift,
and includes manual quarantine overrides for known system blind spots (e.g. silent churn).
"""
import math
import statistics
from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel
from loguru import logger

# --- DATA MODELS ---

class AgentPerformanceStat(BaseModel):
    agent_id: str
    total_provisional_closures: int
    total_verified_closures: int
    verification_rate: float

class GamingRiskReport(BaseModel):
    agent_id: str
    verification_rate: float
    org_baseline_rate: float
    z_score: float
    is_statistical_outlier: bool
    hypotheses: List[str]

class TrustDriftReport(BaseModel):
    issue_cluster_id: str
    resolution_template_id: str
    lifetime_verification_rate: float
    recent_verification_rate_last_30d: float
    is_drifting: bool
    recommended_action: str

# Mocks
QUARANTINED_PATTERNS = set()

# --- PART A: AGENT GAMING DETECTION ---

def detect_agent_gaming_pattern(target_agent_id: str, all_agents_stats: List[AgentPerformanceStat]) -> Optional[GamingRiskReport]:
    """
    Computes if an agent's verification rate is a statistical outlier on the low side
    relative to the organizational baseline using a z-score.
    
    IMPORTANT: This flag is a prompt for a human support-ops conversation, 
    NEVER grounds for automated punitive action against the agent.
    """
    if not all_agents_stats:
        return None
        
    rates = [stat.verification_rate for stat in all_agents_stats]
    org_baseline = statistics.mean(rates)
    
    # Avoid division by zero if all agents have identical rates
    stdev = statistics.stdev(rates) if len(rates) > 1 and statistics.stdev(rates) > 0 else 0.01
    
    target_stat = next((s for s in all_agents_stats if s.agent_id == target_agent_id), None)
    if not target_stat:
        return None
        
    z_score = (target_stat.verification_rate - org_baseline) / stdev
    
    # Flag if they are more than 1.5 standard deviations BELOW the mean
    is_outlier = z_score < -1.5
    
    hypotheses = []
    if is_outlier:
        hypotheses = [
            "HYPOTHESIS A (Gaming/Carelessness): The agent is rapidly closing tickets with generic/unhelpful macros to hit closure-volume KPIs, causing customers to repeatedly reopen tickets.",
            "HYPOTHESIS B (High-Skill Assignment): The agent is assigned to the most complex, novel, or deeply technical escalation queues where resolutions are naturally harder to verify on the first attempt. This is a sign of trust and skill, not failure."
        ]
        
    report = GamingRiskReport(
        agent_id=target_agent_id,
        verification_rate=target_stat.verification_rate,
        org_baseline_rate=org_baseline,
        z_score=z_score,
        is_statistical_outlier=is_outlier,
        hypotheses=hypotheses
    )
    
    if is_outlier:
        logger.warning(f"GAMING ALERT: Agent {target_agent_id} flagged (Z-Score: {z_score:.2f}). Please review hypotheses.")
        
    return report

# --- PART B: TRUST SCORE DRIFT AUDIT ---

def audit_trust_score_drift(
    issue_cluster_id: str, 
    resolution_template_id: str, 
    lifetime_successes: int, 
    lifetime_total: int, 
    recent_successes: int, 
    recent_total: int
) -> TrustDriftReport:
    """
    Detects when a previously highly-trusted pattern stops working recently.
    This triggers a distinct alert from agent-gaming, because it usually indicates
    the underlying product has changed, breaking the old fix.
    """
    lifetime_rate = (lifetime_successes / lifetime_total) if lifetime_total > 0 else 0.0
    recent_rate = (recent_successes / recent_total) if recent_total > 0 else 0.0
    
    # Define drift: Lifetime rate was high (>0.80), but recent rate has dropped significantly (>0.20 drop)
    is_drifting = lifetime_rate > 0.80 and (lifetime_rate - recent_rate) > 0.20 and recent_total >= 5
    
    action = "Monitor"
    if is_drifting:
        action = "ALERT: A previously highly-effective fix is failing rapidly. A recent product update likely broke this resolution. Suspend macro and investigate product changes."
        logger.error(f"DRIFT ALERT: Template {resolution_template_id} for cluster {issue_cluster_id} dropped from {lifetime_rate:.2f} to {recent_rate:.2f} recently.")
        
    return TrustDriftReport(
        issue_cluster_id=issue_cluster_id,
        resolution_template_id=resolution_template_id,
        lifetime_verification_rate=lifetime_rate,
        recent_verification_rate_last_30d=recent_rate,
        is_drifting=is_drifting,
        recommended_action=action
    )

# --- PART C: QUARANTINE & THE SILENT CHURN BLIND SPOT ---

def quarantine_resolution_pattern(resolution_template_id: str, reason: str):
    """
    Immediately and reversibly removes a pattern from active suggestion without 
    waiting for the verification cycle to demote it algorithmically.
    
    KNOWN LIMITATION / BLIND SPOT: "Silent Churn"
    The verification loop uses "customer did not reopen a ticket" as a proxy for "the problem is solved". 
    If a resolution pattern is terrible (e.g., aggressively dismissive), the customer might just give up 
    and cancel their account (churn) rather than reopening the ticket. 
    The algorithmic verification loop will incorrectly see this as a "verified" success.
    
    This function allows human supervisors who catch these cases via sentiment analysis or churn tracking 
    to manually override the algorithm and quarantine the bad pattern.
    """
    logger.critical(f"QUARANTINE EXECUTED: Pattern {resolution_template_id} isolated. Reason: {reason}")
    # In the suggestion engine, we would check: `if template_id in QUARANTINED_PATTERNS: skip()`
    QUARANTINED_PATTERNS.add(resolution_template_id)
    return True

# --- EXECUTIONS ---
if __name__ == "__main__":
    print("\n--- ThreadSmith Support Ops Engine ---")
    
    # 1. Agent Gaming Detection
    print("\n[Testing Agent Gaming Detection]")
    mock_agents = [
        AgentPerformanceStat(agent_id="agt_sarah", total_provisional_closures=100, total_verified_closures=85, verification_rate=0.85),
        AgentPerformanceStat(agent_id="agt_mike", total_provisional_closures=100, total_verified_closures=82, verification_rate=0.82),
        AgentPerformanceStat(agent_id="agt_john", total_provisional_closures=100, total_verified_closures=80, verification_rate=0.80),
        # Outlier
        AgentPerformanceStat(agent_id="agt_gaming", total_provisional_closures=150, total_verified_closures=60, verification_rate=0.40),
    ]
    
    report = detect_agent_gaming_pattern("agt_gaming", mock_agents)
    if report and report.is_statistical_outlier:
        print(f"Flagged Agent {report.agent_id} | Z-Score: {report.z_score:.2f}")
        for hyp in report.hypotheses:
            print(f" -> {hyp}")
            
    # 2. Trust Score Drift
    print("\n[Testing Trust Score Drift]")
    # 38/40 lifetime (95%), but recently 1/6 (16%)
    drift_report = audit_trust_score_drift("c_api", "tpl_api_key", lifetime_successes=38, lifetime_total=40, recent_successes=1, recent_total=6)
    print(f"Drift Detected: {drift_report.is_drifting}")
    print(f"Action: {drift_report.recommended_action}")
    
    # 3. Quarantine & Silent Churn
    print("\n[Testing Quarantine (Silent Churn Blind Spot)]")
    quarantine_resolution_pattern(
        resolution_template_id="tpl_dismissive_macro", 
        reason="Manual supervisor override. Customers are churning instead of replying, falsely inflating the verification rate."
    )
