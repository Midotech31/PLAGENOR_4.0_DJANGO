from types import SimpleNamespace
from pathlib import Path
import os
from unittest.mock import patch

from django.test import SimpleTestCase

from core.ibtikar.legacy import _display_value, document_initial, legacy_initial
from core.ibtikar.schema import get_schema, projection
from documents.ibtikar_canonical import build_document
from documents.ibtikar_reference import reference_content
from documents.views import _cached_doc_path


def collect_text(document):
    values = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                values.append(cell.text)
    return "\n".join(values)


class LegacyDisplayHelperCoverageTests(SimpleTestCase):
    def test_legacy_initial_maps_guest_contact_fallbacks(self):
        schema = get_schema("EGTP-IMT")
        request = SimpleNamespace(
            requester_data={},
            service_params={},
            sample_table=[],
            pricing={},
            title="Projet invité",
            guest_name="Demandeur invité",
            guest_email="invite@example.test",
            guest_phone="+213 555 111 222",
        )
        values = legacy_initial(request, schema)["applicant"]
        self.assertEqual(values["full_name"], "Demandeur invité")
        self.assertEqual(values["email"], "invite@example.test")
        self.assertEqual(values["phone"], "+213 555 111 222")

    def test_human_readable_legacy_value_shapes(self):
        self.assertEqual(_display_value(None), "")
        self.assertEqual(_display_value(True), "Oui")
        self.assertEqual(_display_value(False), "Non")
        self.assertEqual(_display_value(["A", "", "B"]), "A ; B")
        self.assertEqual(
            _display_value({"analysis_mode": "Simple", "active": True}),
            "Analysis mode : Simple ; Active : Oui",
        )
        self.assertEqual(_display_value("Texte"), "Texte")


class RealMALDIFormRegressionTests(SimpleTestCase):
    def test_historical_maldi_request_is_projected_without_internal_json(self):
        requester = SimpleNamespace(
            username="demandeur",
            get_full_name=lambda: "Demandeur Réel",
            organization="ESSBO",
            laboratory="Laboratoire de microbiologie",
            student_level="Doctorant",
            email="demandeur@example.test",
            phone="+213 555 000 001",
            supervisor="Pr Encadrant",
            supervisor_email="encadrant@example.test",
            ibtikar_id="IBT-USER-001",
            ibtikar_declared_balance=190000,
        )
        request = SimpleNamespace(
            requester=requester,
            requester_data={},
            service_params={
                "pathogenic": "true",
                "analysis_mode": "Simple",
                "project_title": "..",
                "analysis_frame": "Projet de doctorat",
                "maldi_target_type": "Disposable",
                "fresh_culture_available": "true",
            },
            sample_table=[{
                "remarks": "",
                "sample_code": "1",
                "organism_type": "Mould",
                "sample_origin": "Food",
                "culture_medium": "",
                "isolation_date": "",
                "culture_conditions": "",
            }],
            pricing={},
            title="..",
            guest_name="",
            guest_email="",
            guest_phone="",
            declared_ibtikar_balance=None,
        )
        schema = get_schema("EGTP-IMT")
        historical = legacy_initial(request, schema)
        self.assertNotIn("email", historical["applicant"])
        legacy = document_initial(request, schema)
        project = projection(
            schema,
            legacy["document_applicant"],
            legacy["parameters"],
            legacy["document_samples"],
            language="fr",
            print_blank_staff=True,
        )
        document = build_document(
            project,
            {
                "number": "IBK-2026-0001",
                "date": "10/09/2026",
                "external_reference": "",
                "revision": "Non applicable — demande historique",
                "draft": False,
                "operator_name": "",
            },
            "fr",
            legacy=legacy["legacy_display"],
        )
        text = collect_text(document)
        title_band = next(
            table for table in document.tables
            if "FICHE DE DEMANDE IBTIKAR" in " ".join(cell.text for cell in table.rows[0].cells)
        )
        self.assertEqual(len(title_band.rows[0].cells), 4)
        self.assertIn("Service demandé", title_band.rows[0].cells[3].text)
        self.assertIn(project["title"], title_band.rows[0].cells[3].text)
        self.assertIn(project["service_code"], title_band.rows[0].cells[3].text)
        self.assertIn("1. INFORMATIONS GÉNÉRALES", text)
        self.assertIn("2. DEMANDEUR ET PROJET", text)

        project_title = next(
            row for row in project["applicant"] if row["name"] == "project_title"
        )
        self.assertEqual(project_title["display"], "Non renseigné")

        for expected in (
            "Demandeur Réel",
            "ESSBO",
            "Laboratoire de microbiologie",
            "Doctorant",
            "demandeur@example.test",
            "+213 555 000 001",
            "Pr Encadrant",
            "encadrant@example.test",
            "IBT-USER-001",
            "190000",
            "☑ Projet de doctorat",
            "☑ Moisissure",
            "☑ Alimentaire",
            "☑ Pathogène",
            "☑ Oui",
            "☑ À usage unique",
            "☑ Simple",
            "V02 / 02.11.2025",
        ):
            self.assertIn(expected, text)

        self.assertNotIn(
            "Fournir des colonies fraîches, pures et bien isolées, sur un milieu adapté",
            text,
        )
        self.assertNotIn(
            "Le demandeur certifie que les échantillons ont été collectés, manipulés et transférés",
            text,
        )

        for forbidden in (
            "requester_data",
            "service_params",
            "sample_table",
            '"pathogenic"',
            "{{ANALYSIS_MODE_LABEL}}",
            "alimenatire",
        ):
            self.assertNotIn(forbidden, text)

        source = reference_content("EGTP-IMT")
        source_text = "\n".join(source["guidance"])
        self.assertNotIn("{{ANALYSIS_MODE_LABEL}}", source_text)
        self.assertNotIn("alimenatire", source_text)
        self.assertIn("paraffiné/alimentaire", source_text)
        self.assertIn("4 °C", source_text)
        self.assertIn("8 °C", source_text)
        self.assertIn("MALDI-TOF MS. Sans culture fraîche,", source_text)

        preview_dir = os.environ.get("PLAGENOR_DOCUMENT_PREVIEW_DIR")
        if preview_dir:
            destination = Path(preview_dir)
            destination.mkdir(parents=True, exist_ok=True)
            document.save(destination / "IBTIKAR_MALDI_CAS_REEL_CORRIGE.docx")


class IbtikarDocumentCacheVersionTests(SimpleTestCase):
    def test_corrected_generator_invalidates_canonical2_cache(self):
        request = SimpleNamespace(
            updated_at=None,
            display_id="IBK-CACHE",
            pk="cache-pk",
            service_id=None,
        )
        with patch(
            "core.ibtikar.models.IbtikarSubmission.objects.filter"
        ) as query, patch(
            "documents.views._block_signature", return_value="0"
        ), patch(
            "documents.views._service_fields_signature", return_value="0"
        ):
            query.return_value.only.return_value.first.return_value = None
            path = _cached_doc_path(request, "IBTIKAR_FORM")
        self.assertIn("__canonical4_hybrid__", path.name)
        self.assertNotIn("__canonical3__", path.name)
