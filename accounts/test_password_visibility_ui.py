from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class PasswordVisibilityContractTests(SimpleTestCase):
    def test_every_password_template_uses_a_base_with_global_visibility_controls(self):
        template_root = Path(settings.BASE_DIR) / "templates"
        password_templates = []
        for path in template_root.rglob("*.html"):
            source = path.read_text(encoding="utf-8")
            if 'type="password"' not in source:
                continue
            password_templates.append(path)
            first_line = source.splitlines()[0].strip()
            self.assertIn("{% extends", first_line, path)
            self.assertTrue(
                "base.html" in first_line or "base_public.html" in first_line,
                f"{path} must inherit a base that loads the global password visibility control",
            )
        self.assertTrue(password_templates)

    def test_both_application_bases_load_the_shared_visibility_script(self):
        template_root = Path(settings.BASE_DIR) / "templates"
        for name in ("base.html", "base_public.html"):
            source = (template_root / name).read_text(encoding="utf-8")
            self.assertIn("js/password-visibility.js", source)
            self.assertIn("data-password-toggle-label", source)

    def test_visibility_script_handles_current_and_dynamic_password_fields(self):
        source = (
            Path(settings.BASE_DIR) / "static" / "js" / "password-visibility.js"
        ).read_text(encoding="utf-8")
        self.assertIn('input[type="password"]', source)
        self.assertIn("MutationObserver", source)
        self.assertIn("aria-pressed", source)
