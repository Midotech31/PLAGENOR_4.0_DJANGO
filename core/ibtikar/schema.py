from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
from pathlib import Path


@lru_cache(maxsize=1)
def definitions():
    return json.loads(Path(__file__).with_name('definitions.json').read_text(encoding='utf-8'))


def get_schema(code):
    value = definitions()['services'].get(code)
    return deepcopy(value) if value else None


def schema_digest(schema):
    return hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def label(value, language='fr'):
    if isinstance(value, dict):
        return value.get(language.split('-')[0], value.get('fr', ''))
    return str(value)


def empty(value):
    return value is None or value == '' or value == [] or value == {}


def matches(rule, local, parameters=None, samples=None, active_fields=None):
    if not rule:
        return True
    if 'any' in rule:
        return any(matches(x, local, parameters, samples, active_fields) for x in rule['any'])
    if 'all' in rule:
        return all(matches(x, local, parameters, samples, active_fields) for x in rule['all'])
    if 'any_row' in rule:
        return any(matches(rule['any_row'], row, parameters) for row in (samples or []))
    scope = parameters if rule.get('scope') == 'parameters' else local
    key = rule.get('field')
    if active_fields is not None and rule.get('scope', 'local') == 'local' and key not in active_fields:
        return False
    value = (scope or {}).get(key)
    values = value if isinstance(value, list) else [value]
    return any(v in rule.get('in', []) for v in values)


def active_names(fields, values, parameters=None, samples=None):
    from graphlib import CycleError, TopologicalSorter

    def dependencies(rule):
        if not rule or 'any_row' in rule or rule.get('scope') == 'parameters':
            return set()
        if 'field' in rule:
            return {rule['field']}
        return {name for child in rule.get('all', rule.get('any', [])) for name in dependencies(child)}

    specs = {field['name']: field for field in fields}
    graph = {name: dependencies(field.get('when')) for name, field in specs.items()}
    active = set()
    try:
        for name in TopologicalSorter(graph).static_order():
            if name in specs and matches(specs[name].get('when'), values, parameters, samples, active):
                active.add(name)
    except CycleError as exc:
        raise ValueError('Cyclic field dependencies') from exc
    return active

def computed_values(fields, values):
    result = dict(values)
    for spec in fields:
        if spec.get('calculation') == 'length':
            sequence = str(values.get('sequence') or '')
            result[spec['name']] = len(sequence) if sequence else None
        elif spec.get('calculation') == 'gc':
            sequence = str(values.get('sequence') or '')
            result[spec['name']] = (str((Decimal(sum(c in 'GC' for c in sequence))
                                       * 100 / len(sequence)).quantize(Decimal('0.01')))
                                    if sequence and set(sequence) <= set('ACGT') else None)
    return result


def display_value(spec, value, language='fr'):
    if empty(value):
        return label({'fr': 'Non renseigné', 'en': 'Not provided', 'ar': 'غير مذكور'}, language)
    options = {str(x['value']): label(x['label'], language) for x in spec.get('options', [])}
    if isinstance(value, list):
        return ' ; '.join(options.get(str(x), str(x)) for x in value)
    if isinstance(value, bool):
        return label({'fr': 'Oui' if value else 'Non', 'en': 'Yes' if value else 'No',
                      'ar': 'نعم' if value else 'لا'}, language)
    return options.get(str(value), str(value))


def project_group(fields, values, language='fr', parameters=None, samples=None, include_empty=False):
    values = computed_values(fields, values or {})
    active = active_names(fields, values, parameters, samples)
    rows = []
    for f in fields:
        if f['name'] not in active:
            continue
        value = values.get(f['name'])
        if empty(value) and not f.get('required') and f['type'] != 'computed' and not (include_empty and f.get('document_blank')):
            continue
        rows.append({'name': f['name'], 'label': label(f['label'], language),
                     'value': value, 'display': display_value(f, value, language), 'all_options': bool(f.get('all_options')),
                     'options': [{'label': label(o['label'], language),
                                  'selected': o['value'] in (value if isinstance(value, list) else [value])}
                                 for o in f.get('options', [])]})
    return rows


