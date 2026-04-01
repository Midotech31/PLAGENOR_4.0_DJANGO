# core/migrations/0018_add_pdf_form_fields.py
# Migration: Add PDF form fields for IBTIKAR system

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_add_invoice_fields_and_payment_settings'),
    ]

    operations = [
        # ========================================================================
        # Request model changes
        # ========================================================================
        migrations.AddField(
            model_name='request',
            name='additional_data',
            field=models.JSONField(
                blank=True, 
                default=dict, 
                verbose_name='Additional Data'
            ),
        ),
        migrations.AddField(
            model_name='request',
            name='analysis_framework',
            field=models.CharField(
                blank=True,
                choices=[
                    ('memoire_fin_cycle', 'Mémoire de fin de cycle'),
                    ('these_doctorat', 'Thèse de doctorat'),
                    ('projet_recherche', 'Projet de recherche'),
                    ('habilitation', 'Habilitation universitaire'),
                    ('autre', 'Autre'),
                ],
                max_length=50,
                verbose_name='Analysis Framework'
            ),
        ),
        
        # ========================================================================
        # Service model changes
        # ========================================================================
        migrations.AddField(
            model_name='service',
            name='ibtikar_instructions',
            field=models.TextField(
                blank=True, 
                help_text="'Tres important' warning block text in French"
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='ibtikar_instructions_en',
            field=models.TextField(
                blank=True, 
                help_text="'Very important' warning block text in English"
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='checklist_items',
            field=models.JSONField(
                blank=True, 
                default=list, 
                help_text='PLAGENOR validation checklist items as JSON list of strings'
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='service_code',
            field=models.CharField(
                blank=True, 
                help_text='Official service code (e.g., EGTP-Seq02)', 
                max_length=50, 
                null=True, 
                unique=True
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='form_version',
            field=models.CharField(
                default='V 01', 
                help_text='Form version number (e.g., V 01)', 
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='deliverables',
            field=models.TextField(
                blank=True, 
                help_text='Expected deliverables description'
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='processing_steps',
            field=models.TextField(
                blank=True, 
                help_text='Processing/analysis workflow steps'
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='analysis_workflow',
            field=models.TextField(
                blank=True, 
                help_text='Analysis workflow description'
            ),
        ),
        
        # ========================================================================
        # ServiceFormField model changes
        # ========================================================================
        migrations.AddField(
            model_name='serviceformfield',
            name='field_category',
            field=models.CharField(
                choices=[('sample_table', 'Sample Table Column'), ('additional_info', 'Additional Info Field')],
                default='sample_table',
                help_text='Whether this field is a sample table column or additional info field',
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name='serviceformfield',
            name='label_fr',
            field=models.CharField(
                blank=True, 
                help_text='Label in French', 
                max_length=255
            ),
        ),
        migrations.AddField(
            model_name='serviceformfield',
            name='label_en',
            field=models.CharField(
                blank=True, 
                help_text='Label in English', 
                max_length=255
            ),
        ),
        migrations.AddField(
            model_name='serviceformfield',
            name='choices_json',
            field=models.JSONField(
                blank=True, 
                help_text='Options for dropdown/checkbox as JSON list', 
                null=True
            ),
        ),
        migrations.AddField(
            model_name='serviceformfield',
            name='is_required',
            field=models.BooleanField(
                default=False, 
                help_text='Whether this field is required'
            ),
        ),
        migrations.AddField(
            model_name='serviceformfield',
            name='order',
            field=models.PositiveIntegerField(
                default=0, 
                help_text='Order within the field category'
            ),
        ),
    ]
