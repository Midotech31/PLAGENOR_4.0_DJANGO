"""Backfill MemberProfile state introduced by the H2/H5 fixes.

H5 — make sure every existing analyst (User.role == 'MEMBER') owns a
     MemberProfile, mirroring the new accounts.signals behaviour for new users.
H2 — recompute MemberProfile.current_load from live Request rows. The field
     existed but was never written, so every row is at the default 0.
"""
from django.db import migrations


LOAD_EXCLUDED_STATES = ['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED']


def backfill(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    MemberProfile = apps.get_model('accounts', 'MemberProfile')
    Request = apps.get_model('core', 'Request')

    # H5: ensure every analyst has a profile.
    for user in User.objects.filter(role='MEMBER'):
        MemberProfile.objects.get_or_create(user=user)

    # H2: recompute current_load from active assignments.
    for mp in MemberProfile.objects.all():
        count = Request.objects.filter(assigned_to=mp).exclude(
            status__in=LOAD_EXCLUDED_STATES
        ).count()
        if mp.current_load != count:
            mp.current_load = count
            mp.save(update_fields=['current_load'])


def noop(apps, schema_editor):
    """Reverse: leave data alone — current_load just resumes drift if the
    new signals are removed, which is the original behaviour."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_must_change_password'),
        ('core', '0010_alter_request_service_rating_alter_request_status_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
