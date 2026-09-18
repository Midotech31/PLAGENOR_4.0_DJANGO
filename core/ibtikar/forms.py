from decimal import Decimal
import json
import re

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory
from django.utils.translation import get_language, gettext as _

from core.ibtikar.schema import active_names, computed_values, empty, label, matches


class RetainedField(forms.Field):
    def validate(self, value):
        if len(str(value)) > 20000:
            raise ValidationError(_('Valeur trop longue.'))


class SequenceField(forms.CharField):
    def to_python(self, value):
        return re.sub(r'\s+', '', super().to_python(value)).upper()

    def validate(self, value):
        super().validate(value)
        if value and not re.fullmatch(r'[ACGTRYSWKMBDHVN]+', value):
            raise ValidationError(_('Utilisez une séquence ADN en orientation 5′→3′ (alphabet IUPAC).'))


class SchemaForm(forms.Form):
    def __init__(self, *args, specs=(), parameters=None, samples=None, existing_files=None, require_complete=True, **kwargs):
        self.specs = specs
        self.parameters = parameters or {}
        self.samples = samples or []
        self.existing_files = existing_files or {}
        self.language = (get_language() or 'fr').split('-')[0]
        super().__init__(*args, **kwargs)
        raw = {}
        for spec in specs:
            key = self.add_prefix(spec['name'])
            if self.is_bound:
                raw[spec['name']] = self.data.getlist(key) if spec['type'] == 'multi' and hasattr(self.data, 'getlist') else self.data.get(key)
            else:
                raw[spec['name']] = self.initial.get(spec['name'])
        self.active = active_names(specs, raw, parameters, samples)
        for spec in specs:
            name = spec['name']
            if spec['type'] == 'computed':
                continue
            required = bool(require_complete and spec['required'] and name in self.active)
            options = [(o['value'], label(o['label'], self.language)) for o in spec.get('options', [])]
            kind = spec['type']
            attr = {'class': 'form-control'}
            if kind == 'multi':
                f = forms.MultipleChoiceField(choices=options, widget=forms.CheckboxSelectMultiple, required=required)
            elif kind == 'choice':
                f = forms.ChoiceField(choices=[('', _('Choisir'))] + options, required=required)
            elif kind == 'consent':
                f = forms.BooleanField(required=required)
            elif kind in ('decimal', 'integer'):
                constraints = {'required': required}
                if spec.get('positive'):
                    constraints['min_value'] = 1 if kind == 'integer' else Decimal('0.000001')
                elif spec.get('nonnegative'):
                    constraints['min_value'] = 0
                if spec.get('maximum') is not None:
                    constraints['max_value'] = spec['maximum']
                f = (forms.IntegerField(**constraints) if kind == 'integer' else
                     forms.DecimalField(max_digits=16, decimal_places=6, **constraints))
                if kind == 'decimal':
                    attr['step'] = 'any'
            elif kind == 'date':
                f = forms.DateField(required=required, input_formats=['%Y-%m-%d'], widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
            elif kind == 'email':
                f = forms.EmailField(required=required, max_length=254)
            elif kind == 'sequence':
                f = SequenceField(required=required, max_length=10000, widget=forms.Textarea(attrs={'rows': 2, 'dir': 'ltr'}))
            elif kind in ('file', 'image'):
                f = forms.FileField(required=required and name not in self.existing_files,
                                    widget=forms.FileInput(attrs={'accept': '.png,.jpg,.jpeg' if kind == 'image' else '.pdf,.png,.jpg,.jpeg'}))
            else:
                f = forms.CharField(required=required, max_length=spec.get('maximum_length', 4000),
                                    widget=forms.Textarea(attrs={'rows': 3}) if kind == 'textarea' else forms.TextInput)
            if name not in self.active and kind not in ('file', 'image'):
                widget = f.widget
                f = RetainedField(required=False, widget=widget)
            f.label = label(spec['label'], self.language)
            f.help_text = label(spec.get('help', ''), self.language)
            f.widget.attrs.update(attr)
            f.ibtikar_spec = spec
            f.exclusive_json = json.dumps(spec.get('exclusive', []))
            f.rule_json = json.dumps(spec.get('when', {}), ensure_ascii=False)
            f.schema_required = spec['required']
            f.existing_file = name in self.existing_files
            f.applicable = name in self.active
            self.fields[name] = f

    def clean(self):
        cleaned = super().clean()
        for spec in self.specs:
            name = spec['name']
            if name not in self.active:
                continue
            value = cleaned.get(name)
            if spec.get('exclusive') and isinstance(value, list):
                if any(x in value for x in spec['exclusive']) and len(value) > 1:
                    self.add_error(name, _('Ce choix ne peut pas être combiné avec une autre option.'))
            if spec['type'] in ('file', 'image') and value:
                from core.uploads import validate_upload
                try:
                    value._ibtikar_original_name = value.name
                    validate_upload(value, 'image' if spec['type'] == 'image' else 'business_document')
                except ValidationError as exc:
                    self.add_error(name, exc)
        return computed_values(self.specs, cleaned)


class SampleFormSet(BaseFormSet):
    def __init__(self, *args, schema=None, parameters=None, **kwargs):
        self.schema = schema or {}
        self.parameters = parameters or {}
        super().__init__(*args, **kwargs)

    def clean(self):
        if any(self.errors):
            return
        rows = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        seen = set()
        for form in rows:
            data = form.cleaned_data
            identity = data.get('sample_code') or (str(data.get('pair_code')) + ':' + str(data.get('direction')) if data.get('pair_code') and data.get('direction') else None)
            if identity and identity in seen:
                form.add_error(None, _('Le code de l’échantillon ou de la paire/orientation est dupliqué.'))
            if identity:
                seen.add(identity)
            for rule in self.schema.get('rules', []):
                if rule['kind'] == 'required_value' and matches(rule.get('when'), data, self.parameters):
                    if data.get(rule['field']) != rule['value']:
                        form.add_error(rule['field'], label(rule['message'], (get_language() or 'fr')))
                elif rule['kind'] == 'risk_consistency':
                    if data.get('origin') == 'clinical' and data.get('risk_status') == 'standard':
                        form.add_error('risk_status', _('Une origine clinique ne peut pas être déclarée standard.'))
                elif rule['kind'] == 'fill_ratio':
                    filled = data.get('fill_volume_ml')
                    nominal = data.get('container_volume_ml')
                    if filled is not None and nominal and Decimal(filled) / Decimal(nominal) > Decimal(rule['maximum']):
                        form.add_error('fill_volume_ml', _('Le remplissage dépasse 50 % du volume nominal du récipient.'))
                elif rule['kind'] == 'minimum_quantity' and data.get('sample_type') == rule['sample_type']:
                    quantity, unit = data.get('quantity'), data.get('quantity_unit')
                    if quantity is not None:
                        conversion = {'g': {'g': '1', 'mg': '0.001'}, 'mL': {'mL': '1', 'uL': '0.001'}}
                        factor = conversion[rule['unit']].get(unit)
                        if factor is None:
                            form.add_error('quantity_unit', _('Cette unité ne permet pas de vérifier la quantité minimale requise.'))
                        elif Decimal(quantity) * Decimal(factor) < Decimal(rule['minimum']):
                            form.add_error('quantity', _('La quantité est inférieure au minimum du formulaire source : %(minimum)s %(unit)s.') % {'minimum': rule['minimum'], 'unit': rule['unit']})


def make_sample_formset(schema, data=None, initial=None, parameters=None, require_complete=True):
    maximum = int(getattr(settings, 'IBTIKAR_MAX_SAMPLE_ROWS', 200))
    factory = formset_factory(SchemaForm, formset=SampleFormSet, extra=0 if initial else 1,
                              can_delete=True, min_num=0, validate_min=False,
                              max_num=maximum, validate_max=True, absolute_max=maximum)
    return factory(data=data, initial=initial, prefix='samples', schema=schema,
                   parameters=parameters,
                   form_kwargs={'specs': schema['samples'], 'parameters': parameters, 'require_complete': require_complete})


def cleaned_samples(formset):
    return [{k: v for k, v in form.cleaned_data.items() if k != 'DELETE'}
            for form in formset if form.cleaned_data and not form.cleaned_data.get('DELETE')]
