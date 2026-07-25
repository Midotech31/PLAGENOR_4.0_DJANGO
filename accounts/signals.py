"""Account signal handlers."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User, MemberProfile


@receiver(post_save, sender=User)
def ensure_member_profile(sender, instance, **kwargs):
    """Every analyst (role == 'MEMBER') must own a MemberProfile.

    Guarantees the profile exists no matter how the user was created or had
    their role changed, so analyst views never hit RelatedObjectDoesNotExist.
    """
    if instance.role == 'MEMBER':
        MemberProfile.objects.get_or_create(user=instance)
