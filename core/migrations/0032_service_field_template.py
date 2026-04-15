# Generated migration for ServiceFieldTemplate model
from django.db import migrations, models
import django.db.models.deletion


def create_field_templates_from_services(apps, schema_editor):
    """Populate ServiceFieldTemplate from existing service fields in DB."""
    Service = apps.get_model('core', 'Service')
    ServiceFormField = apps.get_model('core', 'ServiceFormField')
    ServiceFieldTemplate = apps.get_model('core', 'ServiceFieldTemplate')
    
    for service in Service.objects.prefetch_related('form_fields').all():
        fields = list(service.form_fields.all())
        if not fields:
            continue
        
        fields_data = []
        for field in fields:
            fields_data.append({
                'field_category': field.field_category,
                'name': field.name,
                'label': field.label,
                'label_fr': field.label_fr,
                'label_en': field.label_en,
                'field_type': field.field_type,
                'options': field.options or [],
                'choices_json': field.choices_json or [],
                'order': field.order,
                'sort_order': field.sort_order,
                'required': field.required,
                'help_text_fr': field.help_text_fr or '',
                'help_text_en': field.help_text_en or '',
                'conditional_logic': field.conditional_logic or [],
                'affects_pricing': field.affects_pricing,
                'price_modifier_type': field.price_modifier_type,
                'price_modifier_value': str(field.price_modifier_value) if field.price_modifier_value else None,
                'option_pricing': field.option_pricing or {},
                'condition_note_fr': field.condition_note_fr,
                'condition_note_en': field.condition_note_en,
                'max_selections': field.max_selections,
                'channel': field.channel,
            })
        
        if fields_data:
            ServiceFieldTemplate.objects.create(
                name=f"Template: {service.name}",
                description=f"Champs par défaut pour le service {service.code}",
                fields=fields_data,
                applicable_services=[service.code],
                source_service=service,
                is_active=True,
            )


def reverse_migration(apps, schema_editor):
    """Remove all field templates on reverse."""
    ServiceFieldTemplate = apps.get_model('core', 'ServiceFieldTemplate')
    ServiceFieldTemplate.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_add_max_selections_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceFieldTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Ex: "Champs échantillons standard", "Champs analyse PCR"', max_length=200, verbose_name='Nom du modèle')),
                ('description', models.TextField(blank=True, default='', help_text='Description optionnelle du modèle', verbose_name='Description')),
                ('fields', models.JSONField(default=list, help_text='JSON containing field definitions', verbose_name='Configuration des champs')),
                ('applicable_services', models.JSONField(default=list, help_text='List of service codes this template can be applied to (empty = all)', verbose_name='Services applicables')),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
                ('is_default_for_new', models.BooleanField(default=False, help_text='Use as default template when creating new services', verbose_name='Par défaut pour nouveaux services')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_templates', to='accounts.memberprofile')),
                ('source_service', models.ForeignKey(blank=True, help_text='Service used as source for this template', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='field_templates', to='core.service', verbose_name='Service source')),
            ],
            options={
                'verbose_name': 'Modèle de champs',
                'verbose_name_plural': 'Modèles de champs',
                'db_table': 'service_field_templates',
                'ordering': ['-is_default_for_new', 'name'],
            },
        ),
        migrations.RunPython(
            create_field_templates_from_services,
            reverse_migration,
        ),
    ]
