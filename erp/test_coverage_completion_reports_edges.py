from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from erp.services.reports import Report, export_report, stock_value_estimate


class ReportEdgeCoverageTests(SimpleTestCase):
    def test_export_refuses_over_100000_rows(self):
        queryset = MagicMock()
        queryset.count.return_value = 100001
        dataset = Report("Too large", ["Value"], queryset, lambda obj: [obj])
        with self.assertRaises(ValidationError):
            export_report(dataset, BytesIO())

    def test_export_preserves_native_numeric_cells(self):
        queryset = MagicMock()
        queryset.count.return_value = 1
        queryset.iterator.return_value = iter([1])
        dataset = Report("Numeric", ["Value"], queryset, lambda obj: [obj])
        output = BytesIO()
        self.assertEqual(export_report(dataset, output), 1)
        self.assertGreater(len(output.getvalue()), 0)

    def test_stock_value_uses_purchase_price_fallback(self):
        category = SimpleNamespace(pk=1)
        article = SimpleNamespace(category=category)
        lot = SimpleNamespace(article=article)
        row = SimpleNamespace(
            lot=lot, location=SimpleNamespace(pk=2), quantity=Decimal("3"),
            price=None, purchase_price=Decimal("10"), purchase_factor=Decimal("2"),
            price_currency="DZD",
        )
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.select_related.return_value = qs
        qs.annotate.return_value = qs
        qs.iterator.return_value = iter([row])
        with patch("erp.services.reports._stock", return_value=qs),              patch("erp.services.reports._filter", return_value=qs),              patch("erp.services.reports.permitted", return_value=True):
            result = stock_value_estimate(SimpleNamespace(), {})
        self.assertEqual(result["currencies"]["DZD"], Decimal("15"))
        self.assertEqual(result["unpriced_containers"], 0)
        self.assertEqual(result["hidden_containers"], 0)
