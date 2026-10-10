# core/assignment.py — PLAGENOR 4.0 Assignment Engine (Django ORM)
# score = (skill × w) − (load × w) − availability_penalty + productivity_score

from __future__ import annotations

import re
import unicodedata

from django.utils.translation import gettext as _

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


def _label_tokens(value):
    """Compare whole words, ignoring accents and punctuation, never empty text."""
    value = unicodedata.normalize('NFKD', value or '').casefold()
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return tuple(re.findall(r'[^\W_]+', value))


def _label_variants(obj):
    # Explicit translated fields make qualification independent of UI language.
    return {_label_tokens(getattr(obj, field, '')) for field in
            ('name', 'name_fr', 'name_en', 'name_ar')} - {()}


def _contains_phrase(label, phrase):
    return bool(phrase) and any(
        label[index:index + len(phrase)] == phrase
        for index in range(len(label) - len(phrase) + 1))


def technique_matches_service(technique, service):
    """Match an active certification to a service code or complete name phrase."""
    if not technique.active:
        return False
    code = _label_tokens(service.code)
    service_names = _label_variants(service)
    for label in _label_variants(technique):
        if _contains_phrase(label, code):
            return True
        if any(_contains_phrase(name, label) or _contains_phrase(label, name)
               for name in service_names):
            return True
    return False


def member_ineligibility_reasons(member_profile: MemberProfile, service=None, current_request=None) -> list:
    """Explain every blocking criterion using the same rules as assignment."""
    reasons = []
    if not member_profile.user.is_active:
        reasons.append(_('Compte désactivé.'))
    if member_profile.user.role != 'MEMBER':
        reasons.append(_('Ce compte n’a pas le rôle analyste.'))
    if not member_profile.available:
        reasons.append(_('Analyste indisponible.'))
    keeps_existing_slot = (current_request is not None
                           and current_request.assigned_to_id == member_profile.pk
                           and current_request.status not in LOAD_EXCLUDED_STATES)
    if not keeps_existing_slot and member_profile.current_load >= (member_profile.max_load or DEFAULT_MAX_LOAD):
        reasons.append(_('Capacité atteinte (%(load)s/%(capacity)s).') % {
            'load': member_profile.current_load,
            'capacity': member_profile.max_load or DEFAULT_MAX_LOAD})
    if service is not None and not any(
            technique_matches_service(technique, service)
            for technique in member_profile.techniques.all()):
        reasons.append(_('Aucune technique active correspondant à ce service.'))
    return reasons


def member_is_eligible(member_profile: MemberProfile, service=None) -> bool:
    """Return whether a member may be assigned, not merely how they rank."""
    return not member_ineligibility_reasons(member_profile, service)


def get_assignment_candidates(service=None, current_member_id=None, members=None, current_request=None):
    """Include blocked candidates so operators can see what needs correcting."""
    if members is None:
        members = MemberProfile.objects.select_related('user').prefetch_related('techniques').order_by(
            'user__last_name', 'user__first_name', 'pk')
    return [{'member': member, 'reasons': member_ineligibility_reasons(member, service, current_request)}
            for member in members if member.pk != current_member_id]


def compute_member_score(member_profile: MemberProfile, service=None) -> float:
    """Compute assignment score for a member profile."""
    weights = ASSIGNMENT_WEIGHTS
    max_load = member_profile.max_load or DEFAULT_MAX_LOAD
    current_load = member_profile.current_load

    # Skill score (0-100) — cross-reference member techniques with service
    skill_score = 50.0  # default if no service
    if service:
        member_techniques = [t for t in member_profile.techniques.all() if t.active]
        if member_techniques:
            matched = any(technique_matches_service(t, service) for t in member_techniques)
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
    prod_score = member_profile.productivity_score
    if prod_score is None:
        prod_score = 50.0

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
        if not member_is_eligible(m, service):
            continue
        m._score = compute_member_score(m, service)
        scored.append(m)

    scored.sort(key=lambda x: x._score, reverse=True)
    return scored[:limit]


# An assigned request stops counting toward a member's load once it reaches
# one of these terminal/closed states.
LOAD_EXCLUDED_STATES = ['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED']


def recalculate_member_load(member_profile) -> int:
    """Recompute and persist a member's `current_load` from live Request rows.

    Recompute-from-source (instead of increment/decrement) guarantees the
    counter can never drift. Accepts a MemberProfile instance or a pk.
    """
    if member_profile is None:
        return 0
    mp = member_profile
    if not isinstance(mp, MemberProfile):
        mp = MemberProfile.objects.filter(pk=member_profile).first()
        if mp is None:
            return 0
    count = Request.objects.filter(assigned_to=mp).exclude(
        status__in=LOAD_EXCLUDED_STATES
    ).count()
    if mp.current_load != count:
        mp.current_load = count
        mp.save(update_fields=['current_load'])
    return count


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
