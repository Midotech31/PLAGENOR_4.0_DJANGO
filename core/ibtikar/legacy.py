from copy import deepcopy


FIELD_ALIASES = {
    'full_name': ['full_name', 'guest_name'], 'institution': ['institution', 'organization'],
    'status': ['status', 'student_level'], 'email': ['email', 'guest_email'],
    'phone': ['phone', 'guest_phone'], 'declared_balance': ['declared_balance', 'declared_ibtikar_balance'],
    'sample_code': ['sample_code', 'code'],
    'origin': ['origin', 'sample_origin', 'source_origine_de_l_echantillon', 'origine_des_acides_nucleiques', 'source_d_isolement'],
    'gene': ['gene', 'nom_du_gene', 'nom_du_gene_cible'],
    'amplicon_bp': ['amplicon_bp', 'taille_du_gene'],
    'primer_sequences': ['primer_sequences', 'sequences_des_amorces_utilisees'],
    'remarks': ['remarks', 'remarques_particulieres'],
    'sample_type': ['sample_type', 'type_d_echantillon', 'type_de_l_echantillon'],
    'collection_date': ['collection_date', 'date_de_prelevement'],
    'storage': ['storage', 'condition_de_stockage_etat_de_l_echantil', 'conditions_de_stockage_initiales'],
    'extraction_method': ['extraction_method', 'methode_d_extraction_utilisee'],
    'extraction_date': ['extraction_date', 'date_de_l_extraction'],
    'primer_name': ['primer_name', 'nom_de_l_amorces'],
    'sequence': ['sequence', 'sequence_nucleotidique'],
    'accession': ['accession', 'numero_d_accession_du_gene'],
    'organism_type': ['organism_type', 'type_de_microorganisme'],
    'culture_medium': ['culture_medium', 'milieu_de_culture_approprie'],
    'culture_conditions': ['culture_conditions', 'conditions_de_culture'],
    'drying_level': ['drying_level', 'niveau_de_desiccation'],
    'submitted_type': ['submitted_type', 'sample_purity'],
    'maldi_target': ['maldi_target', 'maldi_target_type'],
    'fresh_culture': ['fresh_culture', 'fresh_culture_available'],
    'risk_status': ['risk_status', 'pathogenic'],
}
VALUE_ALIASES = {
    'sequencing_mode': {'Forward': 'forward', 'Reverse': 'reverse', 'Forward + Reverse': 'both', 'F': 'forward', 'F+R': 'both'},
    'submitted_type': {'Purified': 'purified_pcr', 'Non-purified': 'unpurified_pcr'},
    'analysis_mode': {'Simple': 'single', 'Duplicate': 'duplicate', 'Triplicate': 'triplicate'},
    'maldi_target': {'Reusable': 'reusable', 'Disposable': 'disposable'},
    'fresh_culture': {'true': 'yes', 'false': 'no', 'True': 'yes', 'False': 'no',
                      True: 'yes', False: 'no'},
    'risk_status': {'true': 'pathogenic', 'false': 'standard',
                    'True': 'pathogenic', 'False': 'standard',
                    True: 'pathogenic', False: 'standard',
                    'Pathogenic': 'pathogenic', 'Clinical': 'clinical'},
    'product_recovery': {'true': 'yes', 'false': 'no', True: 'yes', False: 'no'},
    'organism_type': {'Bacterium': 'bacterium', 'Yeast': 'yeast', 'Mould': 'mould'},
    'origin': {'Environmental': 'environmental', 'Food': 'food', 'Hospital / Clinical': 'clinical'},
    'dna_type': {'Plasmidic': 'plasmid', 'Chromosomal': 'chromosomal', 'Genomic': 'genomic'},
    'nucleic_acid_type': {'DNA': 'dna', 'RNA': 'rna'},
    'drying_level': {'Primaire': 'primary', 'Secondaire': 'secondary'},
    'sequencing_depth': {'Standard': 'standard', 'High': 'high'},
    'analysis_frame': {'PFE Classique': 'pfe_classic', 'Projet de doctorat': 'phd', 'Autre': 'other'},
    'delivery_format': {'Dried': 'dried'},
}


def mapped_values(specs, values):
    result = {}
    for spec in specs:
        name = spec['name']
        for alias in FIELD_ALIASES.get(name, [name]):
            if alias not in values:
                continue
            value = deepcopy(values[alias])
            if not isinstance(value, (dict, list)):
                value = VALUE_ALIASES.get(name, {}).get(value, value)
            if spec.get('type') == 'choice' and value not in [o['value'] for o in spec.get('options', [])]:
                continue
            result[name] = value
            break
    return result


