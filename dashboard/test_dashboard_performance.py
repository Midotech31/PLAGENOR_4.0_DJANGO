"""Real dashboard metrics and bounded aggregate query work."""
import json
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from core.models import Request


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class OperationalDashboardMetricsTests(TestCase):
    def test_metrics_preserve_all_channels_states_and_rating_distribution(self):
        user = User.objects.create_user('ops-metrics', role='PLATFORM_ADMIN')
        self.client.force_login(user)
        Request.objects.bulk_create([
            Request(display_id='METRIC-' + str(i), channel=channel, status=status,
                    service_rating=rating)
            for i, (channel, status, rating) in enumerate([
                ('IBTIKAR', 'SUBMITTED', 1), ('IBTIKAR', 'COMPLETED', 5),
                ('GENOCLAB', 'REPORT_UPLOADED', 5), ('GENOCLAB', 'CANCELLED', None),
                ('GENOCLAB', 'VALIDATION_PEDAGOGIQUE', 3),
            ])
        ])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('dashboard:admin_ops'))
        self.assertEqual(response.status_code, 200)
        for key, value in {
            'total_requests': 5, 'pending_count': 3, 'ibtikar_count': 2,
            'genoclab_count': 3, 'completed_count': 1, 'total_ratings': 4,
            'avg_rating': 3.5, 'rating_distribution': {1: 1, 2: 0, 3: 1, 4: 0, 5: 2},
            'rating_percentages': {1: 25.0, 2: 0.0, 3: 25.0, 4: 0.0, 5: 50.0},
        }.items():
            self.assertEqual(response.context[key], value)
        table = connection.ops.quote_name(Request._meta.db_table)
        metrics = [q['sql'] for q in queries if table in q['sql']
                   and 'COUNT(' in q['sql'].upper() and 'GROUP BY' not in q['sql'].upper()]
        print('OPS_METRICS_QUERY_EVIDENCE=' + json.dumps({
            'request_metric_queries': len(metrics), 'http_queries': len(queries),
            'database': connection.vendor, 'requests': 5,
        }, sort_keys=True))
        # Includes three other budget/template counts, alongside the two grouped
        # metric queries. Before consolidation this HTTP request needed 14.
        self.assertLessEqual(len(metrics), 5)

    def test_empty_dashboard_preserves_zero_values_and_default_bar_scales(self):
        user = User.objects.create_user('ops-empty-metrics', role='PLATFORM_ADMIN')
        self.client.force_login(user)
        response = self.client.get(reverse('dashboard:admin_ops'))
        for key in ('total_requests', 'pending_count', 'ibtikar_count', 'genoclab_count',
                    'completed_count', 'total_ratings', 'avg_rating'):
            self.assertEqual(response.context[key], 0)
        self.assertEqual(response.context['rating_distribution'], dict.fromkeys(range(1, 6), 0))
        self.assertEqual(response.context['rating_percentages'], dict.fromkeys(range(1, 6), 0))
