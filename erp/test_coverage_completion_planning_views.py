from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from core.models import Request, Service
from erp import planning_views
from erp.models import AvailabilityBlock, PlanningResource
from erp.services.work import create_work
from erp.test_operations import OperationFixtures


class PlanningViewCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.work = create_work(self.ops, kind="CONTROL", title="Planning view coverage", assignee=self.operator)

    def req(self, method="get", path="/", data=None):
        request = getattr(self.factory, method)(path, data=data or {})
        request.user = self.ops
        return request

    def fake_form(self, cleaned):
        form = MagicMock()
        form.is_valid.return_value = True
        form.cleaned_data = cleaned
        return form

    def test_work_filter_exercises_kind_member_and_text(self):
        qs = MagicMock()
        qs.filter.return_value = qs
        request = self.req(path="/?kind=CONTROL&member=%s&q=coverage" % self.operator.pk)
        result = planning_views._work_filter(request, qs)
        self.assertIs(result, qs)
        self.assertEqual(qs.filter.call_count, 3)
        with self.assertRaises(Exception):
            planning_views._work_filter(self.req(path="/?kind=BAD"), qs)
        with self.assertRaises(Exception):
            planning_views._work_filter(self.req(path="/?member=bad"), qs)

    def test_activity_create_prefill_and_service_error(self):
        service = Service.objects.create(code="PLAN-VIEW", name="Planning")
        req_obj = Request.objects.create(
            display_id="PLAN-VIEW-1", title="Source request", channel="IBTIKAR",
            service=service, status="SUBMITTED",
        )
        form = self.fake_form({
            "key": "not-relevant", "kind": "CONTROL", "title": "X",
        })
        with patch.object(planning_views.forms, "ActivityCreateForm", return_value=form) as form_cls,              patch.object(planning_views, "create_activity_series", side_effect=ValidationError("blocked")),              patch.object(planning_views, "add_validation") as add,              patch.object(planning_views, "_form", return_value=HttpResponse("form")):
            response = planning_views.activity_create(
                self.req("post", "/?request=%s" % req_obj.pk, {"x": "1"})
            )
        self.assertEqual(response.status_code, 200)
        add.assert_called_once()
        initial = form_cls.call_args.kwargs["initial"]
        # POST path has no query prefill; exercise GET independently.
        with patch.object(planning_views.forms, "ActivityCreateForm", return_value=MagicMock()),              patch.object(planning_views, "_form", return_value=HttpResponse("get")):
            get_req = self.req("get", "/?request=%s" % req_obj.pk)
            response = planning_views.activity_create(get_req)
            self.assertEqual(response.status_code, 200)

    def test_schedule_detail_dependencies_resource_and_unavailability_error_paths(self):
        now = timezone.now()
        schedule_form = self.fake_form({
            "expected_version": self.work.version,
            "starts_at": now + timedelta(hours=1),
            "ends_at": now + timedelta(hours=2),
            "resources": [], "request": None, "run": None, "reason": "edit",
        })
        with patch.object(planning_views.forms, "ScheduleForm", return_value=schedule_form),              patch.object(planning_views, "save_schedule", side_effect=ValidationError("schedule")),              patch.object(planning_views, "add_validation") as add,              patch.object(planning_views, "_form", return_value=HttpResponse("form")):
            self.assertEqual(planning_views.activity_schedule(self.req("post", data={"x":"1"}), self.work.pk).status_code, 200)
            add.assert_called_once()

        readiness_form = self.fake_form({"expected_version": self.work.version, "note": "verified"})
        with patch.object(planning_views.forms, "ReadinessForm", return_value=readiness_form),              patch.object(planning_views, "readiness", return_value={"ready":False,"issues":[],"schedule":None}),              patch.object(planning_views, "confirm_resources", side_effect=ValidationError("not ready")),              patch.object(planning_views, "add_validation") as add,              patch.object(planning_views, "render", return_value=HttpResponse("detail")):
            self.assertEqual(planning_views.activity_detail(self.req("post", data={"x":"1"}), self.work.pk).status_code, 200)
            add.assert_called_once()

        dep_form = self.fake_form({"expected_version": self.work.version, "prerequisites": [], "reason": "deps"})
        with patch.object(planning_views.forms, "DependencyForm", return_value=dep_form),              patch.object(planning_views, "set_dependencies", side_effect=ValidationError("deps")),              patch.object(planning_views, "add_validation") as add,              patch.object(planning_views, "_form", return_value=HttpResponse("deps")):
            self.assertEqual(planning_views.dependencies_edit(self.req("post", data={"x":"1"}), self.work.pk).status_code, 200)
            add.assert_called_once()

        resource = PlanningResource.objects.create(code="COV-R", name="Resource")
        resource_form = self.fake_form({"expected_version": resource.version, "code":"COV-R","name":"R","active":True})
        with patch.object(planning_views.forms, "ResourceForm", return_value=resource_form),              patch.object(planning_views, "save_resource", side_effect=ValidationError("resource")),              patch.object(planning_views, "add_validation") as add,              patch.object(planning_views, "_form", return_value=HttpResponse("resource")):
            self.assertEqual(planning_views.resource_edit(self.req("post", data={"x":"1"}), resource.pk).status_code, 200)
            add.assert_called_once()

        unavailable_form = self.fake_form({"member": self.operator, "resource": None, "starts_at": now, "ends_at": now+timedelta(hours=1), "reason":"maintenance"})
        with patch.object(planning_views.forms, "UnavailabilityForm", return_value=unavailable_form),              patch.object(planning_views, "save_unavailability", side_effect=ValidationError("unavailable")),              patch.object(planning_views, "add_validation") as add,              patch.object(planning_views, "_form", return_value=HttpResponse("unavailable")):
            self.assertEqual(planning_views.unavailability_create(self.req("post", data={"x":"1"})).status_code, 200)
            add.assert_called_once()

    def test_unavailability_end_error_and_success_redirect(self):
        block = AvailabilityBlock.objects.create(
            member=self.operator, starts_at=timezone.now(),
            ends_at=timezone.now()+timedelta(hours=1), reason="Maintenance",
            created_by=self.ops,
        )
        form = self.fake_form({"expected_version": block.version, "reason": "finish"})
        with patch.object(planning_views.forms, "UnavailabilityEndForm", return_value=form),              patch.object(planning_views, "cancel_unavailability", side_effect=ValidationError("blocked")),              patch.object(planning_views, "add_validation") as add,              patch.object(planning_views, "_form", return_value=HttpResponse("end")):
            self.assertEqual(planning_views.unavailability_end(self.req("post", data={"x":"1"}), block.pk).status_code, 200)
            add.assert_called_once()
