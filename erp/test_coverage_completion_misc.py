import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from erp import permissions
from erp.management.commands import send_erp_alert_digest
from erp.models import Capability, StockContainer
from erp.services.access import save_grant
from erp.services.preparations import prepare_stock
from erp.templatetags import erp_permissions
from erp.test_operations import OperationFixtures


class PermissionTagCoverageTests(SimpleTestCase):
    def test_request_permission_tags_cover_denials_and_success(self):
        user = Mock()
        request = Mock(pk=uuid.uuid4(), archived=False, status="SUBMITTED")
        with patch.object(erp_permissions, "is_team", return_value=False):
            self.assertFalse(erp_permissions.can_store_request(user, request))
            self.assertFalse(erp_permissions.can_operate_request(user, request))
        grants = Mock()
        grants.return_value.exists.return_value = False
        with patch.object(erp_permissions, "is_team", return_value=True),              patch.object(erp_permissions, "is_manager", return_value=False),              patch.object(erp_permissions, "grants", grants):
            self.assertFalse(erp_permissions.can_store_request(user, request))
        scope = Mock()
        scope.return_value.filter.return_value.exists.return_value = True
        with patch.object(erp_permissions, "is_team", return_value=True),              patch.object(erp_permissions, "is_manager", return_value=True),              patch.object(erp_permissions, "request_scope", scope):
            self.assertTrue(erp_permissions.can_store_request(user, request))
            self.assertTrue(erp_permissions.can_operate_request(user, request))
        request.archived = True
        with patch.object(erp_permissions, "is_team", return_value=True):
            self.assertFalse(erp_permissions.can_operate_request(user, request))


class MiscOperationalCoverageTests(OperationFixtures, TestCase):
    def test_operational_scope_global_grant_returns_unfiltered_queryset(self):
        container, _, _ = self.receive()
        save_grant(self.admin, {
            "user": self.operator,
            "capability": Capability.VIEW_STOCK,
        })
        scoped = permissions.operational_scope(
            StockContainer.objects.all(), self.operator
        )
        self.assertIn(container, scoped)

    def test_alert_digest_command_username_guards_and_delivery_count(self):
        with self.assertRaises(CommandError):
            call_command("send_erp_alert_digest", username="missing-member")
        out = Mock()
        command = send_erp_alert_digest.Command(stdout=out)
        with patch.object(send_erp_alert_digest, "has_access", return_value=True),              patch.object(send_erp_alert_digest, "send_digest", return_value=Mock()):
            command.handle(username=self.operator.username)
        self.assertTrue(out.write.called)

    def test_internal_preparation_replay_returns_existing_preparation(self):
        source, _, _ = self.receive()
        key = uuid.uuid4()
        values = dict(
            key=key, article=self.article, location=self.freezer,
            lot_code="PREP-LOT", container_code="PREP-CONT",
            amount=1, unit=self.unit, prepared_on=timezone.localdate(),
            protocol_reference="SOP-001", reason="Préparation contrôlée",
            ingredients=[{"container": source, "amount": 2, "unit": self.unit}],
        )
        first = prepare_stock(self.admin, **values)
        second = prepare_stock(self.admin, **values)
        self.assertEqual(second.pk, first.pk)
