"""Synthetic scientific assignment fixtures, restricted to the isolated browser DB."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from accounts.models import Technique, User
from core.ibtikar.models import IbtikarSubmission
from core.models import Request, Service


def seed():
    if settings.SETTINGS_MODULE != 'plagenor.settings_e2e':
        raise ImproperlyConfigured('Assignment browser fixtures require isolated E2E settings.')
    service = Service.objects.get(code='EGTP-IMT')
    technique, _ = Technique.objects.get_or_create(name_fr='MALDI-TOF')
    for project in ('chromium', 'firefox', 'mobile-chromium'):
        for language in ('fr', 'en', 'ar'):
            identifier = f'{project}-{language}'
            member = User.objects.create_user('assignment-' + identifier, role='MEMBER',
                                             first_name='Synthetic', last_name=identifier).member_profile
            member.techniques.add(technique)
            req = Request.objects.create(display_id='E2E-ASSIGN-' + identifier, channel='IBTIKAR',
                                          status='IBTIKAR_CODE_SUBMITTED', service=service,
                                          title='Assignment ' + identifier, ibtikar_external_code='SYNTHETIC-CODE')
            IbtikarSubmission.objects.create(request=req, submitted_at=timezone.now(), estimate={'total': 2500})
