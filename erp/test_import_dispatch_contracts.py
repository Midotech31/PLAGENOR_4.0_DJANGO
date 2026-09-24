"""Import dispatch and delegated scope checks fail closed on inconsistent data."""
from types import SimpleNamespace
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from erp.models import Capability
from erp.services.bulk_imports import _execute, _permissions
from erp.test_operations import OperationFixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ImportDispatchContracts(OperationFixtures, TestCase):
    def test_unknown_dispatch_domain_and_cyclic_location_scope_are_rejected(self):
        with self.assertRaisesRegex(ValidationError, 'Domaine d’import inconnu'):
            _execute(self.ops, SimpleNamespace(kind='UNKNOWN'), {'data': {}})
        self.grant(Capability.EDIT_STORAGE)
        rows = [{'row': 2, 'data': {'code': 'CYCLE-A', 'parent_code': 'CYCLE-B'}},
                {'row': 3, 'data': {'code': 'CYCLE-B', 'parent_code': 'CYCLE-A'}}]
        batch = SimpleNamespace(kind='LOCATIONS', payload=rows)
        with self.assertRaises(PermissionDenied):
            _permissions(self.operator, batch, rows[0])
