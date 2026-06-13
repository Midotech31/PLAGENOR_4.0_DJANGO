"""Seed a single demo IBTIKAR request, already assigned to the demo analyst.

Useful for end-to-end UI walkthroughs: instead of going through
registration → declaration → submission → admin validation → assignment
in five separate browser sessions, this command stages a request in the
exact state where the analyst's "Tâches en attente" tab lights up.

Idempotent. Re-running:
  * re-creates the demo requester / analyst if seed_accounts wasn't run
  * sets the requester's declared IBTIKAR balance so the cap-check passes
  * removes any previous seeded demo request (display_id starts with
    'IBT-DEMO-') and creates a fresh one

Usage:
  python manage.py seed_demo_request                  # default: ASSIGNED
  python manage.py seed_demo_request --status REPORT_UPLOADED
  python manage.py seed_demo_request --service EGTP-PCR

After running, log in as ``analyst`` / ``analyst1234`` to see the task,
or as ``amina`` / ``demo1234`` to see it from the requester side.
"""
from datetime import datetime
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User, MemberProfile
from core.models import Request, RequestHistory, Service
from core.sequences import next_display_id
from notifications.models import Notification


# Status presets that walk the request to a meaningful state. Each key
# applies the previous one's setup and then adds its own — declared as a
# flat list so the management command stays simple.
PRESET_FIELDS = {
    'ASSIGNED': dict(
        assignment_accepted=False,
    ),
    'APPOINTMENT_PROPOSED': dict(
        assignment_accepted=True,
        appointment_date=None,
    ),
    'APPOINTMENT_CONFIRMED': dict(
        assignment_accepted=True,
        appointment_confirmed=True,
    ),
    'SAMPLE_RECEIVED': dict(
        assignment_accepted=True,
        appointment_confirmed=True,
    ),
    'ANALYSIS_STARTED': dict(
        assignment_accepted=True,
        appointment_confirmed=True,
    ),
    'ANALYSIS_FINISHED': dict(
        assignment_accepted=True,
        appointment_confirmed=True,
    ),
    'REPORT_UPLOADED': dict(
        assignment_accepted=True,
        appointment_confirmed=True,
    ),
    'SENT_TO_REQUESTER': dict(
        assignment_accepted=True,
        appointment_confirmed=True,
        report_delivered=False,
    ),
}


