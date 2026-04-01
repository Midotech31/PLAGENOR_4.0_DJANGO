# accounts/migrations/0008_add_user_position.py
# Migration: Add position and department fields to User model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_add_milestone_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='position',
            field=models.CharField(
                blank=True,
                choices=[
                    ('etudiant_doctorant', 'Étudiant/Doctorant'),
                    ('chercheur', 'Chercheur'),
                    ('mca', 'MCA'),
                    ('mcb', 'MCB'),
                    ('professeur', 'Professeur'),
                    ('ingenieur', 'Ingénieur'),
                    ('technicien', 'Technicien'),
                    ('autre', 'Autre'),
                ],
                max_length=50,
                verbose_name='Position / Fonction'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='department',
            field=models.CharField(
                blank=True, 
                default='', 
                max_length=200, 
                verbose_name='Department'
            ),
        ),
    ]