def projection(schema, applicant, parameters, samples, staff=None, language='fr', print_blank_staff=False):
    active_parameters = active_data(schema, 'parameters', parameters)
    active_samples = []
    for row in samples:
        active = active_names(schema['samples'], row, active_parameters)
        active_samples.append({k: v for k, v in row.items() if k in active})
    direction = parameters.get('sequencing_mode')
    read_count = len(samples) * (2 if direction == 'both' else 1) if direction in ('forward', 'reverse', 'both') else None
    return {
        'service_code': schema['service_code'], 'title': label(schema['title'], language),
        'version': schema['version'], 'source_version': schema['source_version'],
        'applicant': project_group(schema['applicant'], applicant, language),
        'parameters': project_group(schema['parameters'], parameters, language, samples=active_samples),
        'samples': [project_group(schema['samples'], row, language, active_parameters) for row in samples],
        'staff': project_group(schema['staff'], staff or {}, language, include_empty=print_blank_staff),
        'sample_count': len(samples), 'read_count': read_count,
        'notices': [label(x, language) for x in schema.get('notices', [])],
    }


def active_data(schema, group, values, parameters=None, samples=None):
    names = active_names(schema[group], values, parameters, samples)
    return {k: v for k, v in values.items() if k in names}


def schema_for_service(service):
    if service is None:
        schema = get_schema('EGTP-PSM')
        schema.update(service_code='', version='', title={k: v for k, v in zip(('fr','en','ar'), ('Prestation non renseignée', 'Service not provided', 'الخدمة غير مذكورة'))}, source={}, notices=[], parameters=[], samples=[])
        return schema
    schema = get_schema(service.code)
    if schema is None:
        schema = get_schema('EGTP-PSM')
        schema['service_code'] = service.code
        schema['source_version'] = 'Configuration PLAGENOR'
        schema['source'] = {'kind': 'administrator-defined'}
        schema['title'] = {lang: getattr(service, 'name_' + lang, None) or service.name for lang in ('fr', 'en', 'ar')}
        schema['parameters'] = [f for f in schema['parameters'] if f['name'] not in ('service_kind', 'service_kind_other')]
    open_choices = {'pcr_kit', 'extraction_kit', 'size_marker', 'purification_method'}
    for custom in service.custom_fields.all().order_by('sort_order', 'pk'):
        group = 'samples' if custom.field_category == 'sample_column' else 'parameters'
        existing = next((f for f in schema[group] if f['name'] == custom.name), None)
        if existing and custom.name not in open_choices:
            continue
        spec = existing or {'name': custom.name, 'required': custom.required, 'owner': 'requester'}
        spec = deepcopy(spec)
        spec['label'] = {lang: getattr(custom, 'label_' + lang, None) or custom.label for lang in ('fr', 'en', 'ar')}
        spec['type'] = {'enum': 'choice', 'number': 'decimal', 'boolean': 'choice',
                        'string': 'text'}.get(custom.field_type, 'text')
        options = custom.options or []
        if custom.field_type == 'boolean':
            spec['options'] = [{'value': 'yes', 'label': {'fr': 'Oui', 'en': 'Yes', 'ar': 'نعم'}},
                               {'value': 'no', 'label': {'fr': 'Non', 'en': 'No', 'ar': 'لا'}}]
        elif options:
            spec['options'] = [{'value': str(x), 'label': {'fr': str(x), 'en': str(x), 'ar': str(x)}} for x in options]
        if custom.conditional_logic:
            spec['when'] = {'any': [{'field': r['trigger_field'], 'in': [r['trigger_value']]}
                                   for r in custom.conditional_logic if r.get('trigger_field') and 'trigger_value' in r]}
        spec['source'] = f'ServiceFormField:{custom.pk}'
        spec['price_sensitive'] = bool(custom.affects_pricing)
        spec['configured_field'] = True
        if existing:
            schema[group][schema[group].index(existing)] = spec
        else:
            schema[group].append(spec)
    return schema