class Command(BaseCommand):
    help = "Create a demo IBTIKAR request assigned to the analyst for E2E testing."

    def add_arguments(self, parser):
        parser.add_argument(
            '--status', default='ASSIGNED', choices=list(PRESET_FIELDS),
            help="Target status for the seeded request (default: ASSIGNED).",
        )
        parser.add_argument(
            '--service', default=None,
            help="Service code to use (e.g. EGTP-PCR). Default: the first active service.",
        )
        parser.add_argument(
            '--balance', type=int, default=180000,
            help="Declared IBTIKAR balance for the demo requester (default: 180000).",
        )

    def handle(self, *args, **options):
        target_status = options['status']
        balance = options['balance']

        requester = self._ensure_requester(balance)
        analyst_profile = self._ensure_analyst()
        service = self._ensure_service(options.get('service'))

        # Clear any previously seeded demo request so reruns stay clean.
        deleted = Request.objects.filter(display_id__startswith='IBT-DEMO-').delete()
        if deleted[0]:
            self.stdout.write(f"  Cleaned {deleted[0]} previous demo request(s).")

        # Allocate a sequential display_id under a dedicated DEMO prefix so
        # the seeded row never clashes with real IBT-YYYY-NNNN numbering.
        year = datetime.now().year
        display_id = next_display_id(
            'IBT-DEMO', year,
            initial_value_fn=lambda: 0,
        )

        # Resolve the cost so budget_amount matches a real submission. We
        # use the same canonical resolver the requester form uses.
        from core.pricing import resolve_cost
        price_result = resolve_cost(
            service, 'IBTIKAR',
            sample_table=[{'sample_id': 'DEMO-S1', 'source': 'isolat clinique'}],
            service_params={'pathogenic': False, 'analysis_mode': 'Simple'},
            urgency='Normal',
        )
        budget_amount = float(price_result.get('total') or service.ibtikar_price or 5000)

        extras = PRESET_FIELDS[target_status].copy()
        if target_status == 'APPOINTMENT_CONFIRMED' or target_status in (
            'SAMPLE_RECEIVED', 'ANALYSIS_STARTED', 'ANALYSIS_FINISHED',
            'REPORT_UPLOADED', 'SENT_TO_REQUESTER',
        ):
            # Park a confirmed RDV three days out so the timeline looks real
            extras['appointment_date'] = (timezone.now() + timezone.timedelta(days=3)).date()
            extras['appointment_confirmed_at'] = timezone.now()
        if target_status in ('ASSIGNED', 'APPOINTMENT_PROPOSED'):
            extras['report_token'] = uuid.uuid4()  # so detail page can preview the public report link
        else:
            extras['report_token'] = uuid.uuid4()

        req = Request.objects.create(
            display_id=display_id,
            title=f"[DEMO] Analyse {service.name}",
            description=(
                "Demande de démonstration créée par seed_demo_request — "
                "à utiliser pour parcourir l'ensemble du workflow IBTIKAR."
            ),
            channel='IBTIKAR',
            status=target_status,
            urgency='Normal',
            service=service,
            requester=requester,
            assigned_to=analyst_profile,
            budget_amount=budget_amount,
            declared_ibtikar_balance=float(requester.ibtikar_declared_balance),
            service_params={'pathogenic': False, 'analysis_mode': 'Simple'},
            pricing=price_result,
            sample_table=[
                {'sample_id': 'DEMO-S1', 'source': 'isolat clinique', 'note': 'échantillon démo'},
                {'sample_id': 'DEMO-S2', 'source': 'écouvillon', 'note': 'échantillon démo'},
            ],
            requester_data={'organization': requester.organization or 'USTO'},
            **extras,
        )

        # Walk the history forward so the request detail page shows a
        # realistic timeline (DRAFT → SUBMITTED → … → target_status).
        history_chain = [
            '', 'SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE',
            'PLATFORM_NOTE_GENERATED', 'IBTIKAR_SUBMISSION_PENDING',
            'IBTIKAR_CODE_SUBMITTED', 'ASSIGNED',
        ]
        # Extend the chain past ASSIGNED if the target sits further along
        forward = [
            'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED',
            'ANALYSIS_STARTED', 'ANALYSIS_FINISHED', 'REPORT_UPLOADED',
            'REPORT_VALIDATED', 'SENT_TO_REQUESTER',
        ]
        if target_status in forward:
            history_chain.extend(forward[: forward.index(target_status) + 1])

        prev = ''
        for state in history_chain[1:]:
            RequestHistory.objects.create(
                request=req, from_status=prev, to_status=state,
                actor=None, notes='Seed démo',
            )
            prev = state
            if state == target_status:
                break

        # Mint the analyst's "you have a new task" notification so the
        # /notifications/<pk>/click/ deep-link can be tried right away.
        Notification.objects.create(
            user=analyst_profile.user,
            message=f"Nouvelle tâche assignée — {req.display_id}",
            request=req,
            notification_type='ASSIGNMENT',
        )

        # And one on the requester side, so they have something to click.
        Notification.objects.create(
            user=requester,
            message=f"Votre demande {req.display_id} a été assignée à un analyste.",
            request=req,
            notification_type='WORKFLOW',
        )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f"✓ Demo request {req.display_id} created."))
        self.stdout.write('')
        self.stdout.write('  status      : ' + req.status)
        self.stdout.write('  service     : ' + service.code + ' — ' + service.name)
        self.stdout.write(f'  budget      : {budget_amount:,.0f} DA  (declared: {balance:,.0f} DA)')
        self.stdout.write('  requester   : ' + requester.username + '  (' + (requester.get_full_name() or '') + ')')
        self.stdout.write('  analyst     : ' + analyst_profile.user.username + '  (' + (analyst_profile.user.get_full_name() or '') + ')')
        self.stdout.write('')
        self.stdout.write('  Try it out:')
        self.stdout.write('    Log in as  analyst / analyst1234   → /dashboard/analyst/  (task waiting)')
        self.stdout.write('    Log in as  amina   / demo1234      → /dashboard/requester/ (see your request)')
        self.stdout.write('    Log in as  admin_ops / platform1234 → /dashboard/ops/      (admin view)')

    # ── helpers ────────────────────────────────────────────────────────

    def _ensure_requester(self, balance):
        """Get or create the demo requester (matches seed_accounts)."""
        u, created = User.objects.get_or_create(
            username='amina',
            defaults={
                'email': 'amina@plagenor.dz', 'first_name': 'Amina',
                'last_name': 'Bensalem', 'role': 'REQUESTER',
                'organization': 'USTO', 'laboratory': 'LABBIOMIC',
                'supervisor': 'Pr. Khaldi', 'student_level': 'doctorat',
                'phone': '0555 87 65 43', 'ibtikar_id': 'IDGRSTD78901',
            },
        )
        if created:
            u.set_password('demo1234')
        # Always (re)set the declared balance so the cap-check passes.
        u.ibtikar_declared_balance = balance
        u.ibtikar_balance_declared_at = timezone.now()
        u.role = 'REQUESTER'
        u.is_active = True
        u.save()
        return u

    def _ensure_analyst(self):
        """Get or create the demo analyst + MemberProfile."""
        u, created = User.objects.get_or_create(
            username='analyst',
            defaults={
                'email': 'analyst@plagenor.dz', 'first_name': 'Ahmed',
                'last_name': 'Benali', 'role': 'MEMBER',
            },
        )
        if created:
            u.set_password('analyst1234')
        u.role = 'MEMBER'
        u.is_active = True
        u.save()
        profile, _ = MemberProfile.objects.get_or_create(user=u)
        return profile

    def _ensure_service(self, code):
        """Pick the requested service, or the first IBTIKAR-eligible active service."""
        qs = Service.objects.filter(
            active=True, channel_availability__in=['BOTH', 'IBTIKAR'],
        )
        if code:
            svc = qs.filter(code=code).first()
            if svc:
                return svc
            self.stdout.write(self.style.WARNING(
                f"  Service code '{code}' not found — falling back to first active."
            ))
        svc = qs.order_by('code').first()
        if not svc:
            raise SystemExit(
                "No active IBTIKAR-eligible service found. Run "
                "`python manage.py seed_services` first."
            )
        return svc
