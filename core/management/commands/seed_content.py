from django.core.management.base import BaseCommand
from core.models import PlatformContent

DEFAULTS = {
    # Navigation
    'nav_brand': 'PLAGENOR 4.0',

    # Hero section
    'hero_title': 'PLAGENOR 4.0',
    'hero_subtitle': 'Plateforme Technologique de Génomique — ESSBO · ORAN',
    'hero_description': "Solution intégrée pour la gestion des demandes d'analyses, le suivi des opérations et la facturation au sein de l'ESSBO.",
    'hero_btn_submit': 'Soumettre une demande',
    'hero_btn_guest': 'Soumission invité',
    'hero_btn_services': 'Voir les services',
    'hero_btn_track': 'Suivi de demande',

    # Channel cards
    'ibtikar_title': 'IBTIKAR',
    'ibtikar_description': "Canal dédié aux étudiants et chercheurs de l'ESSBO. Soumettez vos demandes d'analyses dans le cadre de vos projets de recherche avec un financement encadré par le budget IBTIKAR.",
    'genoclab_title': 'GENOCLAB',
    'genoclab_description': "Canal pour les clients externes — universités, entreprises, laboratoires. Demandez un devis, recevez une facture et bénéficiez de nos services d'analyses scientifiques.",

    # Institutions section
    'institutions_title': 'INSTITUTIONS & PARTENAIRES',

    # Services section
    'services_title': 'Nos Services',
    'services_subtitle': 'Analyses scientifiques et techniques proposées par le laboratoire ESSBO',

    # Organization section
    'org_title': 'Organisation',
    'org_subtitle': 'ESSBO → PLAGENOR → GENOCLAB',
    'org_description': "L'École Supérieure des Sciences Biologiques d'Oran (ESSBO) héberge la plateforme PLAGENOR, qui gère deux canaux de service : IBTIKAR pour la communauté académique interne, et GENOCLAB pour les prestations externes.",

    # Footer
    'footer_brand': 'PLAGENOR 4.0',
    'footer_description': "Plateforme de Gestion des Opérations Scientifiques de l'ESSBO. Développée pour la gestion des canaux IBTIKAR et GENOCLAB.",
    'footer_copyright': '© 2026 ESSBO — Tous droits réservés',
    'footer_credit': 'PLAGENOR 4.0 — Conçu par Prof. Mohamed Merzoug | ESSBO',
    'footer_contact_1': "ESSBO — Université d'Oran",
    'footer_contact_2': 'Prof. Mohamed Merzoug',

    # About page
    'about_title': 'À propos de PLAGENOR',
    'about_intro': "L'ESSBO (École Supérieure en Sciences Biologiques d'Oran) héberge PLAGENOR, un service commun de recherche financé par la DGRSDT (Direction Générale de la Recherche Scientifique et du Développement Technologique).",
    'about_genoclab': "PLAGENOR héberge GENOCLAB, la filiale commerciale (SPA) de l'ESSBO, régie par le code de commerce algérien.",
    'about_plagenor': "PLAGENOR 4.0 est la plateforme numérique de gestion de toutes les activités de PLAGENOR — agissant comme un ERP interne pour organiser les flux de travail, gérer les demandes IBTIKAR et les clients GENOCLAB.",
    'about_missions_title': 'Deux missions',
    'about_ibtikar_mission': "Canal académique : réaliser des analyses génomiques pour les étudiants de fin de cycle (Master, Ingéniorat) et les doctorants de toutes les universités algériennes, afin de promouvoir la recherche scientifique en Algérie. Chaque étudiant éligible dispose d'un budget annuel virtuel de 200 000 DA géré par la DGRSDT.",
    'about_genoclab_mission': "Canal commercial : fournir les mêmes analyses génomiques aux clients externes (entreprises, hôpitaux, laboratoires privés, particuliers) sur une base commerciale avec facturation, TVA 19%, et paiement réel.",
    'about_services_title': 'Services',
    'about_services_desc': "Identification microbienne (MALDI-TOF), séquençage Sanger & Illumina, PCR, contrôle qualité des acides nucléiques, lyophilisation, synthèse d'amorces.",
    'about_contact_title': 'Contact',
    'about_contact_name': 'Prof. Mohamed Merzoug',
    'about_contact_email': 'mohamed.merzouge.essbo@email.com',
    'about_contact_phone': '041 24 63 59',
    'about_contact_address': 'Cité Emir Abdelkader, 31000 Oran',

    # Contact page
    'contact_title': 'Contactez-nous',
    'contact_subtitle': "Pour toute question, n'hésitez pas à nous contacter.",
    'contact_institution': "ESSBO — École Supérieure en Sciences Biologiques d'Oran",
    'contact_address': "Université d'Oran, Oran, Algérie",
    'contact_email': 'contact@plagenor.essbo.dz',
    'contact_phone': '+213 (0) 41 XX XX XX',
    'contact_name': 'Prof. Mohamed Merzoug',
    'contact_platform': 'PLAGENOR 4.0',

    # Login page
    'login_title': 'Connexion',
    'login_subtitle': 'Accédez à votre espace PLAGENOR',
    'login_logo_text': 'PLAGENOR 4.0',
    'login_logo_sub': 'Plateforme de Gestion des Opérations',
    'login_footer_1': "ESSBO — Université d'Oran",
    'login_footer_2': 'Conçu par Prof. Mohamed Merzoug',
}


class Command(BaseCommand):
    help = 'Seed default PlatformContent entries'

    def handle(self, *args, **options):
        for key, value in DEFAULTS.items():
            obj, created = PlatformContent.objects.get_or_create(
                key=key,
                defaults={'value': value}
            )
            status = 'Created' if created else 'Exists'
            self.stdout.write(f'  [{status}] {key}')
        self.stdout.write(self.style.SUCCESS(f'Done: {len(DEFAULTS)} content entries'))
