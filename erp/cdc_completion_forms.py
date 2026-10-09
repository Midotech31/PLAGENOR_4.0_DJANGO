from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator
from django.utils.translation import gettext_lazy as _

from .cdc.lot_catalog import MAX_ITEMS
from .models import CdcLot, CdcRevision
from .services.cdc import dossier_scope
from .services.cdc_reuse import source_rows
from .work_forms import OperationForm


class RevisionChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return '%s — R%s' % (obj.dossier.reference, obj.number)


def reusable_revisions(user, dossier):
    return CdcRevision.objects.filter(dossier__in=dossier_scope(user), dossier__family=dossier.family).select_related(
        'dossier').only('id', 'number', 'created_at', 'dossier__id', 'dossier__reference').order_by('-created_at', '-number')


class ReuseFilterForm(OperationForm):
    source_revision = RevisionChoice(label=_('Révision source'), queryset=CdcRevision.objects.none(),
        widget=forms.Select(attrs={'id': 'id_filter_revision'}))
    q = forms.CharField(label=_('Rechercher dans les articles'), max_length=200, required=False)


class ReuseSelectionForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    source_revision = forms.ModelChoiceField(queryset=CdcRevision.objects.none(), widget=forms.HiddenInput)
    target_lot = forms.ModelChoiceField(label=_('Lot de destination'), queryset=CdcLot.objects.none())
    selections = forms.MultipleChoiceField(label=_('Articles à réutiliser'), widget=forms.CheckboxSelectMultiple)
    reason = forms.CharField(label=_('Justification'), max_length=500)

    def __init__(self, *args, user, dossier, search='', **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['source_revision'].queryset = reusable_revisions(user, dossier)
        self.fields['target_lot'].queryset = dossier.lots.filter(active=True)
        value = self.data.get('source_revision') if self.is_bound else self.initial.get('source_revision')
        try:
            revision = self.fields['source_revision'].clean(value)
        except forms.ValidationError:
            rows = []
        else:
            source, rows = source_rows(user, revision.pk, dossier.family)
        self.fields['selections'].choices = [(row['selection'], '%s — %s · %s %s' % (
            row['lot_name'], row['designation'], row['quantity'], row['unit']))
            for row in rows if not search or search.casefold() in ' '.join(
                row[field] for field in ('lot_name', 'designation', 'specifications')).casefold()]


class ReuseRowForm(OperationForm):
    selection = forms.CharField(widget=forms.HiddenInput)
    designation = forms.CharField(label=_('Désignation'), max_length=30000)
    specifications = forms.CharField(label=_('Spécifications techniques'), max_length=30000,
        required=False, widget=forms.Textarea)
    unit = forms.CharField(label=_('Unité documentaire'), max_length=100)
    packaging = forms.CharField(label=_('Conditionnement'), max_length=600, required=False)
    quantity = forms.DecimalField(label=_('Quantité prévue'), min_value=Decimal('0.000001'),
        max_digits=18, decimal_places=6)
    details = forms.CharField(label=_('Précisions complémentaires'), max_length=10000,
        required=False, widget=forms.Textarea)
    omit = forms.BooleanField(label=_('Écarter cet article de la copie'), required=False)

    def clean(self):
        values = super().clean()
        # HTML textareas submit CRLF even when their historical text uses LF.
        for field in ('designation', 'specifications', 'packaging', 'details'):
            if field in values:
                values[field] = values[field].replace('\r\n', '\n')
        return values


ReuseRows = forms.formset_factory(ReuseRowForm, extra=0, max_num=MAX_ITEMS,
    validate_max=True, absolute_max=MAX_ITEMS)


class FinancialImportForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    file = forms.FileField(label=_('Classeur financier du dossier'))
    reason = forms.CharField(label=_('Justification et source des prix'), max_length=500)


class TableRowForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    table_id = forms.CharField(widget=forms.HiddenInput)
    source_row = forms.IntegerField(widget=forms.HiddenInput)
    after_row = forms.IntegerField(label=_('Insérer après la ligne du modèle'), min_value=0)
    reason = forms.CharField(label=_('Justification'), max_length=500)

    def __init__(self, *args, table, source_row, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['after_row'].max_value = len(table['rows']) - 1
        self.fields['after_row'].validators.append(MaxValueValidator(len(table['rows']) - 1))
        for index, cell in enumerate(table['rows'][source_row]['cells']):
            self.fields['cell_%s' % index] = forms.CharField(label=_('Cellule %(number)s') % {'number': index + 1},
                max_length=10000, required=False, initial=' '.join(cell['text'].splitlines()))