def legacy_initial(req, schema):
    """Return the historical payload exactly as stored plus canonical mappings.

    This function deliberately does not infer missing requester/account values:
    the migration/edit contract depends on preserving the historical payload
    without silent backfill.
    """
    params = dict(req.service_params or {})
    common = dict(req.requester_data or {})
    common.update({k: v for k, v in params.items() if k not in common})
    common.setdefault('project_title', req.title)
    for name, value in (
        ('guest_name', req.guest_name),
        ('guest_email', req.guest_email),
        ('guest_phone', req.guest_phone),
    ):
        if value:
            common.setdefault(name, value)
    return {
        'applicant': mapped_values(schema['applicant'], common),
        'parameters': mapped_values(schema['parameters'], params),
        'samples': [
            mapped_values(schema['samples'], row)
            for row in (req.sample_table or [])
        ],
        'legacy_data': {
            'requester_data': deepcopy(req.requester_data),
            'service_params': deepcopy(req.service_params),
            'sample_table': deepcopy(req.sample_table),
            'pricing': deepcopy(req.pricing),
        },
    }


def _used_aliases(specs):
    values = set()
    for spec in specs:
        name = spec['name']
        values.update(FIELD_ALIASES.get(name, [name]))
    return values


def _display_value(value):
    if value in (None, '', [], {}):
        return ''
    if isinstance(value, bool):
        return 'Oui' if value else 'Non'
    if isinstance(value, list):
        return ' ; '.join(str(item) for item in value if item not in (None, ''))
    if isinstance(value, dict):
        return ' ; '.join(
            f"{str(key).replace('_', ' ').capitalize()} : {_display_value(item)}"
            for key, item in value.items() if _display_value(item)
        )
    return str(value)


def _legacy_display_rows(req, schema):
    """Human-readable rows for historical values not represented canonically."""
    rows = []
    requester_used = _used_aliases(schema['applicant'])
    param_used = (
        requester_used
        | _used_aliases(schema['parameters'])
        | _used_aliases(schema['samples'])
    )
    sample_used = _used_aliases(schema['samples'])

    def add_mapping(values, used, prefix=''):
        for key, value in (values or {}).items():
            if key in used:
                continue
            display = _display_value(value)
            if not display:
                continue
            label = str(key).replace('_', ' ').strip().capitalize()
            rows.append({
                'name': f'legacy_{key}',
                'label': f'{prefix}{label}',
                'display': display,
                'value': value,
                'options': [],
                'all_options': False,
            })

    add_mapping(req.requester_data or {}, requester_used)
    add_mapping(req.service_params or {}, param_used)
    for index, sample in enumerate(req.sample_table or [], 1):
        add_mapping(sample, sample_used, prefix=f'Échantillon {index:02d} — ')
    add_mapping(req.pricing or {}, set(), prefix='Tarification historique — ')
    return rows


def document_initial(req, schema):
    """Build document-only values without mutating the historical payload.

    Known account fields may fill otherwise-empty display fields because they
    are authoritative current account data, while legacy_data remains exactly
    as stored. Service-level legacy parameters may also feed sample fields
    where old PLAGENOR versions stored those selections globally.
    """
    initial = legacy_initial(req, schema)
    applicant = deepcopy(initial['applicant'])

    requester = getattr(req, 'requester', None)
    if requester is not None:
        account_values = {
            'full_name': requester.get_full_name() or requester.username,
            'institution': getattr(requester, 'organization', ''),
            'laboratory': getattr(requester, 'laboratory', ''),
            'status': getattr(requester, 'student_level', ''),
            'email': getattr(requester, 'email', ''),
            'phone': getattr(requester, 'phone', ''),
            'supervisor': getattr(requester, 'supervisor', ''),
            'supervisor_email': getattr(requester, 'supervisor_email', ''),
            'ibtikar_id': getattr(requester, 'ibtikar_id', ''),
        }
        declared = getattr(req, 'declared_ibtikar_balance', None)
        if declared is None:
            declared = getattr(requester, 'ibtikar_declared_balance', None)
        account_values['declared_balance'] = declared
        for name, value in mapped_values(schema['applicant'], account_values).items():
            applicant.setdefault(name, value)

    params = dict(req.service_params or {})
    samples = []
    for row in (req.sample_table or []):
        merged = dict(params)
        merged.update(row)
        samples.append(mapped_values(schema['samples'], merged))

    return {
        **initial,
        'document_applicant': applicant,
        'document_samples': samples,
        'legacy_display': _legacy_display_rows(req, schema),
    }
