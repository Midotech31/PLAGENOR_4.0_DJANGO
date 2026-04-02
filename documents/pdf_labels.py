# documents/pdf_labels.py — PLAGENOR 4.0 Bilingual Labels
# Contains all static labels used across the 3 PDF generators (FR/EN)

from django.utils.translation import gettext_lazy as _

# =============================================================================
# FRENCH LABELS
# =============================================================================

LABELS_FR = {
    # Document titles
    'platform_note_title': 'NOTE DE PLATEFORME',
    'platform_note_subtitle': 'Plateforme Technologique de Génomique — ESSBO',
    'sample_reception_title': 'FORMULAIRE DE RÉCEPTION DES ÉCHANTILLONS',
    'ibtikar_form_title': 'FORMULAIRE DE DEMANDE D\'ANALYSE',
    'ibtikar_form_subtitle': 'Programme IBTIKAR — PLAGENOR',
    
    # Institutional header
    'republic_algeria': 'République Algérienne Démocratique et Populaire',
    'ministry_higher_education': 'Ministère de l\'Enseignement Supérieur et de la Recherche Scientifique',
    'essbo_full': 'École Supérieure en Sciences Biologiques d\'Oran',
    'platform_tech': 'Plateforme Technologique de Génomique',
    
    # Reference lines
    'request_reference': 'N° de la demande de l\'analyse',
    'reference_format': '{year}/IBTIKAR/PLAGENOR/{service}',
    'date_format': 'Date: {date}',
    'version': 'Version',
    
    # Section headers
    'section_requester': 'Section 1 — Informations du demandeur',
    'section_analysis': 'Section 2 — Informations relatives à la demande d\'analyse',
    'section_samples': 'Section 3 — Informations sur les échantillons',
    'section_additional': 'Section 4 — Informations supplémentaires',
    'section_ethical': 'Section 5 — Déclaration de responsabilité éthique',
    'section_validation': 'Section 6 — Validation de la demande',
    'section_signature': 'Section 5 — Signature du demandeur',
    
    # Section 1: Requester info
    'full_name': 'Nom et prénom',
    'institution': 'Université / École',
    'laboratory': 'Laboratoire',
    'position': 'Fonction / Poste',
    'email': 'Adresse e-mail',
    'phone': 'Numéro de téléphone',
    'student_level': 'Niveau d\'études',
    
    # Section 2: Analysis info
    'analysis_framework': 'Cadre de l\'analyse',
    'project_title': 'Titre du projet',
    'pi_name': 'Directeur de recherche',
    'pi_email': 'Email du directeur',
    'pi_phone': 'Téléphone du directeur',
    'project_description': 'Description du projet',
    'service_requested': 'Service demandé',
    
    # Analysis framework choices
    'memoire_fin_cycle': 'Mémoire de fin de cycle',
    'these_doctorat': 'Thèse de doctorat',
    'projet_recherche': 'Projet de recherche',
    'habilitation': 'Habilitation universitaire',
    'autre_framework': 'Autre',
    
    # Section 3: Samples
    'sample_table_title': 'Tableau des échantillons',
    'sample_id': 'N°',
    'sample_code': 'Code',
    'sample_type': 'Type d\'échantillon',
    'sample_origin': 'Origine / Source',
    'sampling_date': 'Date de prélèvement',
    'storage_conditions': 'Conditions de stockage',
    'volume_quantity': 'Volume (µl) / Quantité (g)',
    'sample_state': 'État de l\'échantillon',
    'special_notes': 'Remarques particulières',
    'gene_name': 'Nom du gène',
    'gene_size': 'Taille du gène (pb)',
    'primer_sequence': 'Séquences des amorces (5\'→3\')',
    'organism_type': 'Type de microorganisme',
    'isolation_source': 'Source d\'isolement',
    'culture_medium': 'Milieu de culture',
    'culture_conditions': 'Conditions de culture',
    'initial_volume': 'Volume/poids initial',
    'dessiccation_level': 'Niveau de dessiccation',
    'nucleic_acid_origin': 'Origine des acides nucléiques',
    'nucleic_acid_type': 'Type d\'acides nucléiques',
    'extraction_method': 'Méthode d\'extraction',
    'extraction_date': 'Date de l\'extraction',
    'dna_origin': 'Origine de l\'ADN',
    'dna_type': 'Type de l\'ADN',
    'target_gene': 'Gène cible',
    'amplicon_size': 'Taille de l\'amplicon',
    'primer_tm': 'Tm (°C)',
    'isolation_date': 'Date d\'isolement',
    'primer_name': 'Nom de l\'amorce',
    'primer_size': 'Taille (pb)',
    'primer_sequence_full': 'Séquence nucléotidique (5\'→3\')',
    'gene_accession': 'N° d\'accession du Gène',
    'gc_content': '% GC',
    
    # Sample table minimum rows
    'minimum_rows_note': 'Minimum 10 lignes requises — lignes supplémentaires si nécessaire',
    
    # "Très important" block
    'very_important': 'Très important',
    'important_instructions': 'Instructions importantes pour le remplissage du formulaire',
    
    # Section 4: Additional info
    'additional_info_title': 'Informations supplémentaires',
    'extraction_method_requested': 'Méthode d\'extraction souhaitée',
    'extraction_classic': 'Méthode classique',
    'extraction_kit': 'Kit commercial',
    'pcr_kit_type': 'Type de kit de PCR',
    'qc_techniques': 'Techniques de contrôle qualité souhaitées',
    'size_marker': 'Marqueur de taille pour électrophorèse',
    'reading_direction': 'Sens de lecture souhaité',
    'forward': 'Forward',
    'reverse': 'Reverse',
    'both_directions': 'Les deux sens',
    'file_format': 'Format fichiers livrés',
    'fastq_format': 'FASTQ',
    'delivery_method': 'Support de livraison',
    'secure_download': 'Téléchargement via plateforme sécurisée',
    'primer_physics_state': 'État physique souhaité pour recevoir les amorces',
    'final_volume': 'Volume final à récupérer pour chaque amorce (µL)',
    'desired_concentration': 'concentration souhaitée',
    'pcr_product_type': 'Type d\'échantillon soumis',
    'reaction_product_bigdye': 'Produit de réaction BigDye',
    'pcr_purified': 'Produit de PCR purifié',
    'pcr_unpurified': 'Produit de PCR non purifié',
    'other_sample': 'Autre',
    'supplies_provided': 'Consommables fournis par le demandeur',
    'amplification_kit': 'Kit d\'amplification utilisé',
    'qc_results': 'Résultats du contrôle de qualité des PCR',
    'agarose_gel_percentage': 'Pourcentage de gel d\'agarose souhaité',
    'fresh_cultures': 'Fourniture de cultures fraîches',
    'yes': 'Oui',
    'no': 'Non',
    'maldi_target_type': 'Type de cible MALDI-TOF',
    'maldi_single_use': 'Usage unique obligatoire pour pathogènes',
    'analysis_mode': 'Mode d\'analyse',
    'simple_mode': 'Simple',
    'duplicate_mode': 'Duplicata',
    'triplicate_mode': 'Triplicata',
    'desired_dna_volume': 'Volume d\'ADN souhaité récupérer après extraction',
    'pcr_kit_type_service': 'Type de kit PCR',
    
    # Ethical declaration
    'ethical_declaration_title': 'Déclaration de responsabilité éthique',
    'ethical_declaration_text': (
        'La signature du présent formulaire implique que le demandeur certifie que '
        'tous les échantillons soumis ont été collectés, manipulés et transférés '
        'dans le strict respect des normes éthiques et réglementaires applicables. '
        'Le demandeur reconnaît assumer l\'entière responsabilité quant à la nature, '
        'l\'origine et l\'utilisation de ces échantillons, y compris toute implication '
        'éthique ou juridique liée à leur traitement ou leur analyse.'
    ),
    
    # Compliance statement
    'compliance_statement_title': 'Déclaration de Conformité',
    'compliance_statement_text': (
        'Tous les échantillons sont conformes aux exigences de soumission, de transport '
        'et de biosécurité de PLAGENOR. Aucun risque pathogène ou clinique n\'a été '
        'déclaré pour ce projet.'
    ),
    
    # Section 5: Validation (PLAGENOR)
    'reserved_plagenor': 'Cadre réservé à PLAGENOR',
    'operator': 'Opérateur',
    'checklist_title': 'Checklist de conformité (à remplir par PLAGENOR)',
    'optional_comment': 'Commentaire optionnel',
    'reception_date': 'Date de la réception',
    'appointment_date': 'Date de rendez-vous prévue',
    'validation_chef': 'Validation Chef de Service',
    'validation_directeur': 'Visa du Directeur',
    
    # Signature
    'submitter_signature': 'Signature du demandeur',
    'signature_date': 'Date',
    'visa_chef': 'Visa du Chef du Service Commun',
    'visa_directeur': 'Visa du Directeur de l\'ESSBO',
    
    # Platform Note specific
    'platform_note_section1': 'Section 1 — Identification',
    'service_code': 'Code du service',
    'request_id': 'ID de la demande',
    'date_issued': "Date d'émission",
    'platform_note_section2': 'Section 2 — Informations sur l\'analyse',
    'analysis_type': 'Type d\'analyse',
    'number_of_samples': 'Nombre d\'échantillons',
    'sample_details': 'Détails des échantillons',
    'platform_note_section3': 'Section 3 — Description du service',
    'platform_note_section4': 'Section 4 — Notes de traitement',
    'processing_notes': 'Notes de traitement',
    'platform_note_section5': 'Section 5 — Tarification',
    'calculated_cost': 'Coût calculé',
    'discount_applied': 'Remise appliquée',
    'final_cost': 'Coût final',
    'cost_breakdown': 'Détail du coût',
    'pending_validation': 'En attente de validation financière',
    'platform_note_section6': 'Section 6 — Livrables',
    'deliverables': 'Livrables',
    'platform_note_section7': 'Section 7 — Délai estimé',
    'estimated_turnaround': 'Délai estimé de traitement',
    'business_days': 'jours ouvrables',
    
    # Reception Form specific
    'reception_section1': 'Section 1 — Informations sur le demandeur',
    'applicant_full_name': 'Nom complet du demandeur',
    'department': 'Département',
    'reception_section2': 'Section 2 — Informations sur le projet',
    'reception_section3': 'Section 3 — Informations sur les échantillons',
    'additional_notes': 'Notes supplémentaires',
    'reception_section4': 'Section 4 — Transport et suivi',
    'shipping_date': 'Date d\'expédition',
    'tracking_number': 'Numéro de suivi',
    'reception_section5': 'Section 5 — Consentement et conformité',
    'consent_form_attached': 'Formulaire de consentement attaché',
    'ethical_compliance': 'Conformité éthique',
    'reception_section6': 'Section 6 — Déclaration',
    'declaration_text': (
        'Je déclare que les informations fournies sont exactes et complètes à '
        'ma connaissance. Je comprends que toute divergence peut entraîner des '
        'retards dans le traitement.'
    ),
    'reception_section7': 'Section 7 — Déclaration de responsabilité éthique',
    'full_ethical_declaration': (
        'Par la signature de ce formulaire, le demandeur certifie que tous les '
        'échantillons soumis ont été collectés, manipulés et transférés dans le '
        'strict respect des normes éthiques et réglementaires applicables. Le '
        'demandeur reconnaît assumer l\'entière responsabilité quant à la nature, '
        'l\'origine et l\'utilisation de ces échantillons, y compris toute implication '
        'éthique ou juridique liée à leur traitement ou leur analyse.'
    ),
    'reception_section8': 'Section 8 — Bloc de signature',
    
    # Position choices
    'position_etudiant': 'Étudiant/Doctorant',
    'position_chercheur': 'Chercheur',
    'position_mca': 'MCA',
    'position_mcb': 'MCB',
    'position_professeur': 'Professeur',
    'position_ingenieur': 'Ingénieur',
    'position_technicien': 'Technicien',
    'position_autre': 'Autre',
    
    # Footer
    'footer_generated': 'Ce document a été généré automatiquement par PLAGENOR 4.0 le',
    'footer_page': 'Page',
    'footer_of': 'sur',
    
    # Declaration headers
    'declaration_1': 'Déclaration 1 — Exactitude des informations',
    'declaration_2': 'Déclaration 2 — Responsabilité éthique',

    # Validation checklist items
    'checklist_filled': 'Formulaire correctement rempli',
    'checklist_samples': 'Échantillons conformes',
    'checklist_payment': 'Paiement/budget vérifié',

    # Department label
    'department': 'Département / Laboratoire',

    # Empty/placeholder
    'not_applicable': 'N/A',
    'not_specified': 'Non précisé',
    'to_be_filled': 'À remplir',
    'blank': '',
    'pending': 'En attente',
}


