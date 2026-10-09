"""Controlled additions to canonical tables; source assets and managed schedules stay immutable."""
import copy

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from erp.cdc.catalog import document, profile
from erp.cdc.schedule_adapter import managed_ids
from .cdc import _dossier, _revision
from .common import check_version


def editable_table(family, table_id, source_row):
    table = next((table for table in profile(family)['tables'] if table['id'] == table_id), None)
    managed_paragraphs, managed = managed_ids(family)
    if (table is None or table_id in managed or table['nested'] or table['part'] != 'word/document.xml'
            or not 0 < source_row < len(table['rows']) or not table['rows'][source_row]['cloneable']):
        raise ValidationError(_('Cette ligne structurelle ou gérée ne peut pas être dupliquée ici. Utilisez les lots, articles ou informations du dossier.'))
    return table


@transaction.atomic
def add_table_row(user, pk, *, expected, table_id, source_row, after_row, cells, reason):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    editable_table(dossier.family, table_id, source_row)
    if not reason.strip():
        raise ValidationError(_('Justifiez la modification du tableau documentaire.'))
    data = copy.deepcopy(dossier.data)
    data.setdefault('rows', {}).setdefault(table_id, []).append(
        {'source_row': source_row, 'after_row': after_row, 'cells': cells})
    # Check the OOXML operation itself before persisting, including empty-cell anchors.
    document(dossier.family).generate(table_edits=data['rows'])
    dossier.data = data
    return _revision(user, dossier, reason)


@transaction.atomic
def remove_table_row(user, pk, *, expected, table_id, index, reason):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    data = copy.deepcopy(dossier.data)
    rows = data.get('rows', {}).get(table_id, [])
    if not reason.strip() or not 0 <= index < len(rows):
        raise ValidationError(_('Sélectionnez une ligne ajoutée et justifiez son retrait.'))
    rows.pop(index)
    dossier.data = data
    return _revision(user, dossier, reason)
