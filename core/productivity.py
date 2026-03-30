# core/productivity.py — PLAGENOR 4.0 Productivity Engine (Django ORM)

from __future__ import annotations

from accounts.models import MemberProfile
from core.models import Request

# SLA defaults (days)
SLA_DAYS_IBTIKAR = 30
SLA_DAYS_GENOCLAB = 21

# Score thresholds
SCORE_EXCELLENT = 85
SCORE_GOOD = 70
SCORE_NORMAL = 50

PERFORMANCE_LEVELS = [
    {'key': 'fire', 'emoji': '\U0001f525', 'label_fr': 'Le plus rapide', 'label_en': 'Fastest', 'min_score': 90},
    {'key': 'very_good', 'emoji': '\u2b50', 'label_fr': 'Très bien', 'label_en': 'Very Good', 'min_score': 75},
    {'key': 'good', 'emoji': '\U0001f44d', 'label_fr': 'Bien', 'label_en': 'Good', 'min_score': 60},
    {'key': 'not_bad', 'emoji': '\U0001f642', 'label_fr': 'Pas mal', 'label_en': 'Not Bad', 'min_score': 0},
]

PRODUCTIVITY_EMOJI = {
    'EXCELLENT': '\U0001f525',
    'GOOD': '\u2b50',
    'NORMAL': '\U0001f44d',
    'LOW': '\U0001f642',
}


def get_performance_level(score: float) -> dict:
    for level in PERFORMANCE_LEVELS:
        if score >= level['min_score']:
            return level
    return PERFORMANCE_LEVELS[-1]


def get_productivity_status(score: float) -> str:
    if score >= SCORE_EXCELLENT:
        return 'EXCELLENT'
    elif score >= SCORE_GOOD:
        return 'GOOD'
    elif score >= SCORE_NORMAL:
        return 'NORMAL'
    return 'LOW'


def compute_member_productivity(member_profile: MemberProfile) -> dict:
    """Compute productivity metrics for a member."""
    assigned = Request.objects.filter(assigned_to=member_profile)
    total = assigned.count()
    completed_qs = assigned.filter(status='COMPLETED')
    completed = completed_qs.count()
    in_progress = assigned.filter(
        status__in=['ANALYSIS_STARTED', 'ANALYSIS_FINISHED', 'SAMPLE_RECEIVED']
    ).count()

    completion_rate = (completed / total * 100) if total > 0 else 50.0

    # On-time rate
    on_time = 0
    for r in completed_qs.iterator():
        sla = SLA_DAYS_IBTIKAR if r.channel == 'IBTIKAR' else SLA_DAYS_GENOCLAB
        days = (r.updated_at - r.created_at).days
        if days <= sla:
            on_time += 1

    on_time_rate = (on_time / completed * 100) if completed else 50.0

    score = round(completion_rate * 0.6 + on_time_rate * 0.4, 1)
    score = max(0, min(100, score))

    status = get_productivity_status(score)

    return {
        'member_id': member_profile.pk,
        'total_assigned': total,
        'completed': completed,
        'in_progress': in_progress,
        'completion_rate': round(completion_rate, 1),
        'on_time_rate': round(on_time_rate, 1),
        'score': score,
        'status': status,
        'level': get_performance_level(score),
        'emoji': PRODUCTIVITY_EMOJI.get(status, '\u26aa'),
    }


def recalculate_member(member_profile: MemberProfile) -> dict:
    """Recalculate and save productivity for a single member."""
    metrics = compute_member_productivity(member_profile)
    member_profile.productivity_score = metrics['score']
    member_profile.productivity_status = metrics['status']
    member_profile.save(update_fields=['productivity_score', 'productivity_status'])
    return metrics


def recalculate_all() -> list:
    """Recalculate productivity for all members."""
    results = []
    for mp in MemberProfile.objects.all():
        r = recalculate_member(mp)
        results.append(r)
    return results


def get_all_productivity_stats() -> list:
    """Get productivity stats for all members (dashboard display)."""
    results = []
    for mp in MemberProfile.objects.select_related('user').all():
        metrics = compute_member_productivity(mp)
        metrics['name'] = mp.user.get_full_name()
        results.append(metrics)
    return results
