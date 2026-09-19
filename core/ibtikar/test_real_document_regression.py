from types import SimpleNamespace
import os

from django.test import SimpleTestCase

from core.ibtikar.legacy import legacy_initial
from core.ibtikar.schema import get_schema, projection
from documents.ibtikar_canonical import build_document
from documents.ibtikar_reference import reference_content


def collect_text(document):
    values = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                values.append(cell.text)
    return "\n".join(values)


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
            declared_ibtikar_balance=190000,
        )
        schema = get_schema("EGTP-IMT")
        legacy = legacy_initial(request, schema)
        project = projection(
            schema,
            legacy["applicant"],
            legacy["parameters"],
            legacy["samples"],
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
            legacy=legacy["legacy_data"],
        )
        text = collect_text(document)

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

        preview_dir = os.environ.get("PLAGENOR_DOCUMENT_PREVIEW_DIR")
        if preview_dir:
            destination = Path(preview_dir)
            destination.mkdir(parents=True, exist_ok=True)
            document.save(destination / "IBTIKAR_MALDI_CAS_REEL_CORRIGE.docx")
