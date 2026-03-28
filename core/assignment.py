# core/assignment.py — PLAGENOR 4.0 Assignment Engine (Django ORM)
# score = (skill × w) − (load × w) − availability_penalty + productivity_score

from __future__ import annotations

from accounts.models import MemberProfile
from core.models import Request


# Weights matching the Streamlit config
ASSIGNMENT_WEIGHTS = {
    'skill': 40,
    'load': 30,
    'productivity': 20,
    'availability': 10,
}
DEFAULT_MAX_LOAD = 5


def compute_member_score(member_profile: MemberProfile, service=None) -> float:
    """Compute assignment score for a member profile."""
    weights = ASSIGNMENT_WEIGHTS
    max_load = member_profile.max_load or DEFAULT_MAX_LOAD
    current_load = member_profile.current_load

    # Skill score (0-100) — cross-reference member techniques with service
    skill_score = 50.0  # default if no service
    if service:
        member_techniques = list(member_profile.techniques.values_list('name', flat=True))
        if member_techniques:
            # Check if any technique matches service code or name
            service_code = getattr(service, 'code', '')
            service_name = getattr(service, 'name', '')
            matched = any(
                service_code.lower() in t.lower() or t.lower() in service_code.lower()
                or service_name.lower() in t.lower()
                for t in member_techniques
            )
            skill_score = 100.0 if matched else 30.0
        else:
            skill_score = 0.0

    # Load score (0-100, inverted: lower load = higher score)
    if max_load > 0:
        load_ratio = current_load / max_load
        load_score = max(0, (1 - load_ratio)) * 100
    else:
        load_score = 0.0

    # Availability penalty
    availability_penalty = 0 if member_profile.available else 50

    # Productivity score
    prod_score = member_profile.productivity_score or 50.0

    # Weighted calculation
    score = (
        skill_score * (weights['skill'] / 100)
        + load_score * (weights['load'] / 100)
        + prod_score * (weights['productivity'] / 100)
        - availability_penalty * (weights['availability'] / 100)
    )

    return round(max(0, min(100, score)), 1)


def get_recommended_members(service=None, limit: int = 5) -> list:
    """Get recommended members sorted by assignment score."""
    members = MemberProfile.objects.filter(
        available=True,
    ).select_related('user').prefetch_related('techniques')

    scored = []
    for m in members:
        if m.current_load >= (m.max_load or DEFAULT_MAX_LOAD):
            continue
        m._score = compute_member_score(m, service)
        scored.append(m)

    scored.sort(key=lambda x: x._score, reverse=True)
    return scored[:limit]


def get_member_workload(member_profile: MemberProfile) -> dict:
    """Get workload stats for a member."""
    active = Request.objects.filter(
        assigned_to=member_profile,
    ).exclude(status__in=['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED']).count()

    max_load = member_profile.max_load or DEFAULT_MAX_LOAD
    return {
        'member_id': member_profile.pk,
        'name': member_profile.user.get_full_name(),
        'current_load': member_profile.current_load,
        'max_load': max_load,
        'active_requests': active,
        'available': member_profile.available,
        'utilization': round(member_profile.current_load / max(1, max_load) * 100, 1),
    }
