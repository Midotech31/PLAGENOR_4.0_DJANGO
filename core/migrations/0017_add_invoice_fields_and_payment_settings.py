# Generated manually for invoice workflow feature

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_add_hidden_from_archive'),
    ]

    operations = [
        # Add invoice fields to Request model
        migrations.AddField(
            model_name='request',
            name='generated_invoice',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='invoices/generated/',
                verbose_name='Generated Invoice (Excel)'
            ),
        ),
        migrations.AddField(
            model_name='request',
            name='invoice_downloaded_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Invoice Downloaded At'
            ),
        ),
        migrations.AddField(
            model_name='request',
            name='invoice_sent_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Invoice Sent At'
            ),
        ),
        migrations.AddField(
            model_name='request',
            name='signed_invoice',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='invoices/signed/',
                verbose_name='Signed Invoice'
            ),
        ),
        
        # Create PaymentSettings model
        migrations.CreateModel(
            name='PaymentSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bank_account', models.CharField(
                    blank=True,
                    default='',
                    help_text='Account number for bank transfers',
                    max_length=100,
                    verbose_name='Bank Account Number'
                )),
                ('beneficiary_name', models.CharField(
                    blank=True,
                    default='',
                    help_text='Name of the account holder',
                    max_length=200,
                    verbose_name='Beneficiary Name'
                )),
                ('bank_name', models.CharField(
                    blank=True,
                    default='',
                    help_text='Name of the bank',
                    max_length=200,
                    verbose_name='Bank Name'
                )),
                ('payment_instructions', models.TextField(
                    blank=True,
                    default='',
                    help_text='Additional instructions for making payment (free text)',
                    verbose_name='Payment Instructions'
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payment_settings_updates',
                    to='accounts.user'
                )),
            ],
            options={
                'verbose_name': 'Payment Settings',
                'verbose_name_plural': 'Payment Settings',
                'db_table': 'payment_settings',
            },
        ),
    ]
