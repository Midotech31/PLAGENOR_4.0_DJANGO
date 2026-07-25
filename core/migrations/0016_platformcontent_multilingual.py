"""Phase 3.5 — Reshape PlatformContent for multilingual content.

Schema change: (key PK, value) -> (id PK, key, lang, value) with UNIQUE (key, lang).

The auto-generated migration cannot perform the SQLite PK swap, so the database
operation is hand-crafted per engine while the ORM state is reconciled via
SeparateDatabaseAndState. Existing rows are migrated to lang='fr'.
"""
from django.conf import settings
from django.db import migrations, models


def apply_forward(apps, schema_editor):
    vendor = schema_editor.connection.vendor

    if vendor == 'sqlite':
        schema_editor.execute("""
            CREATE TABLE platform_content_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) NOT NULL,
                lang VARCHAR(10) NOT NULL,
                value TEXT NOT NULL,
                updated_at DATETIME NOT NULL,
                updated_by_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
            );
        """)
        schema_editor.execute("""
            INSERT INTO platform_content_new (key, lang, value, updated_at, updated_by_id)
            SELECT key, 'fr', value, updated_at, updated_by_id FROM platform_content;
        """)
        schema_editor.execute("DROP TABLE platform_content;")
        schema_editor.execute("ALTER TABLE platform_content_new RENAME TO platform_content;")
        schema_editor.execute(
            "CREATE UNIQUE INDEX platform_content_key_lang_uniq ON platform_content (key, lang);"
        )
        schema_editor.execute(
            "CREATE INDEX platform_content_updated_by_id_idx ON platform_content (updated_by_id);"
        )
    elif vendor == 'postgresql':
        schema_editor.execute(
            "ALTER TABLE platform_content DROP CONSTRAINT IF EXISTS platform_content_pkey;"
        )
        schema_editor.execute(
            "ALTER TABLE platform_content ADD COLUMN id BIGSERIAL PRIMARY KEY;"
        )
        schema_editor.execute(
            "ALTER TABLE platform_content ADD COLUMN lang VARCHAR(10) NOT NULL DEFAULT 'fr';"
        )
        schema_editor.execute(
            "ALTER TABLE platform_content "
            "ADD CONSTRAINT platform_content_key_lang_uniq UNIQUE (key, lang);"
        )
    else:
        raise NotImplementedError(f"Unsupported database vendor: {vendor}")


def apply_reverse(apps, schema_editor):
    vendor = schema_editor.connection.vendor

    if vendor == 'sqlite':
        schema_editor.execute("""
            CREATE TABLE platform_content_old (
                key VARCHAR(100) PRIMARY KEY NOT NULL,
                value TEXT NOT NULL,
                updated_at DATETIME NOT NULL,
                updated_by_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
            );
        """)
        schema_editor.execute("""
            INSERT INTO platform_content_old (key, value, updated_at, updated_by_id)
            SELECT key, value, updated_at, updated_by_id FROM platform_content WHERE lang = 'fr';
        """)
        schema_editor.execute("DROP TABLE platform_content;")
        schema_editor.execute("ALTER TABLE platform_content_old RENAME TO platform_content;")
    elif vendor == 'postgresql':
        schema_editor.execute("DELETE FROM platform_content WHERE lang <> 'fr';")
        schema_editor.execute(
            "ALTER TABLE platform_content DROP CONSTRAINT platform_content_key_lang_uniq;"
        )
        schema_editor.execute("ALTER TABLE platform_content DROP COLUMN lang;")
        schema_editor.execute("ALTER TABLE platform_content DROP COLUMN id;")
        schema_editor.execute("ALTER TABLE platform_content ADD PRIMARY KEY (key);")
    else:
        raise NotImplementedError(f"Unsupported database vendor: {vendor}")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_backfill_translation_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(apply_forward, apply_reverse),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name='platformcontent',
                    name='key',
                ),
                migrations.AddField(
                    model_name='platformcontent',
                    name='id',
                    field=models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                    preserve_default=False,
                ),
                migrations.AddField(
                    model_name='platformcontent',
                    name='key',
                    field=models.CharField(default='', max_length=100),
                    preserve_default=False,
                ),
                migrations.AddField(
                    model_name='platformcontent',
                    name='lang',
                    field=models.CharField(
                        choices=[('fr', 'Français'), ('en', 'English'), ('ar', 'العربية')],
                        default='fr',
                        max_length=10,
                    ),
                ),
                migrations.AlterUniqueTogether(
                    name='platformcontent',
                    unique_together={('key', 'lang')},
                ),
            ],
        ),
    ]