# =============================================================================
# ENGLISH LABELS
# =============================================================================

LABELS_EN = {
    # Document titles
    'platform_note_title': 'PLATFORM NOTE',
    'platform_note_subtitle': 'Genomics Technology Platform — ESSBO',
    'sample_reception_title': 'SAMPLE RECEPTION FORM',
    'ibtikar_form_title': 'ANALYSIS REQUEST FORM',
    'ibtikar_form_subtitle': 'IBTIKAR Programme — PLAGENOR',
    
    # Institutional header
    'republic_algeria': 'People\'s Democratic Republic of Algeria',
    'ministry_higher_education': 'Ministry of Higher Education and Scientific Research',
    'essbo_full': 'Higher School of Biological Sciences of Oran',
    'platform_tech': 'Genomics Technology Platform',
    
    # Reference lines
    'request_reference': 'Analysis Request No.',
    'reference_format': '{year}/IBTIKAR/PLAGENOR/{service}',
    'date_format': 'Date: {date}',
    'version': 'Version',
    
    # Section headers
    'section_requester': 'Section 1 — Requester Information',
    'section_analysis': 'Section 2 — Analysis Request Information',
    'section_samples': 'Section 3 — Sample Information',
    'section_additional': 'Section 4 — Additional Information',
    'section_ethical': 'Section 5 — Ethical Responsibility Declaration',
    'section_validation': 'Section 6 — Request Validation',
    'section_signature': 'Section 5 — Requester\'s Signature',
    
    # Section 1: Requester info
    'full_name': 'Full Name',
    'institution': 'University / School',
    'laboratory': 'Laboratory',
    'position': 'Position',
    'email': 'Email Address',
    'phone': 'Phone Number',
    'student_level': 'Study Level',
    
    # Section 2: Analysis info
    'analysis_framework': 'Analysis Framework',
    'project_title': 'Project Title',
    'pi_name': 'Research Supervisor',
    'pi_email': 'Supervisor Email',
    'pi_phone': 'Supervisor Phone',
    'project_description': 'Project Description',
    'service_requested': 'Requested Service',
    
    # Analysis framework choices
    'memoire_fin_cycle': 'End-of-cycle Thesis',
    'these_doctorat': 'Doctoral Thesis',
    'projet_recherche': 'Research Project',
    'habilitation': 'University Habilitation',
    'autre_framework': 'Other',
    
    # Section 3: Samples
    'sample_table_title': 'Sample Table',
    'sample_id': 'No.',
    'sample_code': 'Code',
    'sample_type': 'Sample Type',
    'sample_origin': 'Origin / Source',
    'sampling_date': 'Sampling Date',
    'storage_conditions': 'Storage Conditions',
    'volume_quantity': 'Volume (µl) / Quantity (g)',
    'sample_state': 'Sample Condition',
    'special_notes': 'Special Notes',
    'gene_name': 'Gene Name',
    'gene_size': 'Gene Size (bp)',
    'primer_sequence': 'Primer Sequences (5\'→3\')',
    'organism_type': 'Microorganism Type',
    'isolation_source': 'Isolation Source',
    'culture_medium': 'Culture Medium',
    'culture_conditions': 'Culture Conditions',
    'initial_volume': 'Initial Volume/Weight',
    'dessiccation_level': 'Dessiccation Level',
    'nucleic_acid_origin': 'Nucleic Acid Origin',
    'nucleic_acid_type': 'Nucleic Acid Type',
    'extraction_method': 'Extraction Method',
    'extraction_date': 'Extraction Date',
    'dna_origin': 'DNA Origin',
    'dna_type': 'DNA Type',
    'target_gene': 'Target Gene',
    'amplicon_size': 'Amplicon Size',
    'primer_tm': 'Tm (°C)',
    'isolation_date': 'Isolation Date',
    'primer_name': 'Primer Name',
    'primer_size': 'Size (bp)',
    'primer_sequence_full': 'Nucleotide Sequence (5\'→3\')',
    'gene_accession': 'Gene Accession No.',
    'gc_content': '% GC',
    
    # Sample table minimum rows
    'minimum_rows_note': 'Minimum 10 rows required — add additional rows if necessary',
    
    # "Very important" block
    'very_important': 'Very Important',
    'important_instructions': 'Important instructions for form completion',
    
    # Section 4: Additional info
    'additional_info_title': 'Additional Information',
    'extraction_method_requested': 'Requested Extraction Method',
    'extraction_classic': 'Classical Method',
    'extraction_kit': 'Commercial Kit',
    'pcr_kit_type': 'PCR Kit Type',
    'qc_techniques': 'Requested QC Techniques',
    'size_marker': 'Size Marker for Electrophoresis',
    'reading_direction': 'Requested Reading Direction',
    'forward': 'Forward',
    'reverse': 'Reverse',
    'both_directions': 'Both Directions',
    'file_format': 'Delivered File Format',
    'fastq_format': 'FASTQ',
    'delivery_method': 'Delivery Method',
    'secure_download': 'Download via secure platform',
    'primer_physics_state': 'Desired Physical State for Primers',
    'final_volume': 'Final Volume to Recover per Primer (µL)',
    'desired_concentration': 'desired concentration',
    'pcr_product_type': 'Submitted Sample Type',
    'reaction_product_bigdye': 'BigDye Reaction Product',
    'pcr_purified': 'Purified PCR Product',
    'pcr_unpurified': 'Unpurified PCR Product',
    'other_sample': 'Other',
    'supplies_provided': 'Supplies Provided by Requester',
    'amplification_kit': 'Amplification Kit Used',
    'qc_results': 'PCR QC Results',
    'agarose_gel_percentage': 'Desired Agarose Gel Percentage',
    'fresh_cultures': 'Fresh Cultures Supplied',
    'yes': 'Yes',
    'no': 'No',
    'maldi_target_type': 'MALDI-TOF Target Type',
    'maldi_single_use': 'Single-use mandatory for pathogens',
    'analysis_mode': 'Analysis Mode',
    'simple_mode': 'Simple',
    'duplicate_mode': 'Duplicate',
    'triplicate_mode': 'Triplicate',
    'desired_dna_volume': 'Desired DNA Volume After Extraction',
    'pcr_kit_type_service': 'PCR Kit Type',
    
    # Ethical declaration
    'ethical_declaration_title': 'Ethical Responsibility Declaration',
    'ethical_declaration_text': (
        'By signing this form, the applicant hereby certifies that all submitted '
        'samples have been collected, handled, and transferred in strict adherence '
        'to all applicable ethical and regulatory standards. The applicant further '
        'acknowledges full responsibility for the nature, origin, and intended use '
        'of these samples, including any ethical or legal implications arising from '
        'their processing, handling, or analysis.'
    ),
    
    # Compliance statement
    'compliance_statement_title': 'Compliance Statement',
    'compliance_statement_text': (
        'All samples complied with PLAGENOR submission, transport, and biosafety '
        'requirements. No pathogenic or clinical risk was declared for this project.'
    ),
    
    # Section 5: Validation (PLAGENOR)
    'reserved_plagenor': 'Reserved for PLAGENOR',
    'operator': 'Operator',
    'checklist_title': 'Compliance Checklist (to be filled by PLAGENOR)',
    'optional_comment': 'Optional comment',
    'reception_date': 'Reception Date',
    'appointment_date': 'Scheduled Appointment Date',
    'validation_chef': 'Service Head Validation',
    'validation_directeur': 'Director Visa',
    
    # Signature
    'submitter_signature': 'Requester\'s Signature',
    'signature_date': 'Date',
    'visa_chef': 'Common Service Head Visa',
    'visa_directeur': 'ESSBO Director Visa',
    
    # Platform Note specific
    'platform_note_section1': 'Section 1 — Identification',
    'service_code': 'Service Code',
    'request_id': 'Request ID',
    'date_issued': 'Date Issued',
    'platform_note_section2': 'Section 2 — Analysis Information',
    'analysis_type': 'Analysis Type',
    'number_of_samples': 'Number of Samples',
    'sample_details': 'Sample Details',
    'platform_note_section3': 'Section 3 — Service Description',
    'platform_note_section4': 'Section 4 — Processing Notes',
    'processing_notes': 'Processing Notes',
    'platform_note_section5': 'Section 5 — Pricing',
    'calculated_cost': 'Calculated Cost',
    'discount_applied': 'Discount Applied',
    'final_cost': 'Final Cost',
    'cost_breakdown': 'Cost Breakdown',
    'pending_validation': 'Pending financial validation',
    'platform_note_section6': 'Section 6 — Deliverables',
    'deliverables': 'Deliverables',
    'platform_note_section7': 'Section 7 — Estimated Turnaround',
    'estimated_turnaround': 'Estimated Processing Time',
    'business_days': 'business days',
    
    # Reception Form specific
    'reception_section1': 'Section 1 — Submitter Information',
    'applicant_full_name': 'Applicant Full Name',
    'department': 'Department',
    'reception_section2': 'Section 2 — Project Information',
    'reception_section3': 'Section 3 — Sample Information',
    'additional_notes': 'Additional Notes',
    'reception_section4': 'Section 4 — Shipping and Tracking',
    'shipping_date': 'Shipping Date',
    'tracking_number': 'Tracking Number',
    'reception_section5': 'Section 5 — Consent and Compliance',
    'consent_form_attached': 'Consent Form Attached',
    'ethical_compliance': 'Ethical Compliance',
    'reception_section6': 'Section 6 — Declaration',
    'declaration_text': (
        'I hereby declare that the information provided is accurate and complete '
        'to the best of my knowledge. I understand that any discrepancies may '
        'lead to delays in processing.'
    ),
    'reception_section7': 'Section 7 — Ethical Responsibility Declaration',
    'full_ethical_declaration': (
        'By signing this form, the applicant hereby certifies that all submitted '
        'samples have been collected, handled, and transferred in strict adherence '
        'to all applicable ethical and regulatory standards. The applicant further '
        'acknowledges full responsibility for the nature, origin, and intended use '
        'of these samples, including any ethical or legal implications arising from '
        'their processing, handling, or analysis.'
    ),
    'reception_section8': 'Section 8 — Signature Block',
    
    # Position choices
    'position_etudiant': 'Student/PhD Candidate',
    'position_chercheur': 'Researcher',
    'position_mca': 'MCA (Assistant Professor)',
    'position_mcb': 'MCB (Associate Professor)',
    'position_professeur': 'Professor',
    'position_ingenieur': 'Engineer',
    'position_technicien': 'Technician',
    'position_autre': 'Other',
    
    # Footer
    'footer_generated': 'This document was automatically generated by PLAGENOR 4.0 on',
    'footer_page': 'Page',
    'footer_of': 'of',

    # Declaration headers
    'declaration_1': 'Declaration 1 — Accuracy of Information',
    'declaration_2': 'Declaration 2 — Ethical Responsibility',

    # Validation checklist items
    'checklist_filled': 'Form correctly filled',
    'checklist_samples': 'Samples conform',
    'checklist_payment': 'Payment/budget verified',

    # Department label
    'department': 'Department / Laboratory',

    # Empty/placeholder
    'not_applicable': 'N/A',
    'not_specified': 'Not specified',
    'to_be_filled': 'To be filled',
    'blank': '',
    'pending': 'Pending',
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_labels(lang='fr'):
    """
    Get the appropriate label dictionary based on language.
    
    Args:
        lang: Language code ('fr' or 'en')
        
    Returns:
        Dictionary of labels for the specified language
    """
    if lang == 'en':
        return LABELS_EN
    return LABELS_FR


def get_label(key, lang='fr', default=None):
    """
    Get a specific label by key.
    
    Args:
        key: Label key
        lang: Language code ('fr' or 'en')
        default: Default value if key not found
        
    Returns:
        Label text for the specified language
    """
    labels = get_labels(lang)
    return labels.get(key, default or key)


def format_reference(service_code, year=None, lang='fr'):
    """
    Format a request reference line.
    
    Args:
        service_code: Service code (e.g., 'EGTP-Seq02')
        year: Year (defaults to current year)
        lang: Language code
        
    Returns:
        Formatted reference string
    """
    import datetime
    if year is None:
        year = datetime.datetime.now().year
    
    labels = get_labels(lang)
    template = labels.get('reference_format', '{year}/IBTIKAR/PLAGENOR/{service}')
    
    return template.format(year=year, service=service_code)


def get_position_choices(lang='fr'):
    """
    Get position/function choices for forms.
    
    Args:
        lang: Language code
        
    Returns:
        List of tuples (value, display_label)
    """
    labels = get_labels(lang)
    return [
        ('etudiant_doctorant', labels.get('position_etudiant', 'Student/PhD')),
        ('chercheur', labels.get('position_chercheur', 'Researcher')),
        ('mca', labels.get('position_mca', 'MCA')),
        ('mcb', labels.get('position_mcb', 'MCB')),
        ('professeur', labels.get('position_professeur', 'Professor')),
        ('ingenieur', labels.get('position_ingenieur', 'Engineer')),
        ('technicien', labels.get('position_technicien', 'Technician')),
        ('autre', labels.get('position_autre', 'Other')),
    ]


def get_framework_choices(lang='fr'):
    """
    Get analysis framework choices for forms.
    
    Args:
        lang: Language code
        
    Returns:
        List of tuples (value, display_label)
    """
    labels = get_labels(lang)
    return [
        ('memoire_fin_cycle', labels.get('memoire_fin_cycle', 'End-of-cycle Thesis')),
        ('these_doctorat', labels.get('these_doctorat', 'Doctoral Thesis')),
        ('projet_recherche', labels.get('projet_recherche', 'Research Project')),
        ('habilitation', labels.get('habilitation', 'Habilitation')),
        ('autre', labels.get('autre_framework', 'Other')),
    ]
