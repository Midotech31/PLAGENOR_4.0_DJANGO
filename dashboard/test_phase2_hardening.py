"""Regression tests for the second production-hardening phase."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from core.exceptions import InvalidTransitionError
from core.models import Invoice, RateLimitBucket, Request, Service


class SharedRateLimitTests(TestCase):
    def setUp(self):
        RateLimitBucket.objects.all().delete()

    def test_database_counter_is_shared_hashed_and_expires(self):
        from core.ratelimit import _database_counter

        raw_key = 'rl:login:203.0.113.8'
        self.assertEqual(_database_counter(raw_key, 2, 300)[0], False)
        self.assertEqual(_database_counter(raw_key, 2, 300)[0], False)
        limited, retry_after = _database_counter(raw_key, 2, 300)
        self.assertTrue(limited)
        self.assertGreater(retry_after, 0)

        bucket = RateLimitBucket.objects.get()
        self.assertNotIn('203.0.113.8', bucket.key_hash)
        self.assertEqual(len(bucket.key_hash), 64)

        bucket.expires_at = timezone.now() - timedelta(seconds=1)
        bucket.save(update_fields=['expires_at'])
        self.assertEqual(_database_counter(raw_key, 2, 300)[0], False)
        bucket.refresh_from_db()
        self.assertEqual(bucket.count, 1)

    @override_settings(
        RATE_LIMIT_BACKEND='database', RATE_LIMIT_FAIL_CLOSED=True,
    )
    def test_database_limiter_blocks_and_fails_closed(self):
        from core.ratelimit import rate_limit

        factory = RequestFactory()

        @rate_limit('phase2', limit=1, window=120)
        def protected(_request):
            from django.http import HttpResponse
            return HttpResponse('ok')

        first = protected(factory.post('/', REMOTE_ADDR='198.51.100.3'))
        second = protected(factory.post('/', REMOTE_ADDR='198.51.100.3'))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn('Retry-After', second)

        with patch('core.ratelimit._database_counter', side_effect=RuntimeError('db unavailable')):
            degraded = protected(factory.post('/', REMOTE_ADDR='198.51.100.4'))
        self.assertEqual(degraded.status_code, 503)
        self.assertEqual(degraded['Retry-After'], '60')


class FinanceTransactionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.finance = User.objects.create_user(
            username='phase2-finance', password='test-password', role='FINANCE')
        cls.client_user = User.objects.create_user(
            username='phase2-client', password='test-password', role='CLIENT')
        cls.service = Service.objects.create(
            code='PHASE2-FIN', name='Phase 2 financial service',
            channel_availability='BOTH')

    def setUp(self):
        self.client.force_login(self.finance)

    def make_budget_request(self, suffix='1'):
        return Request.objects.create(
            display_id=f'P2-{suffix[:17]}', title='Budget validation',
            channel='IBTIKAR', status='VALIDATION_FINANCE',
            requester=self.client_user, service=self.service,
            budget_amount=Decimal('1250.00'), rejection_reason='')

    def test_approval_rolls_price_back_when_transition_fails(self):
        req = self.make_budget_request('ROLLBACK-APPROVE')
        with patch(
            'dashboard.views.finance.transition',
            side_effect=InvalidTransitionError('simulated failure'),
        ):
            response = self.client.post(
                f'/dashboard/finance/validate/{req.pk}/', {'action': 'approve'})
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'VALIDATION_FINANCE')
        self.assertIsNone(req.admin_validated_price)

    def test_rejection_requires_reason_and_rolls_back_on_failure(self):
        req = self.make_budget_request('ROLLBACK-REJECT')
        self.client.post(
            f'/dashboard/finance/validate/{req.pk}/', {'action': 'reject', 'reason': ''})
        req.refresh_from_db()
        self.assertEqual(req.rejection_reason, '')
        self.assertEqual(req.status, 'VALIDATION_FINANCE')

        with patch(
            'dashboard.views.finance.transition',
            side_effect=InvalidTransitionError('simulated failure'),
        ):
            self.client.post(
                f'/dashboard/finance/validate/{req.pk}/',
                {'action': 'reject', 'reason': 'Budget non conforme'},
            )
        req.refresh_from_db()
        self.assertEqual(req.rejection_reason, '')
        self.assertEqual(req.status, 'VALIDATION_FINANCE')

    def test_valid_approval_and_payment_status_are_persisted(self):
        req = self.make_budget_request('SUCCESS')
        response = self.client.post(
            f'/dashboard/finance/validate/{req.pk}/', {'action': 'approve'})
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'PLATFORM_NOTE_GENERATED')
        self.assertEqual(req.admin_validated_price, Decimal('1250.00'))

        invoice = Invoice.objects.create(
            invoice_number='PHASE2-INV-1', request=req, client=self.client_user,
            line_items=[], total_ttc=Decimal('1250.00'))
        with patch('dashboard.views.finance.log_financial_action') as audit:
            response = self.client.post(
                f'/dashboard/finance/payment/{invoice.pk}/',
                {'payment_status': 'COMPLETED'},
            )
        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.payment_status, 'COMPLETED')
        audit.assert_called_once()
