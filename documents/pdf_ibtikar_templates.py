# documents/pdf_ibtikar_templates.py — PLAGENOR 4.0 IBTIKAR Form Template Data
# Contains all service-specific translations, titles, columns, instructions, and checklists

SERVICE_TITLES = {
    'EGTP-IMT': {
        'fr': "DEMANDE D'IDENTIFICATION MICROBIENNE VIA MALDI-TOF BIOTYPER\nEGTP-IMT",
        'en': "MICROBIAL IDENTIFICATION REQUEST VIA MALDI-TOF BIOTYPER\nEGTP-IMT",
    },
    'EGTP-GDE': {
        'fr': "DEMANDE D'EXTRACTION D'ADN GÉNOMIQUE\nEGTP-GDE",
        'en': "GENOMIC DNA EXTRACTION REQUEST\nEGTP-GDE",
    },
    'EGTP-PCR': {
        'fr': "DEMANDE D'AMPLIFICATION PAR PCR CONVENTIONNELLE\nEGTP-PCR",
        'en': "CONVENTIONAL PCR AMPLIFICATION REQUEST\nEGTP-PCR",
    },
    'EGTP-PS': {
        'fr': "DEMANDE DE PURIFICATION DE PRODUITS DE PCR ET SÉQUENÇAGE SANGER\nEGTP-PS",
        'en': "PCR PRODUCT PURIFICATION AND SANGER SEQUENCING REQUEST\nEGTP-PS",
    },
    'EGTP-SEQ02': {
        'fr': "DEMANDE DE SÉQUENÇAGE SANGER (ADN PRÉ-PURIFIÉ)\nEGTP-SEQ02",
        'en': "SANGER SEQUENCING REQUEST (PRE-PURIFIED DNA)\nEGTP-SEQ02",
    },
    'EGTP-SEQS': {
        'fr': "DEMANDE DE SÉQUENÇAGE SHOTGUN (ILLUMINA)\nEGTP-SEQS",
        'en': "SHOTGUN SEQUENCING REQUEST (ILLUMINA)\nEGTP-SEQS",
    },
    'EGTP-WGS': {
        'fr': "DEMANDE DE SÉQUENÇAGE DE GÉNOME COMPLET (ILLUMINA)\nEGTP-WGS",
        'en': "WHOLE GENOME SEQUENCING REQUEST (ILLUMINA)\nEGTP-WGS",
    },
    'EGTP-LYOPH': {
        'fr': "DEMANDE DE LYOPHILISATION\nEGTP-LYOPH",
        'en': "LYOPHILIZATION REQUEST\nEGTP-LYOPH",
    },
    'EGTP-CAN': {
        'fr': "DEMANDE D'ANALYSE MICROBIOLOGIQUE DES EAUX PAR MÉTHODE CLASSIQUE\nEGTP-CAN",
        'en': "MICROBIOLOGICAL WATER ANALYSIS REQUEST (CLASSICAL METHOD)\nEGTP-CAN",
    },
}

SERVICE_SAMPLE_COLUMNS = {
    'EGTP-IMT': {
        'fr': ["N°", "Code", "Type de microorganisme\n(Bactérie, levure, moisissure)", "Source d'isolement", "Date d'isolement", "Milieu de culture approprié", "Conditions de culture\n(T°, type respiratoire, durée)", "Remarques particulières"],
        'en': ["No.", "Code", "Microorganism Type\n(Bacteria, yeast, mold)", "Isolation Source", "Isolation Date", "Appropriate Culture Medium", "Culture Conditions\n(T°, respiratory type, duration)", "Special Notes"],
    },
    'EGTP-GDE': {
        'fr': ["N°", "Code", "Type d'échantillon\n(Sang, bactérie, tissu...)", "Date de prélèvement", "Volume (µl) / Quantité (g)", "Condition de stockage /\nÉtat de l'échantillon", "Remarques particulières"],
        'en': ["No.", "Code", "Sample Type\n(Blood, bacteria, tissue...)", "Collection Date", "Volume (µl) / Quantity (g)", "Storage Condition /\nSample State", "Special Notes"],
    },
    'EGTP-PCR': {
        'fr': ["N°", "Code", "Gène cible", "Amorces\n(Nom, Séquence 5'→3')", "Taille attendue\nde l'amplicon (pb)", "Concentration\nd'ADN (ng/µl)", "Remarques"],
        'en': ["No.", "Code", "Target Gene", "Primers\n(Name, Sequence 5'→3')", "Expected Amplicon\nSize (bp)", "DNA Concentration\n(ng/µl)", "Notes"],
    },
}

