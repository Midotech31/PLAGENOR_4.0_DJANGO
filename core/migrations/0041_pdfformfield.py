from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0040_homepage_homepagesection_homepageblock'),
    ]

    operations = [
        migrations.CreateModel(
            name='PDFFormField',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pdf_target', models.CharField(choices=[('ibtikar_form', 'Formulaire IBTIKAR'), ('platform_note', 'Note de Plateforme'), ('reception_form', 'Formulaire de Réception')], max_length=20)),
                ('scope_type', models.CharField(choices=[('global', 'Tous les services'), ('service', 'Service spécifique')], default='global', max_length=10)),
                ('name', models.CharField(max_length=100)),
                ('label_fr', models.CharField(max_length=255)),
                ('label_en', models.CharField(blank=True, max_length=255)),
                ('field_kind', models.CharField(choices=[('text_line', 'Ligne de texte'), ('text_block', 'Bloc de texte'), ('checkbox', 'Case à cocher'), ('signature', 'Zone de signature'), ('separator', 'Séparateur / ligne'), ('section_title', 'Titre de section'), ('table_row', 'Ligne de tableau'), ('image', 'Image / Logo')], max_length=20)),
                ('default_value', models.TextField(blank=True)),
                ('options', models.JSONField(blank=True, default=dict)),
                ('order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('service', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='pdf_fields', to='core.service')),
            ],
            options={
                'verbose_name': 'Champ PDF',
                'verbose_name_plural': 'Champs PDF',
                'ordering': ['pdf_target', 'order', 'pk'],
                'unique_together': {('pdf_target', 'scope_type', 'service', 'name')},
            },
        ),
    ]
