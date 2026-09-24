from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('erp', '0021_cdc_toolkit_native_governance'),
    ]

    operations = [
        migrations.AlterField(
            model_name='accessgrant',
            name='capability',
            field=models.CharField(
                choices=[
                    ('view_catalog', 'Consulter le catalogue'),
                    ('edit_catalog', 'Gérer le catalogue'),
                    ('view_storage', 'Consulter les emplacements'),
                    ('edit_storage', 'Gérer les emplacements'),
                    ('view_cost', 'Consulter les coûts'),
                    ('edit_cost', 'Enregistrer les prix'),
                    ('view_stock', 'Consulter le stock'),
                    ('receive_stock', 'Réceptionner le stock'),
                    ('consume_stock', 'Enregistrer les consommations'),
                    ('transfer_stock', 'Transférer le stock'),
                    ('reserve_stock', 'Réserver le stock'),
                    ('control_stock', 'Contrôler les lots et les sorties'),
                    ('inventory', 'Réaliser un inventaire'),
                    ('view_biobank', 'Consulter l’échantillothèque'),
                    ('manage_biobank', 'Gérer l’échantillothèque'),
                    ('view_planning', 'Consulter les besoins prévisionnels'),
                    ('edit_planning', 'Préparer les besoins prévisionnels'),
                    ('review_cdc_technical', 'Effectuer la revue technique des CDC'),
                    ('review_cdc_admin', 'Effectuer la revue administrative et juridique des CDC'),
                    ('review_cdc_financial', 'Effectuer la revue financière des CDC'),
                    ('approve_cdc', 'Approuver définitivement les CDC'),
                ],
                max_length=32,
                verbose_name='Permission',
            ),
        ),
    ]
