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
}
VALUE_ALIASES = {
    'sequencing_mode': {'Forward': 'forward', 'Reverse': 'reverse', 'Forward + Reverse': 'both', 'F': 'forward', 'F+R': 'both'},
    'submitted_type': {'Purified': 'purified_pcr', 'Non-purified': 'unpurified_pcr'},
    'analysis_mode': {'Simple': 'single', 'Duplicate': 'duplicate', 'Triplicate': 'triplicate'},
    'maldi_target': {'Reusable': 'reusable', 'Disposable': 'disposable'},
    'fresh_culture': {'true': 'yes', 'false': 'no', True: 'yes', False: 'no'},
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
    params = dict(req.service_params or {})
    common = dict(req.requester_data or {})
    common.update({k: v for k, v in params.items() if k not in common})
    common.setdefault('project_title', req.title)
    for name, value in [('guest_name', req.guest_name), ('guest_email', req.guest_email), ('guest_phone', req.guest_phone)]:
        if value:
            common.setdefault(name, value)
    return {'applicant': mapped_values(schema['applicant'], common),
            'parameters': mapped_values(schema['parameters'], params),
            'samples': [mapped_values(schema['samples'], row) for row in (req.sample_table or [])],
            'legacy_data': {'requester_data': deepcopy(req.requester_data),
                            'service_params': deepcopy(req.service_params),
                            'sample_table': deepcopy(req.sample_table), 'pricing': deepcopy(req.pricing)}}
