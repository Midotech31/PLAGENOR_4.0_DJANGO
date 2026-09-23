from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase

from erp import alert_views, import_views, preparation_views, safety_views, consumption_views
from erp.test_operations import OperationFixtures


class ControllerErrorCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, method="get", path="/", data=None, user=None):
        req = getattr(self.factory, method)(path, data=data or {})
        req.user = user or self.ops
        return req

    def form(self, cleaned=None):
        obj = MagicMock()
        obj.is_valid.return_value = True
        obj.cleaned_data = cleaned or {}
        return obj

    def test_import_access_template_and_preview_error_paths(self):
        with self.assertRaises(PermissionDenied):
            import_views.batches(self.outsider)
        with self.assertRaises(Http404):
            import_views.template_download(self.request(), "UNKNOWN")

        upload = MagicMock(name="upload")
        upload.name = "coverage.csv"
        upload.read.return_value = b"code;name\nX;Y\n"
        form = self.form({"file": upload, "key": "k", "kind": "CATALOG", "reason": "coverage"})
        with patch.object(import_views, "ImportUploadForm", return_value=form),              patch.object(import_views, "preview_import", side_effect=ValidationError("invalid import")),              patch.object(import_views, "add_validation") as add,              patch.object(import_views, "batches", return_value=[]),              patch.object(import_views, "render", return_value=HttpResponse("import")):
            response = import_views.import_home(self.request("post", data={"x":"1"}))
        self.assertEqual(response.status_code, 200)
        add.assert_called_once()

    def test_import_detail_and_cancel_surface_service_validation(self):
        batch = SimpleNamespace(pk=1, version=0, payload=[], report={}, filename="x.csv")
        apply_form = self.form({"expected_version": 0, "confirmed": True})
        with patch.object(import_views, "batches", return_value=MagicMock()),              patch.object(import_views, "get_object_or_404", return_value=batch),              patch.object(import_views, "require_batch"),              patch.object(import_views, "ImportApplyForm", return_value=apply_form),              patch.object(import_views, "apply_import", side_effect=ValidationError("apply")),              patch.object(import_views, "add_validation") as add,              patch.object(import_views, "render", return_value=HttpResponse("detail")):
            response = import_views.import_detail(self.request("post", data={"x":"1"}), 1)
        self.assertEqual(response.status_code, 200)
        add.assert_called_once()

        cancel_form = self.form({"expected_version": 0, "reason": "cancel"})
        with patch.object(import_views, "batches", return_value=MagicMock()),              patch.object(import_views, "get_object_or_404", return_value=batch),              patch.object(import_views, "require_batch"),              patch.object(import_views, "ImportCancelForm", return_value=cancel_form),              patch.object(import_views, "cancel_import", side_effect=ValidationError("cancel")),              patch.object(import_views, "add_validation") as add,              patch.object(import_views, "render", return_value=HttpResponse("cancel")):
            response = import_views.import_cancel(self.request("post", data={"x":"1"}), 1)
        self.assertEqual(response.status_code, 200)
        add.assert_called_once()

    def test_alert_policy_and_action_error_paths(self):
        policy_obj = SimpleNamespace(
            dormant_days=30, receipt_pending_days=2, occupancy_percent=80,
            overstock_multiplier=2, digest_enabled=True, version=0,
            expiry_days=[180, 90, 30],
        )
        form = self.form({
            "expected_version": 0, "expiry_days": [180], "dormant_days": 30,
            "receipt_pending_days": 2, "occupancy_percent": 80,
            "overstock_multiplier": 2, "digest_enabled": True,
        })
        with patch.object(alert_views, "require_manager"),              patch.object(alert_views, "policy", return_value=policy_obj),              patch.object(alert_views, "AlertPolicyForm", return_value=form),              patch.object(alert_views, "save_policy", side_effect=ValidationError("policy")),              patch.object(alert_views, "add_validation") as add,              patch.object(alert_views, "render", return_value=HttpResponse("policy")):
            self.assertEqual(alert_views.alert_policy(self.request("post", data={"x":"1"})).status_code, 200)
            add.assert_called_once()

        with patch.object(alert_views, "has_access", return_value=False):
            with self.assertRaises(PermissionDenied):
                alert_views.alert_action(self.request(), "missing")
        with patch.object(alert_views, "has_access", return_value=True),              patch.object(alert_views, "collect_alerts", return_value={"alerts":[]}):
            with self.assertRaises(Http404):
                alert_views.alert_action(self.request(), "missing")

        row = {"signature":"sig","label":"L","message":"M"}
        action_form = self.form({"reason":"work","assignee":None})
        with patch.object(alert_views, "has_access", return_value=True),              patch.object(alert_views, "collect_alerts", return_value={"alerts":[row]}),              patch.object(alert_views, "AlertActionForm", return_value=action_form),              patch.object(alert_views, "acknowledge", side_effect=ValidationError("ack")),              patch.object(alert_views, "add_validation") as add,              patch.object(alert_views, "render", return_value=HttpResponse("action")):
            self.assertEqual(alert_views.alert_action(self.request("post", data={"x":"1"}), "sig").status_code, 200)
            add.assert_called_once()

    def test_safety_target_document_and_configuration_error_paths(self):
        with patch.object(safety_views, "require_target", side_effect=ValidationError("target")):
            with self.assertRaises(Http404):
                safety_views._target(self.ops, "article", self.article.pk)

        target = self.article
        with patch.object(safety_views, "_target", side_effect=[target, PermissionDenied()]),              patch.object(safety_views, "target_cost_access", return_value=True),              patch.object(safety_views, "render", return_value=HttpResponse("docs")):
            response = safety_views.document_list(self.request(), "article", self.article.pk)
        self.assertEqual(response.status_code, 200)

        file = MagicMock()
        file.name = "sds.pdf"
        file.read.return_value = b"%PDF-1.4"
        doc_form = self.form({"file":file, "title":"SDS", "kind":"SDS", "financial":False, "documented_on":None, "source":"source"})
        with patch.object(safety_views, "_target", return_value=target),              patch.object(safety_views.forms, "DocumentForm", return_value=doc_form),              patch.object(safety_views, "attach_document", side_effect=ValidationError("document")),              patch.object(safety_views, "add_validation") as add,              patch.object(safety_views, "render", return_value=HttpResponse("upload")):
            self.assertEqual(safety_views.document_upload(self.request("post", data={"x":"1"}), "article", self.article.pk).status_code, 200)
            add.assert_called_once()

        for view_name, form_name, service_name, instance in (
            ("hazard_edit", "HazardForm", "save_hazard_tag", SimpleNamespace(pk=1, version=0)),
            ("rule_edit", "StorageRuleForm", "save_storage_rule", SimpleNamespace(pk=1, version=0)),
        ):
            form = self.form({"expected_version":0, "code":"X"})
            with patch.object(safety_views, "require_manager"),                  patch.object(safety_views, "get_object_or_404", return_value=instance),                  patch.object(safety_views.forms, form_name, return_value=form),                  patch.object(safety_views, service_name, side_effect=ValidationError("blocked")),                  patch.object(safety_views, "add_validation") as add,                  patch.object(safety_views, "render", return_value=HttpResponse("form")):
                response = getattr(safety_views, view_name)(self.request("post", data={"x":"1"}), 1)
            self.assertEqual(response.status_code, 200)
            add.assert_called_once()

    def test_preparation_and_consumption_list_guard_paths(self):
        with patch.object(preparation_views, "is_manager", return_value=False),              patch.object(preparation_views, "grants") as grants:
            grants.return_value.exists.return_value = False
            with self.assertRaises(PermissionDenied):
                preparation_views.preparation_create(self.request(user=self.operator))

        form = self.form({"key":"x"})
        ingredient = SimpleNamespace(cleaned_data={"container": self.container if hasattr(self, "container") else None})
        formset = MagicMock()
        formset.is_valid.return_value = True
        formset.__iter__.return_value = iter([ingredient])
        with patch.object(preparation_views, "PreparationForm", return_value=form),              patch.object(preparation_views, "IngredientFormSet", return_value=formset),              patch.object(preparation_views, "prepare_stock", side_effect=ValidationError("prep")),              patch.object(preparation_views, "add_validation") as add,              patch.object(preparation_views, "render", return_value=HttpResponse("prep")):
            self.assertEqual(preparation_views.preparation_create(self.request("post", data={"x":"1"})).status_code, 200)
            add.assert_called_once()

        with self.assertRaises(PermissionDenied):
            consumption_views.run_list(self.request(user=self.outsider))
        with patch.object(consumption_views, "run_scope", return_value=MagicMock()),              patch.object(consumption_views, "render", return_value=HttpResponse("runs")):
            self.assertEqual(consumption_views.run_list(self.request(path="/?q=test")).status_code, 200)
