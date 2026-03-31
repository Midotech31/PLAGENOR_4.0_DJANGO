# Generated migration to add performance indexes
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_citation_acknowledged'),
        ('accounts', '0005_must_change_password'),
        ('notifications', '__first__'),
    ]

    operations = [
        # Indexes for Request model - commonly filtered fields
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['channel'], name='request_chann_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['status'], name='request_status_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['created_at'], name='request_created_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['updated_at'], name='request_updated_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['display_id'], name='request_display_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['archived'], name='request_arch_idx'),
        ),
        # Composite indexes for common query patterns
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['channel', 'archived'], name='request_ch_arch_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['channel', 'status'], name='request_ch_stat_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['status', 'created_at'], name='request_stat_cr_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['assigned_to', 'status'], name='request_asgn_stat_idx'),
        ),
        migrations.AddIndex(
            model_name='request',
            index=models.Index(fields=['requester', 'created_at'], name='request_req_cr_idx'),
        ),
        
        # Indexes for RequestHistory model
        migrations.AddIndex(
            model_name='requesthistory',
            index=models.Index(fields=['request', 'created_at'], name='reqhist_req_cr_idx'),
        ),
        
        # Indexes for Invoice model
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['payment_status'], name='invoice_paystat_idx'),
        ),
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['client', 'created_at'], name='invoice_cli_cr_idx'),
        ),
    ]
