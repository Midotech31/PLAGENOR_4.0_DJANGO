"""Read-only evaluation grids built exclusively from one immutable CDC revision."""
import io
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _, get_language_bidi
from openpyxl import Workbook
from openpyxl.cell.cell import IllegalCharacterError
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from erp.cdc.lot_catalog import fingerprint
from erp.models import CdcCriterion, CdcRequirement


def _sheet(book, title, headers, rows, widths):
    sheet = book.create_sheet(title)
    for number, row in enumerate((headers, *rows), 1):
        for column, value in enumerate(row, 1):
            cell = sheet.cell(number, column)
            if value is None or isinstance(value, (int, Decimal)):
                cell.value = value
            else:
                value = str(value)
                if len(value) > 32767:
                    raise ValidationError(_('Un texte de la révision dépasse la capacité d’une cellule Excel.'))
                cell.value = value
                # Preserve source text exactly, including leading =, +, -, @.
                # Explicit string cells cannot become spreadsheet formulas.
                cell.data_type = 's'
            cell.alignment = Alignment(vertical='top', wrap_text=True)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='173B63')
    for column, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.rightToLeft = get_language_bidi()
    sheet.print_title_rows = '1:1'
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    return sheet


def criteria_workbook(revision):
    """Export technical snapshots without live joins or internal estimates."""
    if fingerprint({'document': revision.data, 'estimates': revision.estimates}) != revision.sha256:
        raise ValidationError(_('L’intégrité de la révision CDC ne peut pas être confirmée.'))
    try:
        data = revision.data
        lots = {lot['id']: lot for lot in data.get('lot_catalog', {}).get('lots', [])}
        items = {(lot['id'], item['key']): item for lot in lots.values() for item in lot['items']}
        methods, kinds = dict(CdcCriterion.Method.choices), dict(CdcRequirement.Kind.choices)
        criteria = []
        for row in data.get('criteria', []):
            weight = Decimal(row['weight'])
            threshold = Decimal(row['threshold']) if row['threshold'] is not None else None
            if not weight.is_finite() or (threshold is not None and not threshold.is_finite()):
                raise ValueError('Non-finite score')
            criteria.append((row['code'], lots.get(row['lot'], {'name': row['lot']})['name'] if row['lot'] else _('Global'),
                row['title'], methods[row['method']], weight, threshold,
                _('Oui') if row['eliminatory'] else _('Non'), row['evidence'], row['position']))
        requirements = [(row['id'], lots[row['lot']]['name'], row['item_key'],
            items[(row['lot'], row['item_key'])]['designation'], kinds[row['kind']], row['statement'],
            row['evidence'], row['verification_method'], row['justification'], row['position'])
            for row in data.get('requirements', [])]
        book = Workbook()
        book.remove(book.active)
        _sheet(book, _('Critères'), (_('Code'), _('Lot'), _('Critère'), _('Méthode'),
            _('Pondération (points)'), _('Seuil éventuel'), _('Critère éliminatoire'),
            _('Justificatif / preuve attendue'), _('Position')), criteria,
            (16, 36, 48, 24, 18, 18, 18, 48, 12))
        _sheet(book, _('Exigences'), (_('Identifiant de l’exigence'), _('Lot'), _('Clé de l’article'),
            _('Désignation'), _('Nature de l’exigence'), _('Exigence'), _('Preuve exigée'),
            _('Méthode de vérification / réception'), _('Justification'), _('Position')),
            requirements, (38, 36, 28, 48, 24, 60, 48, 48, 48, 12))
        _sheet(book, _('Traçabilité'), (_('Champ'), _('Valeur')),
            [(_('Référence CDC'), data['reference']), (_('Révision'), revision.number),
             (_('Identifiant de révision'), str(revision.pk)), (_('Empreinte SHA-256'), revision.sha256),
             (_('Créée le'), revision.created_at.isoformat()), (_('Auteur'), str(revision.actor_id))],
            (32, 80))
        output = io.BytesIO()
        book.save(output)
        return output.getvalue()
    except (KeyError, TypeError, AttributeError, ValueError, InvalidOperation, IllegalCharacterError) as error:
        raise ValidationError(_('Les données CDC structurées de la révision sont invalides.')) from error
