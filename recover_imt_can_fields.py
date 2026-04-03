"""
Recover form fields for EGTP-IMT and EGTP-CAN services.
Run with: python manage.py shell < recover_imt_can_fields.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
django.setup()

from core.models import Service, ServiceFormField

def get_or_create_service(code):
    """Get service by code or return None."""
    try:
        return Service.objects.get(code=code)
    except Service.DoesNotExist:
        print(f"[ERROR] Service {code} not found!")
        return None

def create_field(service, category, field_data):
    """Create a form field if it doesn't exist."""
    name = field_data['name']
    
    # Check if field already exists
    existing = ServiceFormField.objects.filter(service=service, name=name).first()
    if existing:
        print(f"  [SKIP] Field '{name}' already exists")
        return existing
    
    field = ServiceFormField.objects.create(
        service=service,
        field_category=category,
        name=name,
        label=field_data.get('label', name),
        label_fr=field_data.get('label_fr', field_data.get('label', name)),
        label_en=field_data.get('label_en', ''),
        field_type=field_data.get('field_type', 'text'),
        options=field_data.get('options', []),
        choices_json=field_data.get('options', []) or None,
        order=field_data.get('order', 0),
        sort_order=field_data.get('order', 0),
        is_required=False,
        required=False,
        channel='BOTH',
    )
    print(f"  [OK] Created field: {name}")
    return field

def recover_imt():
    """Recover EGTP-IMT fields."""
    print("\n" + "="*60)
    print("Recovering EGTP-IMT (Microbial Identification MALDI-TOF)")
    print("="*60)
    
    service = get_or_create_service('EGTP-IMT')
    if not service:
        return
    
    # Sample table columns
    sample_fields = [
        {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
        {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
        {'name': 'organism', 'label': 'Type microorganisme', 'label_fr': 'Type de microorganisme (Bactérie, levure, moisissure)', 'label_en': 'Microorganism Type', 'order': 2},
        {'name': 'isolation', 'label': 'Source isolement', 'label_fr': "Source d'isolement (environnementale, alimentaire, clinique, etc.)", 'label_en': 'Isolation Source', 'order': 3},
        {'name': 'isolation_date', 'label': 'Date isolement', 'label_fr': "Date d'isolement", 'label_en': 'Isolation Date', 'order': 4},
        {'name': 'culture_medium', 'label': 'Milieu culture', 'label_fr': 'Milieu de culture approprié', 'label_en': 'Culture Medium', 'order': 5},
        {'name': 'culture_conditions', 'label': 'Conditions culture', 'label_fr': 'Conditions de culture (Température, type respiratoire, durée incubation)', 'label_en': 'Culture Conditions', 'order': 6},
        {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 7},
    ]
    
    # Additional info fields
    additional_fields = [
        {'name': 'fresh_cultures', 'label': 'Cultures fraîches', 'label_fr': 'Fourniture de cultures fraîches', 'label_en': 'Fresh Cultures Supplied', 'field_type': 'select', 'options': ['Oui', 'Non'], 'order': 0},
        {'name': 'maldi_target', 'label': 'Cible MALDI', 'label_fr': 'Type de cible MALDI-TOF', 'label_en': 'MALDI-TOF Target Type', 'field_type': 'select', 'options': ['Usage unique obligatoire pour pathogènes'], 'order': 1},
        {'name': 'analysis_mode', 'label': 'Mode analyse', 'label_fr': "Mode d'analyse", 'label_en': 'Analysis Mode', 'field_type': 'select', 'options': ['Simple', 'Duplicata', 'Triplicata'], 'order': 2},
    ]
    
    print("\n[+] Creating sample table columns:")
    for field_data in sample_fields:
        create_field(service, 'sample_table', field_data)
    
    print("\n[+] Creating additional info fields:")
    for field_data in additional_fields:
        create_field(service, 'additional_info', field_data)
    
    print(f"\n[DONE] EGTP-IMT recovery complete!")
    print(f"   Service: {service.name}")
    print(f"   Total fields: {service.form_fields.count()}")

def recover_can():
    """Recover EGTP-CAN fields."""
    print("\n" + "="*60)
    print("Recovering EGTP-CAN (Capillary Electrophoresis)")
    print("="*60)
    
    service = get_or_create_service('EGTP-CAN')
    if not service:
        return
    
    # Sample table columns
    sample_fields = [
        {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
        {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
        {'name': 'origin', 'label': 'Origine', 'label_fr': 'Origine des acides nucleiques', 'label_en': 'Nucleic Acid Origin', 'order': 2},
        {'name': 'nucleic_type', 'label': 'Type', 'label_fr': "Type d'acides nucleiques (plasmidique, chromosomique)", 'label_en': 'Nucleic Acid Type', 'order': 3},
        {'name': 'extraction', 'label': 'Méthode extraction', 'label_fr': "Méthode d'extraction utilisée", 'label_en': 'Extraction Method Used', 'order': 4},
        {'name': 'extraction_date', 'label': 'Date extraction', 'label_fr': "Date de l'extraction", 'label_en': 'Extraction Date', 'order': 5},
        {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
    ]
    
    # Additional info fields
    additional_fields = [
        {'name': 'qc_techniques', 'label': 'Techniques QC', 'label_fr': 'Techniques de contrôle qualité souhaitées', 'label_en': 'Requested QC Techniques', 'field_type': 'select', 'options': [], 'order': 0},
        {'name': 'gel_percentage', 'label': '% agarose', 'label_fr': "Pourcentage de gel d'agarose souhaité (si demandé)", 'label_en': 'Desired Agarose Gel Percentage', 'field_type': 'text', 'order': 1},
        {'name': 'size_marker', 'label': 'Marqueur', 'label_fr': "Marqueur de taille pour l'électrophorèse", 'label_en': 'Size Marker for Electrophoresis', 'field_type': 'select', 'options': [], 'order': 2},
    ]
    
    print("\n[+] Creating sample table columns:")
    for field_data in sample_fields:
        create_field(service, 'sample_table', field_data)
    
    print("\n[+] Creating additional info fields:")
    for field_data in additional_fields:
        create_field(service, 'additional_info', field_data)
    
    print(f"\n[DONE] EGTP-CAN recovery complete!")
    print(f"   Service: {service.name}")
    print(f"   Total fields: {service.form_fields.count()}")

if __name__ == '__main__':
    print("\n[PLAGENOR 4.0 - Form Field Recovery]")
    print("Recovering lost fields from EGTP-IMT and EGTP-CAN services\n")

    recover_imt()
    recover_can()

    print("\n" + "="*60)
    print("[RECOVERY COMPLETE]")
    print("="*60)
