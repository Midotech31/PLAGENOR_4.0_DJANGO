# core/migrations/0019_populate_service_form_fields.py
# Data migration: Populate ServiceFormField for all 9 IBTIKAR services

from django.db import migrations


def populate_service_form_fields(apps, schema_editor):
    """Populate ServiceFormField for all 9 IBTIKAR services."""
    
    Service = apps.get_model('core', 'Service')
    ServiceFormField = apps.get_model('core', 'ServiceFormField')
    
    # Get services by code
    services = {s.code: s for s in Service.objects.all()}
    
    # Data for all 9 services
    service_data = {
        # EGTP-Seq02 — Identification Microbienne via le Séquençage
        'EGTP-Seq02': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'type', 'label': "Type d'échantillon", 'label_fr': "Type d'échantillon (Sang, bactérie, tissu animal…)", 'label_en': 'Sample Type (Blood, bacteria, animal tissue...)', 'order': 2},
                {'name': 'date', 'label': 'Date de prélèvement', 'label_fr': 'Date de prélèvement', 'label_en': 'Sampling Date', 'order': 3},
                {'name': 'volume', 'label': 'Volume/Quantité', 'label_fr': 'Volume (µl) / Quantité (g)', 'label_en': 'Volume (µl) / Quantity (g)', 'order': 4},
                {'name': 'storage', 'label': 'Conditions de stockage', 'label_fr': 'Condition de stockage', 'label_en': 'Storage Conditions', 'order': 5},
                {'name': 'state', 'label': "État de l'échantillon", 'label_fr': "État de l'échantillon", 'label_en': 'Sample State', 'order': 6},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 7},
            ],
            'additional_info': [
                {
                    'name': 'extraction_method',
                    'label': 'Méthode extraction',
                    'label_fr': 'Méthode d\'extraction souhaitée',
                    'label_en': 'Requested Extraction Method',
                    'field_type': 'dropdown',
                    'options': ['Méthode classique', 'Kit commercial'],
                    'order': 0,
                },
                {
                    'name': 'pcr_kit',
                    'label': 'Kit PCR',
                    'label_fr': 'Type de kit de PCR',
                    'label_en': 'PCR Kit Type',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 1,
                },
                {
                    'name': 'qc_techniques',
                    'label': 'Techniques QC',
                    'label_fr': 'Techniques de contrôle qualité souhaitées',
                    'label_en': 'Requested QC Techniques',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 2,
                },
                {
                    'name': 'size_marker',
                    'label': 'Marqueur taille',
                    'label_fr': 'Marqueur de taille pour électrophorèse',
                    'label_en': 'Size Marker for Electrophoresis',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 3,
                },
                {
                    'name': 'reading_direction',
                    'label': 'Sens lecture',
                    'label_fr': 'Sens de lecture souhaité',
                    'label_en': 'Requested Reading Direction',
                    'field_type': 'checkbox',
                    'options': ['Forward', 'Reverse', 'Les deux sens'],
                    'order': 4,
                },
            ],
            'checklist': [
                "Échantillons reçus en bon état",
                "Quantité minimale d'échantillon respectée",
                "Mode de conservation/transport respecté",
                "Contrôle qualité d'ADN fourni",
                "Formulaire rempli intégralement",
            ],
            'ibtikar_instructions': (
                "• Chaque échantillon doit être identifié de manière claire et unique.\n"
                "• Le volume minimum requis est de 50 µL par échantillon.\n"
                "• Les échantillons doivent être транспорés à une température de -20°C ou -80°C selon le type.\n"
                "• Tout échantillon non conforme sera rejeté."
            ),
        },
        
        # EGTP-SeqS — Séquençage d'ADN Sanger
        'EGTP-SeqS': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'gene', 'label': 'Nom du gène', 'label_fr': 'Nom du gène', 'label_en': 'Gene Name', 'order': 2},
                {'name': 'gene_size', 'label': 'Taille gène (pb)', 'label_fr': 'Taille du gène (pb)', 'label_en': 'Gene Size (bp)', 'order': 3},
                {'name': 'origin', 'label': 'Source', 'label_fr': 'Source/origine de l\'échantillon', 'label_en': 'Sample Origin', 'order': 4},
                {'name': 'primers', 'label': 'Séquences amorces', 'label_fr': 'Séquences des amorces utilisées (5\'→3\')', 'label_en': 'Primer Sequences (5\'→3\')', 'order': 5},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
            ],
            'additional_info': [
                {
                    'name': 'sample_type',
                    'label': 'Type échantillon',
                    'label_fr': 'Type d\'échantillon soumis',
                    'label_en': 'Submitted Sample Type',
                    'field_type': 'checkbox',
                    'options': ["Produit de réaction BigDye", "Produit de PCR purifié", "Produit de PCR non purifié", 'Autre'],
                    'order': 0,
                },
                {
                    'name': 'supplies',
                    'label': 'Consommables',
                    'label_fr': 'Consommables fournis par le demandeur',
                    'label_en': 'Supplies Provided by Requester',
                    'field_type': 'text',
                    'order': 1,
                },
                {
                    'name': 'reading_direction',
                    'label': 'Sens lecture',
                    'label_fr': 'Sens de lecture souhaité',
                    'label_en': 'Requested Reading Direction',
                    'field_type': 'checkbox',
                    'options': ['Forward', 'Reverse', 'Les deux sens'],
                    'order': 2,
                },
                {
                    'name': 'amplification_kit',
                    'label': 'Kit amplification',
                    'label_fr': 'Kit d\'amplification utilisé',
                    'label_en': 'Amplification Kit Used',
                    'field_type': 'text',
                    'order': 3,
                },
                {
                    'name': 'qc_results',
                    'label': 'Résultats QC',
                    'label_fr': 'Résultats du contrôle de qualité des PCR',
                    'label_en': 'PCR QC Results',
                    'field_type': 'textarea',
                    'order': 4,
                },
            ],
            'checklist': [
                "Échantillons reçus en bon état",
                "Volume d'échantillon suffisant",
                "Amorces fournies séparément",
                "Concentration adéquate (entre 50 et 300 ng)",
                "Formulaire rempli intégralement",
                "Contrôle qualité des PCR fourni",
            ],
            'ibtikar_instructions': (
                "• Les amorces doivent être fournies séparément des échantillons.\n"
                "• La concentration en ADN doit être entre 50 et 300 ng.\n"
                "• Les produits BigDye doivent être frais (moins de 2 semaines).\n"
                "• Inclure les résultats de contrôle qualité des PCR."
            ),
        },
        
        # EGTP-Illumina-Microbial-WGS — MiSeq Illumina Whole Genome Sequencing
        'EGTP-Illumina-Microbial-WGS': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'organism', 'label': 'Type microorganisme', 'label_fr': 'Type de microorganisme (Bactérie, levure, moisissure)', 'label_en': 'Microorganism Type', 'order': 2},
                {'name': 'isolation', 'label': 'Source isolement', 'label_fr': 'Source d\'isolement (environnementale, alimentaire, clinique, etc.)', 'label_en': 'Isolation Source', 'order': 3},
                {'name': 'culture_medium', 'label': 'Milieu culture', 'label_fr': 'Milieu de culture approprié', 'label_en': 'Appropriate Culture Medium', 'order': 4},
                {'name': 'culture_conditions', 'label': 'Conditions culture', 'label_fr': 'Conditions de culture (Température, type respiratoire, durée d\'incubation)', 'label_en': 'Culture Conditions', 'order': 5},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
            ],
            'additional_info': [
                {
                    'name': 'file_format',
                    'label': 'Format fichiers',
                    'label_fr': 'Format fichiers livrés',
                    'label_en': 'Delivered File Format',
                    'field_type': 'text',
                    'options': ['FASTQ'],
                    'order': 0,
                },
                {
                    'name': 'delivery_method',
                    'label': 'Livraison',
                    'label_fr': 'Support de livraison',
                    'label_en': 'Delivery Method',
                    'field_type': 'text',
                    'options': ['Téléchargement via plateforme sécurisée'],
                    'order': 1,
                },
            ],
            'checklist': [
                "Échantillons reçus en bon état (aspect, température…)",
                "Quantité du milieu de culture respectée (4 × 5 ml)",
                "Mode de conservation/transport respecté",
                "Formulaire rempli intégralement",
            ],
            'ibtikar_instructions': (
                "• Fournir 4 × 5 ml de milieu de culture par échantillon.\n"
                "• Les échantillons doivent être vivants et en phase exponentielle de croissance.\n"
                "• Inclure les conditions de culture optimales.\n"
                "• Les résultats seront livrés au format FASTQ via la plateforme sécurisée."
            ),
        },
        
        # EGTP-Lyoph — Lyophilisation
        'EGTP-Lyoph': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'type', 'label': 'Type échantillon', 'label_fr': "Type de l'échantillon (Bactérie, plantes…)", 'label_en': 'Sample Type', 'order': 2},
                {'name': 'volume', 'label': 'Volume/Poids', 'label_fr': 'Volume/poids initial (ml/g)', 'label_en': 'Initial Volume/Weight', 'order': 3},
                {'name': 'dessiccation', 'label': 'Niveau dessiccation', 'label_fr': 'Niveau de dessiccation (primaire/secondaire)', 'label_en': 'Dessiccation Level', 'order': 4},
                {'name': 'storage', 'label': 'Stockage initial', 'label_fr': 'Conditions de stockage initiales', 'label_en': 'Initial Storage Conditions', 'order': 5},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
            ],
            'additional_info': [],
            'checklist': [
                "Échantillons reçus en bon état (aspect, température…)",
                "Mode de conservation/transport respecté",
                "Formulaire rempli intégralement",
            ],
            'ibtikar_instructions': (
                "• Les échantillons doivent être frais ou congelés.\n"
                "• Préciser le niveau de dessiccation souhaité (primaire ou secondaire).\n"
                "• Indiquer les conditions de stockage initiales recommandées.\n"
                "• Le lyophilisat sera retourné au demandeur dans un délai de 5-7 jours."
            ),
        },
        
        # EGTP-GDE — Extraction d'ADN Génomique
        'EGTP-GDE': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'type', 'label': 'Type échantillon', 'label_fr': "Type d'échantillon (Sang, bactérie, tissu animal…)", 'label_en': 'Sample Type', 'order': 2},
                {'name': 'date', 'label': 'Date de prélèvement', 'label_fr': 'Date de prélèvement', 'label_en': 'Sampling Date', 'order': 3},
                {'name': 'volume', 'label': 'Volume/Quantité', 'label_fr': 'Volume (µl) / Quantité (g)', 'label_en': 'Volume/Quantity', 'order': 4},
                {'name': 'storage', 'label': 'Conditions stockage', 'label_fr': 'Condition de stockage', 'label_en': 'Storage Conditions', 'order': 5},
                {'name': 'state', 'label': "État échantillon", 'label_fr': "État de l'échantillon", 'label_en': 'Sample State', 'order': 6},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 7},
            ],
            'additional_info': [
                {
                    'name': 'extraction_method',
                    'label': 'Méthode extraction',
                    'label_fr': 'Méthode d\'extraction souhaitée',
                    'label_en': 'Requested Extraction Method',
                    'field_type': 'dropdown',
                    'options': ['Méthode classique', 'Kit commercial'],
                    'order': 0,
                },
                {
                    'name': 'qc_techniques',
                    'label': 'Techniques QC',
                    'label_fr': 'Techniques de contrôle qualité souhaitées',
                    'label_en': 'Requested QC Techniques',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 1,
                },
                {
                    'name': 'desired_volume',
                    'label': 'Volume souhaité',
                    'label_fr': 'Volume d\'ADN souhaité récupérer après extraction',
                    'label_en': 'Desired DNA Volume After Extraction',
                    'field_type': 'text',
                    'order': 2,
                },
            ],
            'checklist': [
                "Échantillons reçus en bon état",
                "Quantité minimale d'échantillon respectée",
                "Mode de conservation/transport respecté",
                "Contrôle qualité d'ADN fourni",
                "Formulaire rempli intégralement",
            ],
            'ibtikar_instructions': (
                "• Chaque échantillon doit être identifié de manière claire.\n"
                "• Le volume minimum est de 200 µL pour les échantillons liquides.\n"
                "• Pour les tissus, minimum 100 mg requis.\n"
                "• Les échantillons doivent être транспорés congelés."
            ),
        },
        
        # EGTP-CAN — Contrôle qualité des acides nucleiques
        'EGTP-CAN': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'origin', 'label': 'Origine', 'label_fr': 'Origine des acides nucleiques', 'label_en': 'Nucleic Acid Origin', 'order': 2},
                {'name': 'nucleic_type', 'label': 'Type', 'label_fr': "Type d'acides nucleiques (plasmidique, chromosomique)", 'label_en': 'Nucleic Acid Type', 'order': 3},
                {'name': 'extraction', 'label': 'Méthode extraction', 'label_fr': 'Méthode d\'extraction utilisée', 'label_en': 'Extraction Method Used', 'order': 4},
                {'name': 'extraction_date', 'label': 'Date extraction', 'label_fr': 'Date de l\'extraction', 'label_en': 'Extraction Date', 'order': 5},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
            ],
            'additional_info': [
                {
                    'name': 'qc_techniques',
                    'label': 'Techniques QC',
                    'label_fr': 'Techniques de contrôle qualité souhaitées',
                    'label_en': 'Requested QC Techniques',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 0,
                },
                {
                    'name': 'gel_percentage',
                    'label': '% agarose',
                    'label_fr': 'Pourcentage de gel d\'agarose souhaité (si demandé)',
                    'label_en': 'Desired Agarose Gel Percentage',
                    'field_type': 'text',
                    'order': 1,
                },
                {
                    'name': 'size_marker',
                    'label': 'Marqueur',
                    'label_fr': 'Marqueur de taille pour l\'électrophorèse',
                    'label_en': 'Size Marker for Electrophoresis',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 2,
                },
            ],
            'checklist': [
                "Échantillons reçus en bon état (aspect, température…)",
                "Volume d'échantillon suffisant (10 µL)",
                "Formulaire rempli intégralement",
            ],
            'ibtikar_instructions': (
                "• Fournir au moins 10 µL d'échantillon par test.\n"
                "• Les échantillons doivent être purs et sans contaminants.\n"
                "• Indiquer la méthode d'extraction utilisée précédemment.\n"
                "• Préciser les techniques de contrôle qualité souhaitées."
            ),
        },
        
        # EGTP-PCR — PCR
        'EGTP-PCR': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'dna_origin', 'label': 'Origine ADN', 'label_fr': 'Origine de l\'ADN', 'label_en': 'DNA Origin', 'order': 2},
                {'name': 'dna_type', 'label': 'Type ADN', 'label_fr': "Type de l'ADN (plasmidique, chromosomique…)", 'label_en': 'DNA Type', 'order': 3},
                {'name': 'extraction', 'label': 'Méthode extraction', 'label_fr': 'Méthode de l\'extraction d\'ADN', 'label_en': 'DNA Extraction Method', 'order': 4},
                {'name': 'target_gene', 'label': 'Gène cible', 'label_fr': 'Gène cible', 'label_en': 'Target Gene', 'order': 5},
                {'name': 'amplicon_size', 'label': 'Taille amplicon', 'label_fr': 'Taille de l\'amplicon', 'label_en': 'Amplicon Size', 'order': 6},
                {'name': 'primers', 'label': 'Séquences amorces', 'label_fr': 'Séquences des amorces utilisées (5\'→3\')', 'label_en': 'Primer Sequences', 'order': 7},
                {'name': 'tm', 'label': 'Tm (°C)', 'label_fr': 'Tm (°C)', 'label_en': 'Tm (°C)', 'order': 8},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 9},
            ],
            'additional_info': [
                {
                    'name': 'pcr_kit',
                    'label': 'Kit PCR',
                    'label_fr': 'Type de kit PCR',
                    'label_en': 'PCR Kit Type',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 0,
                },
                {
                    'name': 'qc_techniques',
                    'label': 'Techniques QC',
                    'label_fr': 'Techniques de contrôle qualité souhaitées',
                    'label_en': 'Requested QC Techniques',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 1,
                },
                {
                    'name': 'size_marker',
                    'label': 'Marqueur',
                    'label_fr': 'Marqueur de taille pour l\'électrophorèse',
                    'label_en': 'Size Marker for Electrophoresis',
                    'field_type': 'dropdown',
                    'options': [],
                    'order': 2,
                },
                {
                    'name': 'pcr_volume',
                    'label': 'Volume PCR',
                    'label_fr': 'Volume du produit de PCR à récupérer après amplification',
                    'label_en': 'PCR Product Volume to Recover',
                    'field_type': 'text',
                    'order': 3,
                },
            ],
            'checklist': [
                "Échantillons reçus en bon état (aspect, température…)",
                "Volume d'échantillon suffisant (10 µL)",
                "Amorces fournies séparément",
                "Concentration adéquate (entre 50 et 300 ng)",
                "Formulaire rempli intégralement",
            ],
            'ibtikar_instructions': (
                "• Fournir les amorces séparément à une concentration de 10 µM.\n"
                "• L'ADN模板 doit avoir une concentration entre 50 et 300 ng/µL.\n"
                "• Préciser la taille attendue de l'amplicon.\n"
                "• Indiquer le kit PCR préféré si applicable."
            ),
        },
        
        # EGTP-IMT — Identification Microbienne via MALDI-TOF
        'EGTP-IMT': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'organism', 'label': 'Type microorganisme', 'label_fr': 'Type de microorganisme (Bactérie, levure, moisissure)', 'label_en': 'Microorganism Type', 'order': 2},
                {'name': 'isolation', 'label': 'Source isolement', 'label_fr': 'Source d\'isolement (environnementale, alimentaire, clinique, etc.)', 'label_en': 'Isolation Source', 'order': 3},
                {'name': 'isolation_date', 'label': 'Date isolement', 'label_fr': 'Date d\'isolement', 'label_en': 'Isolation Date', 'order': 4},
                {'name': 'culture_medium', 'label': 'Milieu culture', 'label_fr': 'Milieu de culture approprié', 'label_en': 'Culture Medium', 'order': 5},
                {'name': 'culture_conditions', 'label': 'Conditions culture', 'label_fr': 'Conditions de culture (Température, type respiratoire, durée d\'incubation)', 'label_en': 'Culture Conditions', 'order': 6},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 7},
            ],
            'additional_info': [
                {
                    'name': 'fresh_cultures',
                    'label': 'Cultures fraîches',
                    'label_fr': 'Fourniture de cultures fraîches',
                    'label_en': 'Fresh Cultures Supplied',
                    'field_type': 'dropdown',
                    'options': ['Oui', 'Non'],
                    'order': 0,
                },
                {
                    'name': 'maldi_target',
                    'label': 'Cible MALDI',
                    'label_fr': 'Type de cible MALDI-TOF',
                    'label_en': 'MALDI-TOF Target Type',
                    'field_type': 'dropdown',
                    'options': ['Usage unique obligatoire pour pathogènes'],
                    'order': 1,
                },
                {
                    'name': 'analysis_mode',
                    'label': 'Mode analyse',
                    'label_fr': 'Mode d\'analyse',
                    'label_en': 'Analysis Mode',
                    'field_type': 'dropdown',
                    'options': ['Simple', 'Duplicata', 'Triplicata'],
                    'order': 2,
                },
            ],
            'checklist': [
                "Échantillons reçus en bon état",
                "Quantité minimale d'échantillon respectée",
                "Mode de conservation/transport respecté",
                "Formulaire rempli intégralement",
            ],
            'ibtikar_instructions': (
                "• Fournir des cultures pures et fraîches (24-48h de croissance).\n"
                "• Pour les agents pathogènes, usage unique obligatoire des cibles MALDI-TOF.\n"
                "• Préciser le milieu de culture utilisé et les conditions d'incubation.\n"
                "• Indiquer le mode d'analyse souhaité (simple, duplicata ou triplicata)."
            ),
        },
        
        # EGTP-PS — Synthèse des Amorces
        'EGTP-PS': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'fr', 'label': 'F/R', 'label_fr': 'F/R', 'label_en': 'F/R', 'order': 1},
                {'name': 'name', 'label': 'Nom amorce', 'label_fr': 'Nom de l\'amorce', 'label_en': 'Primer Name', 'order': 2},
                {'name': 'size', 'label': 'Taille (pb)', 'label_fr': 'Taille (pb)', 'label_en': 'Size (bp)', 'order': 3},
                {'name': 'sequence', 'label': 'Séquence', 'label_fr': 'Séquence nucléotidique (5\'→3\')', 'label_en': 'Nucleotide Sequence (5\'→3\')', 'order': 4},
                {'name': 'gene', 'label': 'Gène cible', 'label_fr': 'Nom du Gène ciblé', 'label_en': 'Target Gene Name', 'order': 5},
                {'name': 'accession', 'label': 'N° accession', 'label_fr': 'N° d\'accession du Gène', 'label_en': 'Gene Accession No.', 'order': 6},
                {'name': 'gc', 'label': '% GC', 'label_fr': '% GC', 'label_en': '% GC', 'order': 7},
                {'name': 'tm', 'label': 'Tm (°C)', 'label_fr': 'Tm (°C)', 'label_en': 'Tm (°C)', 'order': 8},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 9},
            ],
            'additional_info': [
                {
                    'name': 'physical_state',
                    'label': 'État physique',
                    'label_fr': 'État physique souhaité pour recevoir les amorces',
                    'label_en': 'Desired Physical State for Primers',
                    'field_type': 'dropdown',
                    'options': ['Lyophilisé', 'Dissous dans l\'eau', 'Dissous dans TE'],
                    'order': 0,
                },
                {
                    'name': 'final_volume',
                    'label': 'Volume final',
                    'label_fr': 'Volume final à récupérer pour chaque amorce (µL)',
                    'label_en': 'Final Volume per Primer (µL)',
                    'field_type': 'text',
                    'order': 1,
                },
                {
                    'name': 'concentration',
                    'label': 'Concentration',
                    'label_fr': 'concentration souhaitée',
                    'label_en': 'Desired Concentration',
                    'field_type': 'text',
                    'order': 2,
                },
            ],
            'checklist': [
                "Échantillons reçus en bon état",
                "Séquences des amorces fournies en format clair (5'→3')",
                "Longueur des amorces compatible avec la synthèse standard",
                "Formulaire rempli intégralement",
            ],
            'ibtikar_instructions': (
                "• Les séquences doivent être fournies en format clair 5'→3'.\n"
                "• La longueur des amorces doit être entre 15 et 30 pb pour la synthèse standard.\n"
                "• Indiquer le gène cible et le numéro d'accession si disponible.\n"
                "• Préciser la concentration et le volume souhaités."
            ),
        },
    }
    
    # Create ServiceFormField records
    for service_code, data in service_data.items():
        if service_code not in services:
            print(f"WARNING: Service '{service_code}' not found in database. Skipping ServiceFormField population.")
            continue
        
        service = services[service_code]
        
        # Create sample table fields
        for field_data in data.get('sample_table', []):
            ServiceFormField.objects.create(
                service=service,
                field_category='sample_table',
                name=field_data['name'],
                label=field_data['label'],
                label_fr=field_data.get('label_fr', field_data['label']),
                label_en=field_data.get('label_en', field_data['label']),
                field_type='text',
                order=field_data.get('order', 0),
                sort_order=field_data.get('order', 0),
            )
        
        # Create additional info fields
        for field_data in data.get('additional_info', []):
            ServiceFormField.objects.create(
                service=service,
                field_category='additional_info',
                name=field_data['name'],
                label=field_data['label'],
                label_fr=field_data.get('label_fr', field_data['label']),
                label_en=field_data.get('label_en', field_data['label']),
                field_type=field_data.get('field_type', 'text'),
                options=field_data.get('options', []),
                choices_json=field_data.get('options', []),
                order=field_data.get('order', 0),
                sort_order=field_data.get('order', 0),
            )
        
        # Update service checklist and instructions
        service.checklist_items = data.get('checklist', [])
        service.ibtikar_instructions = data.get('ibtikar_instructions', '')
        service.save()


def reverse_populate(apps, schema_editor):
    """Reverse migration: Remove all ServiceFormField records created by this migration."""
    ServiceFormField = apps.get_model('core', 'ServiceFormField')
    ServiceFormField.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_add_pdf_form_fields'),
    ]

    operations = [
        migrations.RunPython(populate_service_form_fields, reverse_populate),
    ]
