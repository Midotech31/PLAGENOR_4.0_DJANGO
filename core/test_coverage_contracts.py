from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User, Technique
from core.assignment import (compute_member_score, get_member_workload,
                             get_recommended_members, recalculate_member_load)
from core.exceptions import PricingConfigurationError
from core.models import Request, Service
from core.pricing import calculate_price, resolve_cost, format_price
from notifications.models import Notification


class UncoveredContractsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='coverage-owner', role='CLIENT')
        self.other = User.objects.create_user(username='coverage-other', role='CLIENT')
        self.req = Request.objects.create(display_id='COVER-001', channel='GENOCLAB', requester=self.owner)
        self.service = Service.objects.create(code='COVER', name='Coverage assay', genoclab_price=10)

    def test_notification_read_timestamp_is_preserved_and_bulk_read_is_scoped(self):
        self.client.force_login(self.owner)
        mine = Notification.objects.create(user=self.owner, message='Invoice', request=self.req)
        other = Notification.objects.create(user=self.other, message='Private')
        response = self.client.get(reverse('notifications:click', args=[mine.pk]))
        self.assertEqual(response.url, reverse('dashboard:client_request_detail', args=[self.req.pk]))
        mine.refresh_from_db()
        self.assertIsNotNone(mine.read_at)
        first_read = mine.read_at
        self.client.get(reverse('notifications:click', args=[mine.pk]))
        mine.refresh_from_db()
        self.assertEqual(mine.read_at, first_read)
        unread = Notification.objects.create(user=self.owner, message='New')
        self.client.post(reverse('notifications:mark_all_read'))
        unread.refresh_from_db(); other.refresh_from_db()
        self.assertIsNotNone(unread.read_at)
        self.assertFalse(other.read)
        self.assertIsNone(other.read_at)
        self.assertEqual(self.client.get(reverse('notifications:click', args=[other.pk])).status_code, 404)

    def test_notification_links_do_not_redirect_to_external_hosts(self):
        self.client.force_login(self.owner)
        for link in ('https://evil.example/path', '//evil.example/path'):
            n = Notification.objects.create(user=self.owner, message='Unsafe', action_url=link)
            self.assertEqual(self.client.get(reverse('notifications:click', args=[n.pk])).url, '/dashboard/')
        n = Notification.objects.create(user=self.owner, message='Safe', action_url='/dashboard/client/')
        self.assertEqual(self.client.get(reverse('notifications:click', args=[n.pk])).url, '/dashboard/client/')
        n = Notification.objects.create(user=self.owner, message='Generic')
        self.assertEqual(self.client.get(reverse('notifications:click', args=[n.pk])).url, '/dashboard/')

    def test_notification_routes_respect_roles_and_ownership(self):
        from notifications.views import _get_detail_url
        expected = {'SUPER_ADMIN': 'dashboard:admin_request_detail', 'PLATFORM_ADMIN': 'dashboard:admin_request_detail',
                    'MEMBER': 'dashboard:analyst_request_detail', 'REQUESTER': 'dashboard:requester_request_detail'}
        for role, route in expected.items():
            self.owner.role = role
            self.assertEqual(_get_detail_url(self.owner, self.req), reverse(route, args=[self.req.pk]))
        for role in ('CLIENT', 'REQUESTER'):
            self.other.role = role
            self.assertIsNone(_get_detail_url(self.other, self.req))
        self.other.role = 'FINANCE'
        self.assertEqual(_get_detail_url(self.other, self.req), reverse('dashboard:finance'))
        n = Notification(user=self.other, request=self.req, message='Finance')
        self.assertEqual(n.get_absolute_url(), '/dashboard/finance/')
        self.assertIn('Finance', str(n))
        self.other.role = 'UNKNOWN'
        self.assertIsNone(_get_detail_url(self.other, self.req))

    def test_pricing_rejects_invalid_configuration_instead_of_charging_zero(self):
        invalid = [({}, []), ({'pricing': {'currency':'DZD'}}, [{}]),
                   ({'pricing': {'model':'per_sample_fixed','unit_price':10}}, {}),
                   ({'pricing': {'model':'per_sample_fixed'}}, [{}]),
                   ({'pricing': {'model':'per_sample_fixed','unit_price':10}}, []),
                   ({'pricing': {'model':'per_sample_table_row_with_multiplier'}}, [{}]),
                   ({'pricing': {'model':'per_sample_table_row_with_multiplier'}}, [])]
        for definition, samples in invalid:
            with self.subTest(definition=definition, samples=samples), self.assertRaises(PricingConfigurationError):
                calculate_price(definition, {}, samples)
        for price in ('NaN', 'Infinity', '-1', 'not-a-price'):
            with self.subTest(price=price), self.assertRaises(PricingConfigurationError):
                calculate_price({'pricing': {'model':'per_sample_fixed', 'unit_price':price}}, {}, [{}])
        self.assertEqual(format_price(1234), '1,234 DZD')

    def test_database_authored_prices_override_registry_and_validate_multiplier(self):
        block = {'base_price': {'default':'10.25'}, 'multipliers': {'full':'2'}}
        self.service.pricing_data = block
        with patch('core.registry.get_service_def', return_value=None):
            result = resolve_cost(self.service, 'GENOCLAB', sample_table=[{'id':1},{'id':2}], service_params={'analysis_mode':'full'})
            self.assertEqual(result['total'], Decimal('41.00'))
            self.assertEqual(result['source'], 'service_pricing_data')
            for params in ({}, {'analysis_mode':'missing'}):
                with self.assertRaises(PricingConfigurationError):
                    resolve_cost(self.service, 'GENOCLAB', sample_table=[{'id':1}], service_params=params)
            for invalid in (['invalid'], {'base_price': {'default':10}}):
                self.service.pricing_data = invalid
                with self.assertRaises(PricingConfigurationError):
                    resolve_cost(self.service, 'GENOCLAB', sample_table=[{'id':1}])

    def test_assignment_zero_productivity_and_workload(self):
        user = User.objects.create_user(username='coverage-member', role='MEMBER')
        member = user.member_profile
        member.current_load = 0; member.available = True; member.productivity_score = 0
        self.assertEqual(compute_member_score(member), 50.0)
        member.productivity_score = None
        self.assertEqual(compute_member_score(member), 60.0)
        self.assertEqual(compute_member_score(member, self.service), 40.0)
        self.assertEqual(get_recommended_members(self.service), [])
        self.req.assigned_to = member; self.req.save()
        self.assertEqual(recalculate_member_load(member.pk), 1)
        member.refresh_from_db()
        stats = get_member_workload(member)
        self.assertEqual(stats['active_requests'], 1)
        self.assertEqual(stats['current_load'], 1)
        self.assertEqual(recalculate_member_load(None), 0)
        self.assertEqual(recalculate_member_load(999999), 0)

    def test_tariff_api_rejects_invalid_inputs_without_mutating_saved_prices(self):
        from core.models import ServicePricing
        ops = User.objects.create_user(username='coverage-ops', role='PLATFORM_ADMIN')
        self.client.force_login(ops)
        payload = {'name':'Standard', 'amount':'10.25', 'is_active':'on', 'channel':'OHB', 'pricing_type':'BASE'}
        add = reverse('dashboard:pricing_add_api', args=[self.service.pk])
        for invalid in ({'name':''}, {'pricing_type':'UNKNOWN'}, {'channel':'PUBLIC'}, {'amount':''},
                        {'amount':'abc'}, {'amount':'NaN'}, {'min_quantity':'x'}, {'min_quantity':'0'},
                        {'min_quantity':'3','max_quantity':'2'}, {'min_amount':'3','max_amount':'2'},
                        {'valid_from':'bad-date'}, {'valid_from':'2026-12-31','valid_until':'2026-01-01'}):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.client.post(add, {**payload, **invalid}).status_code, 400)
                self.assertFalse(ServicePricing.objects.filter(service=self.service).exists())
        response = self.client.post(add, payload)
        self.assertEqual(response.status_code, 201)
        tier = ServicePricing.objects.get(service=self.service)
        update = reverse('dashboard:pricing_update_api', args=[tier.pk])
        self.assertEqual(self.client.post(update, {**payload, 'amount':'invalid'}).status_code, 400)
        tier.refresh_from_db(); self.assertEqual(tier.amount, Decimal('10.25'))
        self.assertEqual(self.client.post(update, {**payload, 'amount':'12.50'}).status_code, 200)
        tier.refresh_from_db(); self.assertEqual(tier.amount, Decimal('12.50'))
        listing = self.client.get(reverse('dashboard:pricing_list_api', args=[self.service.pk]))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()['configs']), 1)
        self.assertEqual(self.client.post(reverse('dashboard:pricing_delete_api', args=[tier.pk])).status_code, 200)
        self.assertFalse(ServicePricing.objects.filter(pk=tier.pk).exists())