SERVICE_INSTRUCTIONS = {
    'EGTP-IMT': {
        'fr': {
            'important': "Les cultures soumises à l'analyse doivent impérativement être fraîches, pures et en phase exponentielle de croissance afin de garantir un profil protéique optimal et une identification fiable via la technologie MALDI-TOF MS.",
            'transport': "Les échantillons doivent être conditionnés dans des boîtes de Pétri bien fermées, scellées individuellement avec du film paraffin/alimentaire, puis placés dans un emballage secondaire étanche et rigide.",
        },
        'en': {
            'important': "Cultures submitted for analysis must be fresh, pure, and in the exponential growth phase to ensure an optimal proteomic profile and reliable identification via MALDI-TOF MS technology.",
            'transport': "Samples must be placed in well-sealed Petri dishes, individually wrapped with paraffin/cling film, then placed in a sealed, rigid secondary container.",
        },
    },
}

SERVICE_ADDITIONAL_FIELDS = {
    'EGTP-IMT': {
        'fr': [{'key': 'fresh_culture', 'label': "Fourniture de cultures fraîches"}, {'key': 'maldi_target_type', 'label': "Type de cible MALDI-TOF"}, {'key': 'analysis_mode', 'label': "Mode d'analyse"}],
        'en': [{'key': 'fresh_culture', 'label': "Fresh Culture Provision"}, {'key': 'maldi_target_type', 'label': "MALDI-TOF Target Type"}, {'key': 'analysis_mode', 'label': "Analysis Mode"}],
    },
}

SERVICE_CHECKLIST = {
    'EGTP-IMT': {
        'fr': ["Échantillons reçus en bon état", "Quantité minimale d'échantillon respectée", "Mode de conservation/transport respecté", "Formulaire rempli intégralement"],
        'en': ["Samples received in good condition", "Minimum sample quantity met", "Storage/transport conditions met", "Form completely filled"],
    },
}

