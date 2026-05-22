"""Signal handlers that keep MemberProfile.current_load in sync with reality.

`current_load` is recomputed from live Request rows whenever a Request is
saved or deleted, so it can never drift from the true active-assignment count.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from core.models import Request
from core.assignment import recalculate_member_load


@receiver(post_save, sender=Request)
def sync_load_on_request_save(sender, instance, **kwargs):
    """Recompute load for the current assignee and, on re-assignment, the
    previous assignee captured by Request.__init__."""
    affected = set()
    if instance.assigned_to_id:
        affected.add(instance.assigned_to_id)
    original_id = getattr(instance, '_original_assigned_to_id', None)
    if original_id:
        affected.add(original_id)
    for member_id in affected:
        recalculate_member_load(member_id)
    # Re-baseline the snapshot for any subsequent save on this instance.
    instance._original_assigned_to_id = instance.assigned_to_id


@receiver(post_delete, sender=Request)
def sync_load_on_request_delete(sender, instance, **kwargs):
    if instance.assigned_to_id:
        recalculate_member_load(instance.assigned_to_id)
