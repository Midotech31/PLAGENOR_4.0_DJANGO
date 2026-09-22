from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F as models_F
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.forms.models import model_to_dict
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import translation

from erp import forms, views
from erp.models import (AccessGrant, Article, ArticleConversion, AuditEvent, Capability,
                        Category, Location, LocationClosure, LocationType, Party, PriceObservation, Unit)
from erp.permissions import (catalog_scope, has_access, is_manager, permitted, require,
                             storage_scope)
from erp.services.access import save_grant
from erp.services.catalog import convert_quantity, quantity, record_price, save_article, save_conversion, save_reference
from erp.services.common import Conflict, assign, scalar, snapshot
from erp.services.storage import save_location
from erp.templatetags.erp_access import erp_available, erp_value


def fixtures():
    User = get_user_model()
    admin = User.objects.create_user(username='erp-admin', role='SUPER_ADMIN')
    operator = User.objects.create_user(username='erp-operator', role='MEMBER')
    outsider = User.objects.create_user(username='erp-customer', role='REQUESTER')
    unit = save_reference(admin, Unit, {'code': 'PIECE', 'name': 'Pièce', 'dimension': 'COUNT', 'factor': Decimal(1)})
    ml = save_reference(admin, Unit, {'code': 'ML', 'name': 'mL', 'dimension': 'VOLUME', 'factor': Decimal('0.001')})
    ul = save_reference(admin, Unit, {'code': 'UL', 'name': 'µL', 'dimension': 'VOLUME', 'factor': Decimal('0.000001')})
    box = save_reference(admin, Unit, {'code': 'BOX', 'name': 'Boîte', 'dimension': 'PACKAGE', 'factor': Decimal(1)})
    category = save_reference(admin, Category, {'code': 'REAGENTS', 'name': 'Réactifs'})
    other = save_reference(admin, Category, {'code': 'CHEMICALS', 'name': 'Produits chimiques'})
    party = save_reference(admin, Party, {'code': 'SUPPLIER', 'name': 'Fournisseur de test', 'is_supplier': True, 'is_manufacturer': True})
    article = save_article(admin, {'code': 'TIPS', 'name': 'Pointes', 'category': category, 'base_unit': unit,
                                   'manufacturer': party, 'manufacturer_reference': 'R-123'})
    liquid = save_article(admin, {'code': 'BUFFER', 'name': 'Tampon', 'category': other, 'base_unit': ml})
    kind = save_reference(admin, LocationType, {'code': 'ROOM', 'name': 'Salle'})
    storage_kind = save_reference(admin, LocationType, {'code': 'FREEZER', 'name': 'Congélateur', 'can_store': True, 'cold_storage': True})
    lab = save_location(admin, {'code': 'LAB', 'name': 'Laboratoire', 'kind': kind})
    freezer = save_location(admin, {'code': 'F80', 'name': 'Congélateur -80 °C', 'kind': storage_kind, 'parent': lab,
                                    'temperature_target': Decimal('-80'), 'temperature_min': Decimal('-90'), 'temperature_max': Decimal('-70')})
    rack = save_location(admin, {'code': 'RACK', 'name': 'Rack', 'kind': kind, 'parent': freezer})
    return locals()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
                   STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                             'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
                   SECURE_SSL_REDIRECT=False)
class FoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, value in fixtures().items():
            if name != 'User':
                setattr(cls, name, value)

    def grant(self, capability, **scope):
        return save_grant(self.admin, {'user': self.operator, 'capability': capability, **scope})

    def form_data(self, form_class, instance, **changes):
        data = {key: (str(value) if value is not None else '')
                for key, value in model_to_dict(instance, fields=form_class._meta.fields,
                                               exclude=form_class._meta.exclude).items()}
        data['expected_version'] = str(instance.version)
        data.update(changes)
        return data

    def test_account_reuse_and_scoped_permission_predicates(self):
        self.assertTrue(is_manager(self.admin))
        self.assertFalse(has_access(self.outsider))
        self.assertFalse(has_access(AnonymousUser()))
        self.assertFalse(erp_available(self.operator))
        self.grant(Capability.EDIT_CATALOG, category=self.category)
        self.assertTrue(erp_available(self.operator))
        self.assertTrue(permitted(self.operator, Capability.VIEW_CATALOG, category=self.category))
        self.assertFalse(permitted(self.operator, Capability.VIEW_CATALOG, category=self.other))
        self.assertFalse(permitted(self.operator, Capability.EDIT_CATALOG))
        self.assertFalse(permitted(self.outsider, Capability.VIEW_CATALOG))
        self.assertEqual(list(catalog_scope(Article.objects.all(), self.operator)), [self.article])
        self.assertEqual(catalog_scope(Article.objects.all(), self.outsider).count(), 0)
        self.grant(Capability.VIEW_CATALOG)
        self.assertEqual(catalog_scope(Article.objects.all(), self.operator).count(), 2)
        self.assertEqual(catalog_scope(Article.objects.all(), self.admin).count(), 2)
        with self.assertRaises(PermissionDenied):
            require(self.outsider, Capability.VIEW_CATALOG)
        self.operator.is_active = False
        self.assertFalse(has_access(self.operator))

    def test_location_scopes_include_descendants_not_siblings_or_parents(self):
        self.grant(Capability.EDIT_STORAGE, location=self.freezer)
        self.assertTrue(permitted(self.operator, Capability.EDIT_STORAGE, location=self.rack))
        self.assertFalse(permitted(self.operator, Capability.EDIT_STORAGE, location=self.lab))
        self.assertEqual(set(storage_scope(Location.objects.all(), self.operator)), {self.freezer, self.rack})
        self.assertEqual(storage_scope(Location.objects.all(), self.outsider).count(), 0)
        self.assertEqual(storage_scope(Location.objects.all(), self.admin).count(), 3)
        self.grant(Capability.VIEW_STORAGE)
        self.assertEqual(storage_scope(Location.objects.all(), self.operator).count(), 3)

    def test_grant_changes_are_versioned_and_external_accounts_are_refused(self):
        grant = self.grant(Capability.VIEW_CATALOG)
        with self.assertRaises(PermissionDenied):
            save_grant(self.operator, {'user': self.operator, 'capability': Capability.EDIT_COST})
        with self.assertRaises(ValidationError):
            save_grant(self.admin, {'user': self.outsider, 'capability': Capability.VIEW_CATALOG})
        with self.assertRaises(ValidationError):
            self.grant(Capability.VIEW_STORAGE, category=self.category)
        with self.assertRaises(ValidationError):
            self.grant(Capability.VIEW_CATALOG, location=self.lab)
        changed = save_grant(self.admin, {'active': False}, pk=grant.pk, expected=1)
        self.assertEqual(changed.version, 2)
        self.assertFalse(has_access(self.operator))
        with self.assertRaises(Conflict):
            save_grant(self.admin, {'active': True}, pk=grant.pk, expected=1)

    def test_reference_units_are_immutable_but_labels_and_status_are_editable(self):
        unit = save_reference(self.admin, Unit, {'name': 'Pièces', 'factor': Decimal('1')}, pk=self.unit.pk, expected=1)
        self.assertEqual(unit.version, 2)
        with self.assertRaises(ValidationError):
            save_reference(self.admin, Unit, {'factor': Decimal('2')}, pk=unit.pk, expected=2)
        with self.assertRaises(ValidationError):
            save_reference(self.admin, Unit, {'code': 'BAD', 'name': 'Boîte', 'dimension': 'PACKAGE', 'factor': Decimal(960)})
        with self.assertRaises(ValidationError):
            save_reference(self.admin, Article, {})
        with self.assertRaises(ValidationError):
            assign(self.article, {'version': 50})
        with self.assertRaises(ValidationError):
            save_reference(self.admin, Unit, {'code': 'ZERO', 'name': 'Z', 'dimension': 'COUNT', 'factor': Decimal(0)})

    def test_category_cycles_are_refused(self):
        sub = save_reference(self.admin, Category, {'code': 'SUB', 'name': 'Sous-catégorie', 'parent': self.category})
        with self.assertRaises(ValidationError):
            save_reference(self.admin, Category, {'parent': sub}, pk=self.category.pk, expected=1)
        self.category.refresh_from_db()
        self.assertIsNone(self.category.parent_id)

    def test_article_edits_require_old_and_new_category_permissions(self):
        self.grant(Capability.EDIT_CATALOG, category=self.category)
        changed = save_article(self.operator, {'name': 'Pointes filtrées'}, pk=self.article.pk, expected=1)
        self.assertEqual(changed.version, 2)
        with self.assertRaises(PermissionDenied):
            save_article(self.operator, {'category': self.other}, pk=self.article.pk, expected=2)
        self.article.refresh_from_db()
        self.assertEqual(self.article.category, self.category)
        with self.assertRaises(Conflict):
            save_article(self.admin, {'name': 'Écrasement'}, pk=self.article.pk, expected=1)
        with self.assertRaises(ValidationError):
            save_article(self.admin, {'base_unit': self.ml}, pk=self.article.pk, expected=2)

    def test_article_identity_thresholds_and_partner_validation(self):
        base = {'code': 'SECOND', 'name': 'Second', 'category': self.category, 'base_unit': self.unit}
        for changes in ({'minimum_stock': -1}, {'order_multiple': 0},
                        {'temperature_min': Decimal(8), 'temperature_max': Decimal(4)},
                        {'manufacturer': self.party, 'manufacturer_reference': 'r-123'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                save_article(self.admin, {**base, **changes})
        self.party.is_manufacturer = False
        with self.assertRaises(ValidationError):
            save_article(self.admin, {**base, 'manufacturer': self.party})
        self.party.is_supplier = False
        with self.assertRaises(ValidationError):
            save_article(self.admin, {**base, 'preferred_supplier': self.party})
        self.unit.active = False
        with self.assertRaises(ValidationError):
            save_article(self.admin, base)
        self.unit.active = True
        self.category.active = False
        with self.assertRaises(ValidationError):
            save_article(self.admin, base)

    def test_unit_and_packaging_conversions_are_exact_and_product_specific(self):
        result, factor = convert_quantity(self.liquid, '125', self.ul)
        self.assertEqual(result, Decimal('0.125000'))
        self.assertEqual(factor, Decimal('0.001'))
        with self.assertRaises(ValidationError):
            convert_quantity(self.article, 1, self.box)
        conversion = save_conversion(self.admin, self.article, {'unit': self.box, 'factor': Decimal(960),
                                                                 'justification': '10 racks de 96 pointes'})
        self.assertEqual(convert_quantity(self.article, 2, self.box)[0], Decimal(1920))
        conversion = save_conversion(self.admin, self.article, {'factor': Decimal(480)}, pk=conversion.pk, expected=1)
        self.assertEqual(conversion.version, 2)
        self.assertEqual(convert_quantity(self.article, 1, self.box)[0], Decimal(480))
        with self.assertRaises(ValidationError):
            convert_quantity(self.liquid, 1, self.box)
        with self.assertRaises(ValidationError):
            save_conversion(self.admin, self.article, {'unit': self.unit, 'factor': Decimal(1), 'justification': 'X'})
        with self.assertRaises(ValidationError):
            save_conversion(self.admin, self.article, {'unit': self.ul, 'factor': Decimal(1), 'justification': ' '})
        with self.assertRaises(ValidationError):
            save_conversion(self.admin, self.article, {'article': self.liquid, 'unit': self.box, 'factor': Decimal(1), 'justification': 'X'})

    def test_nonfinite_excessive_or_imprecise_quantities_fail_without_rounding(self):
        for value in (True, '-1', 'NaN', 'Infinity', '1E99999999', '1E-999999999', '1E-61', 'x', None, '1' * 65):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                quantity(value)
        self.assertEqual(quantity('1E-60'), Decimal('1E-60'))
        with self.assertRaises(ValidationError):
            convert_quantity(self.article, '1E-999999999', self.unit)
        self.assertEqual(convert_quantity(self.article, 0, self.unit)[0], 0)
        with self.assertRaises(ValidationError):
            convert_quantity(self.article, '0.0000001', self.unit)
        self.article.active = False
        with self.assertRaises(ValidationError):
            convert_quantity(self.article, 1, self.unit)

    def test_hierarchy_reparenting_preserves_identity_and_internal_closure(self):
        target = save_location(self.admin, {'code': 'LAB2', 'name': 'Laboratoire 2', 'kind': self.kind})
        save_location(self.admin, {'parent': target}, pk=self.freezer.pk, expected=1)
        self.assertTrue(LocationClosure.objects.filter(ancestor=target, descendant=self.rack, depth=2).exists())
        self.assertFalse(LocationClosure.objects.filter(ancestor=self.lab, descendant=self.rack).exists())
        self.assertTrue(LocationClosure.objects.filter(ancestor=self.freezer, descendant=self.rack, depth=1).exists())
        self.assertEqual(Location.objects.count(), 4)
        with self.assertRaises(ValidationError):
            save_location(self.admin, {'parent': self.rack}, pk=target.pk, expected=1)
        with self.assertRaises(ValidationError):
            save_location(self.admin, {'active': False}, pk=self.freezer.pk, expected=2)
        with self.assertRaises(Conflict):
            save_location(self.admin, {'name': 'Conflit'}, pk=self.freezer.pk, expected=1)

    def test_storage_ranges_grids_and_inactive_references_are_validated(self):
        base = {'code': 'BOX1', 'name': 'Boîte', 'kind': self.kind, 'parent': self.rack}
        box = save_location(self.admin, {**base, 'grid_rows': 8, 'grid_columns': 12})
        self.assertEqual(box.capacity, 96)
        for values in ({'temperature_target': 10, 'temperature_max': 8},
                       {'temperature_target': -90, 'temperature_min': -80},
                       {'grid_rows': 8, 'grid_columns': 12, 'capacity': 81}, {'grid_rows': 8}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                save_location(self.admin, {**base, 'code': 'INVALID', **values})
        self.rack.active = False
        with self.assertRaises(ValidationError):
            save_location(self.admin, {**base, 'code': 'INACTIVE'})
        self.rack.active = True
        self.kind.active = False
        with self.assertRaises(ValidationError):
            save_location(self.admin, {**base, 'code': 'INACTIVE'})

    def test_scoped_operator_can_edit_scope_root_without_reparenting(self):
        self.grant(Capability.EDIT_STORAGE, location=self.freezer)
        modified = save_location(self.operator, {'name': 'Congélateur principal'}, pk=self.freezer.pk, expected=1)
        self.assertEqual(modified.name, 'Congélateur principal')
        with self.assertRaises(PermissionDenied):
            save_location(self.operator, {'parent': None}, pk=self.freezer.pk, expected=2)

    def test_audit_is_atomic_append_only_and_uses_existing_log_sink(self):
        count = AuditEvent.objects.count()
        with patch('erp.services.common.log_action') as sink, self.captureOnCommitCallbacks(execute=True):
            save_article(self.admin, {'name': 'Pointes de contrôle'}, pk=self.article.pk, expected=1)
        sink.assert_called_once()
        event = AuditEvent.objects.latest('id')
        self.assertEqual(event.before['name'], 'Pointes')
        self.assertEqual(event.after['name'], 'Pointes de contrôle')
        self.assertEqual(event.actor, self.admin)
        for operation in (lambda: event.save(), lambda: event.delete(),
                          lambda: AuditEvent.objects.filter(pk=event.pk).update(reason='erase'),
                          lambda: AuditEvent.objects.filter(pk=event.pk).delete()):
            with self.assertRaises(ValidationError):
                operation()
        with patch('erp.services.common.AuditEvent.objects.create', side_effect=RuntimeError('storage failure')):
            with self.assertRaises(RuntimeError):
                save_article(self.admin, {'name': 'Uncommitted'}, pk=self.article.pk, expected=2)
        self.article.refresh_from_db()
        self.assertEqual(self.article.name, 'Pointes de contrôle')
        self.assertEqual(AuditEvent.objects.count(), count + 1)

    def test_prices_are_immutable_separate_and_do_not_rewrite_catalogue(self):
        values = {'unit': self.unit, 'amount': Decimal('12.50'), 'observed_on': date(2026, 9, 1),
                  'source': 'Devis fournisseur de test', 'currency': 'dzd', 'supplier': self.party}
        with self.assertRaises(PermissionDenied):
            record_price(self.operator, self.article, values)
        self.grant(Capability.EDIT_COST, category=self.category)
        price = record_price(self.operator, self.article, values)
        self.assertEqual(price.amount, Decimal('12.50'))
        self.assertEqual(price.currency, 'DZD')
        self.assertEqual(price.snapshot['article_name'], 'Pointes')
        save_article(self.admin, {'name': 'Nouvelle désignation'}, pk=self.article.pk, expected=1)
        price.refresh_from_db()
        self.assertEqual(price.snapshot['article_name'], 'Pointes')
        with self.assertRaises(ValidationError):
            price.save()
        for changes in ({'article': self.liquid}, {'actor': self.outsider}, {'currency': 'INVALID'}, {'amount': -1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                record_price(self.admin, self.article, {**values, **changes})
        self.party.is_supplier = False
        with self.assertRaises(ValidationError):
            record_price(self.admin, self.article, values)

    def test_language_fallback_and_missing_values_remain_explicit(self):
        self.article.name_en = 'Pipette tips'
        self.article.name_ar = 'رؤوس ماصات'
        for language, expected in [('en', 'Pipette tips'), ('ar', 'رؤوس ماصات'), ('fr', 'Pointes'), ('de', 'Pointes')]:
            with translation.override(language):
                self.assertEqual(str(self.article), expected)
        with translation.override('fr'):
            self.assertEqual(erp_value(True), 'Oui')
            self.assertEqual(erp_value(False), 'Non')
            self.assertEqual(erp_value(None), 'Non renseigné')
            self.assertEqual(erp_value('abc'), 'abc')
        self.assertEqual(scalar(date(2026, 9, 1)), '2026-09-01')
        self.assertEqual(scalar(Decimal('1.20')), '1.20')
        self.assertEqual(scalar(None), None)

    def test_http_authentication_registry_and_supported_methods(self):
        self.assertEqual(self.client.get('/erp/').status_code, 302)
        self.client.force_login(self.outsider)
        for url in ('/erp/', '/erp/articles/', '/erp/audit/', '/erp/units/new/'):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/erp/').status_code, 200)
        self.assertEqual(self.client.post('/erp/').status_code, 405)
        self.assertEqual(self.client.get('/erp/unknown/').status_code, 404)
        for section in views.SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(self.client.get('/erp/' + section + '/').status_code, 200)
                self.assertEqual(self.client.get('/erp/' + section + '/new/').status_code, 200)
        self.assertEqual(self.client.get('/erp/audit/').status_code, 200)

    def test_list_filters_and_costs_do_not_cross_permission_boundaries(self):
        self.grant(Capability.VIEW_CATALOG, category=self.category)
        self.client.force_login(self.operator)
        self.assertContains(self.client.get('/erp/articles/'), 'TIPS')
        self.assertNotContains(self.client.get('/erp/articles/'), 'BUFFER')
        self.assertEqual(self.client.get(reverse('erp:article', args=[self.liquid.pk])).status_code, 404)
        self.assertContains(self.client.get('/erp/articles/?q=R-123&state=all'), 'TIPS')
        self.assertNotContains(self.client.get('/erp/articles/?q=NOTFOUND'), 'Pointes')
        self.assertNotContains(self.client.get('/erp/articles/?state=inactive'), 'TIPS')
        self.assertEqual(self.client.get('/erp/delegations/').status_code, 403)
        self.assertEqual(self.client.get('/erp/location-types/').status_code, 403)
        self.assertEqual(self.client.get('/erp/units/new/').status_code, 403)
        record_price(self.admin, self.article, {'unit': self.unit, 'amount': Decimal('77.20'),
                     'observed_on': date(2026, 9, 1), 'source': 'ERP_PRIVATE_PRICE_MARKER'})
        detail = reverse('erp:article', args=[self.article.pk])
        self.assertNotContains(self.client.get(detail), 'ERP_PRIVATE_PRICE_MARKER')
        self.assertEqual(self.client.get(reverse('erp:price', args=[self.article.pk])).status_code, 403)
        self.grant(Capability.VIEW_COST, category=self.category)
        self.assertContains(self.client.get(detail), 'ERP_PRIVATE_PRICE_MARKER')
        self.assertEqual(self.client.get(reverse('erp:price', args=[self.article.pk])).status_code, 403)

    def test_http_reference_creation_and_optimistic_edit_conflicts(self):
        self.client.force_login(self.admin)
        data = {'code': 'COUNT2', 'name': 'Autre unité', 'dimension': 'COUNT', 'factor': '1', 'active': 'on'}
        response = self.client.post('/erp/units/new/', data)
        self.assertEqual(response.status_code, 302)
        obj = Unit.objects.get(code='COUNT2')
        url = reverse('erp:edit', kwargs={'section': 'units', 'pk': obj.pk})
        self.assertEqual(self.client.get(url).status_code, 200)
        edited = {**data, 'name': 'Unité renommée', 'expected_version': '1'}
        self.assertEqual(self.client.post(url, edited).status_code, 302)
        self.assertEqual(self.client.post(url, edited).status_code, 400)
        obj.refresh_from_db()
        self.assertEqual(obj.name, 'Unité renommée')
        self.assertEqual(self.client.post(url, {**edited, 'factor': '2', 'expected_version': '2'}).status_code, 400)
        self.assertEqual(self.client.post('/erp/units/new/', {'code': 'BAD'}).status_code, 400)
        form = forms.UnitForm({}, user=self.admin)
        form.is_valid()
        views.add_validation(form, IntegrityError('duplicate'))
        self.assertTrue(form.non_field_errors())

    def test_http_scoped_catalogue_and_storage_edits_are_enforced(self):
        self.grant(Capability.EDIT_CATALOG, category=self.category)
        self.grant(Capability.EDIT_STORAGE, location=self.freezer)
        self.client.force_login(self.operator)
        self.assertContains(self.client.get('/erp/'), 'Référentiels scientifiques')
        self.assertEqual(self.client.get('/erp/articles/new/').status_code, 200)
        self.assertEqual(self.client.get('/erp/locations/new/').status_code, 200)
        self.assertContains(self.client.get('/erp/articles/'), 'Ajouter')
        self.assertContains(self.client.get('/erp/locations/'), 'Ajouter')
        data = self.form_data(forms.ArticleForm, self.article, name='Pointes neuves')
        url = reverse('erp:edit', kwargs={'section': 'articles', 'pk': self.article.pk})
        self.assertEqual(self.client.post(url, data).status_code, 302)
        bad = {**data, 'category': str(self.other.pk), 'expected_version': '2'}
        self.assertEqual(self.client.post(url, bad).status_code, 400)
        location_data = self.form_data(forms.LocationForm, self.freezer, name='Congélateur central')
        location_url = reverse('erp:edit', kwargs={'section': 'locations', 'pk': self.freezer.pk})
        self.assertEqual(self.client.post(location_url, location_data).status_code, 302)
        denied_url = reverse('erp:edit', kwargs={'section': 'locations', 'pk': self.lab.pk})
        self.assertEqual(self.client.get(denied_url).status_code, 404)
        self.assertEqual(self.client.get('/erp/delegations/new/').status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/erp/delegations/').status_code, 200)

    def test_conversion_and_price_forms_handle_success_errors_and_updates(self):
        self.client.force_login(self.admin)
        conversion_url = reverse('erp:conversion_new', args=[self.article.pk])
        self.assertEqual(self.client.get(conversion_url).status_code, 200)
        data = {'unit': str(self.box.pk), 'factor': '960', 'justification': '10 × 96 pointes', 'active': 'on'}
        self.assertEqual(self.client.post(conversion_url, data).status_code, 302)
        conversion = self.article.conversions.get(unit=self.box)
        edit = reverse('erp:conversion_edit', args=[self.article.pk, conversion.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        self.assertEqual(self.client.post(edit, {**data, 'expected_version': '1', 'factor': '480'}).status_code, 302)
        self.assertEqual(self.client.post(edit, {**data, 'expected_version': '1'}).status_code, 400)
        self.assertEqual(self.client.post(conversion_url, {'unit': str(self.unit.pk), 'factor': '1', 'justification': 'X'}).status_code, 400)
        self.assertEqual(self.client.post(conversion_url, {'unit': ''}).status_code, 400)
        price_url = reverse('erp:price', args=[self.article.pk])
        self.assertEqual(self.client.get(price_url).status_code, 200)
        price = {'unit': str(self.unit.pk), 'amount': '25.00', 'currency': 'DZD', 'observed_on': '2026-09-01', 'source': 'Devis de test'}
        self.assertEqual(self.client.post(price_url, price).status_code, 302)
        self.assertEqual(self.client.post(price_url, {**price, 'unit': str(self.ml.pk)}).status_code, 400)
        self.assertEqual(self.client.post(price_url, {'amount': '-1'}).status_code, 400)
        self.assertEqual(self.client.get(reverse('erp:article', args=[self.article.pk])).status_code, 200)

    def test_search_pagination_inactive_records_and_cross_site_scripting(self):
        self.client.force_login(self.admin)
        for index in range(33):
            save_reference(self.admin, Unit, {'code': 'Q%02d' % index, 'name': '<script>alert(1)</script>', 'dimension': 'COUNT'})
        response = self.client.get('/erp/units/?q=Q&state=all&page=2')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertEqual(self.client.get('/erp/units/?page=not-a-number').status_code, 200)
        self.assertEqual(self.client.get('/erp/audit/?page=2').status_code, 200)
        self.client.force_login(self.operator)
        self.grant(Capability.EDIT_STORAGE, location=self.freezer)
        self.assertEqual(self.client.get('/erp/').status_code, 200)
        self.assertEqual(self.client.get('/erp/parties/').status_code, 403)

    def test_real_csrf_middleware_blocks_unauthenticated_mutation_tokens(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.admin)
        self.assertEqual(browser.post('/erp/units/new/', {'code': 'UNSAFE'}).status_code, 403)
        self.assertFalse(Unit.objects.filter(code='UNSAFE').exists())


    def test_structured_quantities_operational_units_and_internal_codes(self):
        with self.assertRaises(ValidationError):
            save_article(self.admin, {'concentration_value': Decimal('10')}, pk=self.article.pk, expected=1)
        changed = save_article(self.admin, {'concentration_value': Decimal('10'), 'concentration_unit': self.ml,
                                            'purchase_unit': self.unit, 'consumption_unit': self.unit}, pk=self.article.pk, expected=1)
        self.assertEqual(changed.purchase_unit, self.unit)
        self.assertEqual(changed.consumption_unit, self.unit)
        with self.assertRaises(ValidationError):
            save_article(self.admin, {'purchase_unit': self.box}, pk=self.article.pk, expected=2)
        with self.assertRaises(ValidationError):
            save_article(self.admin, {'code': 'REASSIGNED'}, pk=self.article.pk, expected=2)
        self.assertTrue(Article.objects.filter(code='TIPS').exists())
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post('/erp/units/new/', {'code': 'lower-code', 'name': 'Unité', 'dimension': 'COUNT', 'factor': '1', 'active': 'on'}).status_code, 302)
        self.assertTrue(Unit.objects.filter(code='LOWER-CODE').exists())
        grouped = forms.ArticleForm(instance=changed, user=self.admin)
        self.assertEqual({field.name for group in grouped.groups for field in group['fields']},
                         {field.name for field in grouped.visible_fields()})

    def test_hierarchical_navigation_and_parent_prefill(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('erp:location', args=[self.freezer.pk]))
        self.assertContains(response, 'RACK')
        self.assertContains(response, self.lab.name)
        create = '/erp/locations/new/?parent=' + str(self.freezer.pk)
        response = self.client.get(create)
        self.assertEqual(response.context['form'].initial['parent'], self.freezer.pk)
        self.assertEqual(self.client.get('/erp/locations/new/?parent=invalid').status_code, 404)
        self.grant(Capability.EDIT_STORAGE, location=self.rack)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(create).status_code, 404)
        self.assertEqual(self.client.get(reverse('erp:location', args=[self.lab.pk])).status_code, 404)


    def test_new_erp_translations_are_available_in_all_requested_languages(self):
        self.client.force_login(self.admin)
        for lang, expected in [('fr', 'Référentiels scientifiques'), ('en', 'Scientific reference data'), ('ar', 'المرجعيات العلمية')]:
            self.client.cookies['django_language'] = lang
            response = self.client.get('/erp/')
            self.assertContains(response, expected)
            self.assertContains(response, 'dir="rtl"' if lang == 'ar' else 'dir="ltr"')
            detail = self.client.get(reverse('erp:article', args=[self.article.pk]))
            self.assertNotIn(self.article.criticality, [str(value) for _, value in detail.context['fields']])
            self.assertContains(detail, 'tabindex="0" role="region"', count=2)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        for name, value in fixtures().items():
            if name != 'User':
                setattr(self, name, value)

    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_opposite_reparenting_cannot_create_cycle(self):
        sibling = save_location(self.admin, {'code': 'F2', 'name': 'Second congélateur', 'kind': self.storage_kind, 'parent': self.lab})
        barrier = Barrier(2)

        def move(source, parent):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                save_location(self.admin, {'parent': parent}, pk=source.pk, expected=1)
                return 'saved'
            except ValidationError:
                return 'rejected'
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(move, self.freezer, sibling), pool.submit(move, sibling, self.freezer)]
            self.assertCountEqual([job.result(timeout=20) for job in jobs], ['saved', 'rejected'])
        self.assertFalse(LocationClosure.objects.filter(depth__gt=0, ancestor_id=models_F('descendant_id')).exists())

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_stale_updates_cannot_overwrite_each_other(self):
        barrier = Barrier(2)

        def edit(name):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                save_article(self.admin, {'name': name}, pk=self.article.pk, expected=1)
                return 'saved'
            except Conflict:
                return 'conflict'
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(edit, name) for name in ('Première saisie', 'Seconde saisie')]
            self.assertCountEqual([job.result(timeout=20) for job in jobs], ['saved', 'conflict'])
        self.article.refresh_from_db()
        self.assertEqual(self.article.version, 2)

    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_duplicate_manufacturer_references_are_rejected(self):
        barrier = Barrier(2)

        def create(code):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                save_article(self.admin, {'code': code, 'name': code, 'category': self.category,
                             'base_unit': self.unit, 'manufacturer': self.party, 'manufacturer_reference': 'DUP-1'})
                return 'saved'
            except (ValidationError, IntegrityError):
                return 'rejected'
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(create, code) for code in ('DUPA', 'DUPB')]
            self.assertCountEqual([job.result(timeout=20) for job in jobs], ['saved', 'rejected'])
        self.assertEqual(Article.objects.filter(manufacturer_reference='DUP-1').count(), 1)


    @skipUnlessDBFeature('has_select_for_update')
    def test_database_blocks_raw_history_mutation_and_nonfinite_values(self):
        from django.db import DatabaseError
        event = AuditEvent.objects.latest('id')
        for operation in ('UPDATE erp_auditevent SET reason = %s WHERE id = %s',
                          'DELETE FROM erp_auditevent WHERE reason <> %s AND id = %s'):
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(operation, ['tamper', event.pk])
        price = record_price(self.admin, self.article, {'unit': self.unit, 'amount': Decimal('5'),
                             'observed_on': date(2026, 9, 1), 'source': 'Test source'})
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE erp_priceobservation SET amount = %s WHERE id = %s', [9, price.pk])
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE erp_unit SET factor = 'NaN' WHERE id = %s", [self.unit.pk])
        price.refresh_from_db()
        self.assertEqual(price.amount, Decimal('5'))


class ERPUpgradeTests(TransactionTestCase):
    def test_additive_migrations_preserve_existing_requests_and_profiles(self):
        from django.db.migrations.executor import MigrationExecutor
        from core.models import Request
        executor = MigrationExecutor(connection)
        target = [node for node in executor.loader.graph.leaf_nodes() if node[0] == 'erp']
        executor.migrate([('erp', None)])
        try:
            user = get_user_model().objects.create_user(username='erp-upgrade-user', role='REQUESTER', organization='Institution existante')
            samples = [{'sample_code': 'HISTORICAL-01', 'unmapped_field': 'preserved'}]
            request = Request.objects.create(display_id='IBK-ERP-UPGRADE', title='Projet historique', requester=user,
                                             channel='IBTIKAR', status='SUBMITTED', sample_table=samples)
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            request.refresh_from_db()
            user.refresh_from_db()
            self.assertEqual(request.sample_table, samples)
            self.assertEqual(user.organization, 'Institution existante')
            self.assertEqual(Article.objects.count(), 0)
            self.assertEqual(Location.objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(target)