TRANSLATIONS = {
    'fr': {
        'republic': "République Algérienne Démocratique et Populaire",
        'ministry': "Ministère de l'Enseignement Supérieur et de la Recherche Scientifique",
        'school': "École Supérieure des Sciences Biologiques d'Oran",
        'platform': "Plateforme Technologique de Génomique",
        'request_number': "N° de la demande de l'analyse",
        'section1_title': "1. Informations du demandeur",
        'full_name': "Nom et prénom",
        'university': "Université / École",
        'laboratory': "Laboratoire",
        'position': "Fonction / Poste",
        'email': "Adresse e-mail",
        'phone': "Numéro de téléphone",
        'section2_title': "2. Informations relatives à la demande d'analyse",
        'analysis_frame': "Cadre de l'analyse",
        'project_title': "Titre du projet",
        'research_director': "Directeur de recherche / Porteur de projet",
        'section3_title': "3. Informations sur les échantillons",
        'very_important': "Très important",
        'section4_title': "4. Informations supplémentaires",
        'ethical_declaration_title': "Déclaration de responsabilité éthique",
        'ethical_declaration_text': "La signature du présent formulaire engage le demandeur à certifier que les échantillons soumis ont été collectés, manipulés et transférés dans le respect strict des normes éthiques et réglementaires en vigueur.",
        'requester_signature': "Signature du demandeur",
        'section5_title': "5. Validation de la demande (Cadre réservé à PLAGENOR)",
        'operator': "Opérateur",
        'operator_name': "Nom et prénom",
        'reception_date': "Date de la réception",
        'signature': "Signature",
        'checklist_title': "Checklist de conformité (à remplir par PLAGENOR)",
        'check_samples_ok': "Échantillons reçus en bon état",
        'check_quantity_ok': "Quantité minimale d'échantillon respectée",
        'check_transport_ok': "Mode de conservation/transport respecté",
        'check_form_ok': "Formulaire rempli intégralement",
        'comment': "Commentaire (optionnel)",
        'visa_responsables': "Visa des responsables",
        'visa_chef_service': "Visa du Chef du Service Commun",
        'visa_directeur': "Visa du Directeur de l'ESSBO",
        'date': "Date",
        'version': "V 02",
        'version_date': "02.11.2025",
        'form_intro': "Afin de garantir un traitement optimal de vos échantillons, veuillez remplir ce formulaire avec précision.",
        'yes': "Oui",
        'no': "Non",
        'to_be_filled': "À remplir",
    },
    'en': {
        'republic': "People's Democratic Republic of Algeria",
        'ministry': "Ministry of Higher Education and Scientific Research",
        'school': "Higher School of Biological Sciences of Oran",
        'platform': "Genomics Technology Platform",
        'request_number': "Analysis Request No.",
        'section1_title': "1. Requester Information",
        'full_name': "Full Name",
        'university': "University / School",
        'laboratory': "Laboratory",
        'position': "Position",
        'email': "Email Address",
        'phone': "Phone Number",
        'section2_title': "2. Analysis Request Information",
        'analysis_frame': "Analysis Framework",
        'project_title': "Project Title",
        'research_director': "Research Supervisor / Project Leader",
        'section3_title': "3. Sample Information",
        'very_important': "Very Important",
        'section4_title': "4. Additional Information",
        'ethical_declaration_title': "Ethical Responsibility Declaration",
        'ethical_declaration_text': "By signing this form, the applicant hereby certifies that all submitted samples have been collected, handled, and transferred in strict adherence to all applicable ethical and regulatory standards.",
        'requester_signature': "Requester's Signature",
        'section5_title': "5. Request Validation (Reserved for PLAGENOR)",
        'operator': "Operator",
        'operator_name': "Full Name",
        'reception_date': "Reception Date",
        'signature': "Signature",
        'checklist_title': "Compliance Checklist (to be filled by PLAGENOR)",
        'check_samples_ok': "Samples received in good condition",
        'check_quantity_ok': "Minimum sample quantity met",
        'check_transport_ok': "Storage/transport conditions met",
        'check_form_ok': "Form completely filled",
        'comment': "Comment (optional)",
        'visa_responsables': "Responsible Authorities",
        'visa_chef_service': "Common Service Head Visa",
        'visa_directeur': "ESSBO Director Visa",
        'date': "Date",
        'version': "V 02",
        'version_date': "02.11.2025",
        'form_intro': "To ensure optimal processing of your samples, please fill in this form accurately.",
        'yes': "Yes",
        'no': "No",
        'to_be_filled': "To be filled",
    },
}


def get_translations(lang='fr'):
    return TRANSLATIONS.get(lang, TRANSLATIONS['fr'])


def get_service_title(service_code, lang='fr'):
    if service_code in SERVICE_TITLES:
        return SERVICE_TITLES[service_code].get(lang, SERVICE_TITLES[service_code]['fr'])
    return service_code


def get_sample_columns(service_code, lang='fr'):
    if service_code in SERVICE_SAMPLE_COLUMNS:
        return SERVICE_SAMPLE_COLUMNS[service_code].get(lang, [])
    return []


def get_service_instructions(service_code, lang='fr'):
    if service_code in SERVICE_INSTRUCTIONS:
        return SERVICE_INSTRUCTIONS[service_code].get(lang, {'important': '', 'transport': ''})
    return {'important': '', 'transport': ''}


def get_additional_fields(service_code, lang='fr'):
    if service_code in SERVICE_ADDITIONAL_FIELDS:
        return SERVICE_ADDITIONAL_FIELDS[service_code].get(lang, [])
    return []


def get_checklist(service_code, lang='fr'):
    if service_code in SERVICE_CHECKLIST:
        return SERVICE_CHECKLIST[service_code].get(lang, [])
    return ["Échantillons reçus en bon état"] if lang == 'fr' else ["Samples received in good condition"]
