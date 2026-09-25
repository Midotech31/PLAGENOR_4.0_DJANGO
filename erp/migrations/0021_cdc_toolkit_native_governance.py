from decimal import Decimal
import uuid

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('erp', '0020_cdc_archive_and_procurement_requirement_links'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CdcRequirement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('position', models.PositiveSmallIntegerField(default=1)),
                ('kind', models.CharField(
                    choices=[
                        ('MANDATORY', 'Obligatoire'),
                        ('MINIMUM', 'Minimum'),
                        ('PREFERRED', 'Souhaitable'),
                        ('SCORED', 'Notée'),
                        ('INFORMATIONAL', 'Informative'),
                        ('ELIMINATORY', 'Éliminatoire'),
                    ],
                    max_length=16,
                    verbose_name="Nature de l’exigence",
                )),
                ('statement', models.TextField(verbose_name='Exigence')),
                ('evidence', models.TextField(blank=True, verbose_name='Preuve exigée')),
                ('verification_method', models.TextField(blank=True, verbose_name='Méthode de vérification / réception')),
                ('justification', models.TextField(blank=True, verbose_name='Justification')),
                ('active', models.BooleanField(default=True, verbose_name='Retenir cette exigence')),
                ('item', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='requirements',
                    to='erp.cdcitem',
                )),
            ],
            options={'ordering': ['position', 'id']},
        ),
        migrations.AddConstraint(
            model_name='cdcrequirement',
            constraint=models.UniqueConstraint(
                fields=('item', 'position'),
                name='erp_cdc_requirement_position',
            ),
        ),
        migrations.CreateModel(
            name='CdcCriterion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=40, verbose_name='Code')),
                ('title', models.CharField(max_length=255, verbose_name='Critère')),
                ('method', models.CharField(
                    choices=[
                        ('PROPORTIONAL', 'Proportionnelle'),
                        ('BINARY', 'Binaire'),
                        ('INVERSE_PRICE', 'Prix inverse'),
                    ],
                    default='PROPORTIONAL',
                    max_length=16,
                    verbose_name='Méthode',
                )),
                ('weight', models.DecimalField(
                    decimal_places=2,
                    max_digits=5,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0')),
                        django.core.validators.MaxValueValidator(Decimal('100')),
                    ],
                    verbose_name='Pondération (points)',
                )),
                ('threshold', models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    max_digits=8,
                    null=True,
                    verbose_name='Seuil éventuel',
                )),
                ('eliminatory', models.BooleanField(default=False, verbose_name='Critère éliminatoire')),
                ('evidence', models.TextField(blank=True, verbose_name='Justificatif / preuve attendue')),
                ('position', models.PositiveSmallIntegerField(default=1)),
                ('active', models.BooleanField(default=True, verbose_name='Retenir ce critère')),
                ('dossier', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='criteria',
                    to='erp.cdcdossier',
                )),
                ('lot', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='criteria',
                    to='erp.cdclot',
                )),
            ],
            options={'ordering': ['lot_id', 'position', 'id']},
        ),
        migrations.AddConstraint(
            model_name='cdccriterion',
            constraint=models.UniqueConstraint(
                fields=('dossier', 'code'),
                name='erp_cdc_criterion_code',
            ),
        ),
        migrations.AddConstraint(
            model_name='cdccriterion',
            constraint=models.CheckConstraint(
                condition=models.Q(weight__gte=0, weight__lte=100),
                name='erp_cdc_criterion_weight',
            ),
        ),
        migrations.CreateModel(
            name='CdcClause',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(
                    max_length=32,
                    unique=True,
                    validators=[django.core.validators.RegexValidator('^[A-Z0-9][A-Z0-9._-]{0,31}$')],
                    verbose_name='Code interne',
                )),
                ('name', models.CharField(max_length=255, verbose_name='Désignation française')),
                ('name_en', models.CharField(blank=True, max_length=255, verbose_name='Désignation anglaise')),
                ('name_ar', models.CharField(blank=True, max_length=255, verbose_name='Désignation arabe')),
                ('active', models.BooleanField(default=True, verbose_name='Actif')),
                ('title', models.CharField(max_length=255, verbose_name='Intitulé de la clause')),
            ],
            options={'ordering': ['code']},
        ),
        migrations.CreateModel(
            name='CdcClauseRevision',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('number', models.PositiveIntegerField()),
                ('text_fr', models.TextField(verbose_name='Texte français')),
                ('text_en', models.TextField(blank=True, verbose_name='Texte anglais')),
                ('text_ar', models.TextField(blank=True, verbose_name='Texte arabe')),
                ('source_reference', models.CharField(max_length=500, verbose_name='Source / référence')),
                ('status', models.CharField(
                    choices=[
                        ('DRAFT', 'Brouillon'),
                        ('ACTIVE', 'Validée / active'),
                        ('RETIRED', 'Retirée'),
                    ],
                    default='DRAFT',
                    max_length=8,
                )),
                ('sha256', models.CharField(max_length=64)),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('clause', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='revisions',
                    to='erp.cdcclause',
                )),
            ],
            options={'ordering': ['-number']},
        ),
        migrations.AddConstraint(
            model_name='cdcclauserevision',
            constraint=models.UniqueConstraint(
                fields=('clause', 'number'),
                name='erp_cdc_clause_revision_number',
            ),
        ),
        migrations.AddField(
            model_name='cdcclause',
            name='active_revision',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='active_for',
                to='erp.cdcclauserevision',
            ),
        ),
        migrations.CreateModel(
            name='CdcClauseSelection',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('position', models.PositiveSmallIntegerField(default=1)),
                ('mandatory', models.BooleanField(default=False, verbose_name='Clause obligatoire pour ce dossier')),
                ('note', models.CharField(blank=True, max_length=500, verbose_name='Note interne')),
                ('active', models.BooleanField(default=True, verbose_name='Retenir cette clause')),
                ('dossier', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='clause_selections',
                    to='erp.cdcdossier',
                )),
                ('revision', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='selections',
                    to='erp.cdcclauserevision',
                )),
            ],
            options={'ordering': ['position', 'id']},
        ),
        migrations.AddConstraint(
            model_name='cdcclauseselection',
            constraint=models.UniqueConstraint(
                fields=('dossier', 'revision'),
                name='erp_cdc_clause_selection_unique',
            ),
        ),
        migrations.CreateModel(
            name='CdcReviewDecision',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stage', models.CharField(
                    choices=[
                        ('TECHNICAL', 'Revue technique'),
                        ('ADMIN_LEGAL', 'Revue administrative et juridique'),
                        ('FINANCIAL', 'Revue financière'),
                    ],
                    max_length=16,
                )),
                ('outcome', models.CharField(
                    choices=[
                        ('APPROVED', 'Approuvée'),
                        ('CHANGES', 'Corrections demandées'),
                    ],
                    max_length=12,
                )),
                ('comment', models.CharField(max_length=1000, verbose_name='Compte rendu')),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('dossier', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='review_decisions',
                    to='erp.cdcdossier',
                )),
                ('revision', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='review_decisions',
                    to='erp.cdcrevision',
                )),
            ],
            options={'ordering': ['created_at', 'id']},
        ),
        migrations.AddConstraint(
            model_name='cdcreviewdecision',
            constraint=models.UniqueConstraint(
                fields=('revision', 'stage'),
                name='erp_cdc_review_stage_unique',
            ),
        ),
    ]
