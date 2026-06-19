from django.core.management.base import BaseCommand
from core.models import PlatformContent

DEFAULTS_FR = {
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
    'footer_contact_1': "École Supérieure en Sciences Biologiques d'Oran (ESSBO)",
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
    'contact_address': "ESSBO, Cité Emir Abdelkader (EX-INESSMO), 31000 Oran, Algérie",
    'contact_email': 'genomicsplatform.essbo@gmail.com',
    'contact_phone': '+213 (0) 41 XX XX XX',
    'contact_name': 'Prof. Mohamed Merzoug',
    'contact_platform': 'PLAGENOR 4.0',

    # Login page
    'login_title': 'Connexion',
    'login_subtitle': 'Accédez à votre espace PLAGENOR',
    'login_logo_text': 'PLAGENOR 4.0',
    'login_logo_sub': 'Plateforme de Gestion des Opérations',
    'login_footer_1': "École Supérieure en Sciences Biologiques d'Oran (ESSBO)",
    'login_footer_2': 'Conçu par Prof. Mohamed Merzoug',

    # === GENOCLAB commercial documents (devis & facture) =================
    # Every field here is rendered in the generated quote / invoice.
    # SuperAdmin can edit any of them at /dashboard/home/content/update/
    # (or via /admin/) — change the bank account / NIF / footer wording
    # without touching code.
    'genoclab_quote_title':       'Facture Proforma',
    'genoclab_invoice_title':     'Facture',
    'genoclab_issuer_name':       "École Supérieure en Sciences Biologiques d'Oran (ESSBO)",
    'genoclab_issuer_address1':   'BP 1042 SAIM MOHAMED,',
    'genoclab_issuer_address2':   'Cité Emir Abdelkader (EX-INESSMO)',
    'genoclab_issuer_address3':   '31000 Oran',
    'genoclab_issuer_treasury':   'Cpte Trésor : 00831001131000208471',
    'genoclab_issuer_nif':        'N.I.F : 415020000310784',
    'genoclab_issuer_ccp':        "Cpte CCP Agent comptable de l'ESSBO : 007999990000",
    'genoclab_issuer_phone':      'Téléphone / Fax : +213 41 24 63 59',
    'genoclab_vat_rate':          '0.19',
    'genoclab_footer_legal':      (
        'Arrêtée la présente facture à la somme de '
        '____________________________________________________________ Dinars Algériens.'
    ),
    'genoclab_footer_office':     (
        'Siège social — BP 1042 SAIM MOHAMED, Cité Emir Abdelkader (EX-INESSMO), 31000 Oran'
    ),
    'genoclab_footer_contact':    (
        "École Supérieure en Sciences Biologiques d'Oran (ESSBO) · "
        'https://essb-oran.edu.dz/'
    ),
}

DEFAULTS_EN = {
    'nav_brand': 'PLAGENOR 4.0',
    'hero_title': 'PLAGENOR 4.0',
    'hero_subtitle': 'Genomics Technology Platform — ESSBO · ORAN',
    'hero_description': "Integrated solution for managing analysis requests, tracking operations, and billing within ESSBO.",
    'hero_btn_submit': 'Submit a request',
    'hero_btn_guest': 'Guest submission',
    'hero_btn_services': 'View services',
    'hero_btn_track': 'Track request',
    'ibtikar_title': 'IBTIKAR',
    'ibtikar_description': "Channel dedicated to ESSBO students and researchers. Submit your analysis requests as part of your research projects with funding framed by the IBTIKAR budget.",
    'genoclab_title': 'GENOCLAB',
    'genoclab_description': "Channel for external clients — universities, companies, laboratories. Request a quote, receive an invoice, and benefit from our scientific analysis services.",
    'institutions_title': 'INSTITUTIONS & PARTNERS',
    'services_title': 'Our Services',
    'services_subtitle': 'Scientific and technical analyses offered by the ESSBO laboratory',
    'org_title': 'Organization',
    'org_subtitle': 'ESSBO → PLAGENOR → GENOCLAB',
    'org_description': "The Higher School of Biological Sciences of Oran (ESSBO) hosts the PLAGENOR platform, which manages two service channels: IBTIKAR for the internal academic community, and GENOCLAB for external services.",
    'footer_brand': 'PLAGENOR 4.0',
    'footer_description': "ESSBO Scientific Operations Management Platform. Developed for managing the IBTIKAR and GENOCLAB channels.",
    'footer_copyright': '© 2026 ESSBO — All rights reserved',
    'footer_credit': 'PLAGENOR 4.0 — Designed by Prof. Mohamed Merzoug | ESSBO',
    'footer_contact_1': "Higher School of Biological Sciences of Oran (ESSBO)",
    'footer_contact_2': 'Prof. Mohamed Merzoug',
    'about_title': 'About PLAGENOR',
    'about_intro': "ESSBO (Higher School of Biological Sciences of Oran) hosts PLAGENOR, a shared research service funded by DGRSDT (General Directorate for Scientific Research and Technological Development).",
    'about_genoclab': "PLAGENOR hosts GENOCLAB, the commercial subsidiary (SPA) of ESSBO, governed by Algerian commercial code.",
    'about_plagenor': "PLAGENOR 4.0 is the digital platform managing all PLAGENOR activities — acting as an internal ERP to organize workflows, handle IBTIKAR requests and GENOCLAB clients.",
    'about_missions_title': 'Two missions',
    'about_ibtikar_mission': "Academic channel: perform genomic analyses for graduating students (Master, Engineering) and doctoral candidates from all Algerian universities, to promote scientific research in Algeria. Each eligible student has an annual virtual budget of 200,000 DA managed by DGRSDT.",
    'about_genoclab_mission': "Commercial channel: provide the same genomic analyses to external clients (companies, hospitals, private laboratories, individuals) on a commercial basis with invoicing, 19% VAT, and real payment.",
    'about_services_title': 'Services',
    'about_services_desc': "Microbial identification (MALDI-TOF), Sanger & Illumina sequencing, PCR, nucleic acid quality control, lyophilization, primer synthesis.",
    'about_contact_title': 'Contact',
    'about_contact_name': 'Prof. Mohamed Merzoug',
    'about_contact_email': 'mohamed.merzouge.essbo@email.com',
    'about_contact_phone': '041 24 63 59',
    'about_contact_address': 'Cité Emir Abdelkader, 31000 Oran',
    'contact_title': 'Contact us',
    'contact_subtitle': "For any question, do not hesitate to contact us.",
    'contact_institution': "ESSBO — Higher School of Biological Sciences of Oran",
    'contact_address': "ESSBO, Cité Emir Abdelkader (EX-INESSMO), 31000 Oran, Algeria",
    'contact_email': 'genomicsplatform.essbo@gmail.com',
    'contact_phone': '+213 (0) 41 XX XX XX',
    'contact_name': 'Prof. Mohamed Merzoug',
    'contact_platform': 'PLAGENOR 4.0',
    'login_title': 'Sign in',
    'login_subtitle': 'Access your PLAGENOR workspace',
    'login_logo_text': 'PLAGENOR 4.0',
    'login_logo_sub': 'Operations Management Platform',
    'login_footer_1': "Higher School of Biological Sciences of Oran (ESSBO)",
    'login_footer_2': 'Designed by Prof. Mohamed Merzoug',
}

DEFAULTS_AR = {
    'nav_brand': 'PLAGENOR 4.0',
    'hero_title': 'PLAGENOR 4.0',
    'hero_subtitle': 'منصة التكنولوجيا الجينومية — ESSBO · وهران',
    'hero_description': "حل متكامل لإدارة طلبات التحليل ومتابعة العمليات والفوترة داخل ESSBO.",
    'hero_btn_submit': 'إرسال طلب',
    'hero_btn_guest': 'إرسال كزائر',
    'hero_btn_services': 'عرض الخدمات',
    'hero_btn_track': 'تتبع الطلب',
    'ibtikar_title': 'IBTIKAR',
    'ibtikar_description': "قناة مخصصة لطلاب وباحثي ESSBO. أرسل طلبات التحليل في إطار مشاريعك البحثية بتمويل من ميزانية IBTIKAR.",
    'genoclab_title': 'GENOCLAB',
    'genoclab_description': "قناة للعملاء الخارجيين — جامعات وشركات ومخابر. اطلب عرض أسعار، استلم فاتورة، واستفد من خدمات التحليل العلمي لدينا.",
    'institutions_title': 'المؤسسات والشركاء',
    'services_title': 'خدماتنا',
    'services_subtitle': 'التحاليل العلمية والتقنية المقدمة من مخبر ESSBO',
    'org_title': 'التنظيم',
    'org_subtitle': 'ESSBO → PLAGENOR → GENOCLAB',
    'org_description': "تستضيف المدرسة العليا للعلوم البيولوجية بوهران (ESSBO) منصة PLAGENOR التي تدير قناتين: IBTIKAR للمجتمع الأكاديمي الداخلي وGENOCLAB للخدمات الخارجية.",
    'footer_brand': 'PLAGENOR 4.0',
    'footer_description': "منصة إدارة العمليات العلمية لـ ESSBO. مطورة لإدارة قناتي IBTIKAR وGENOCLAB.",
    'footer_copyright': '© 2026 ESSBO — جميع الحقوق محفوظة',
    'footer_credit': 'PLAGENOR 4.0 — تصميم البروفيسور محمد مرزوق | ESSBO',
    'footer_contact_1': "ESSBO — جامعة وهران",
    'footer_contact_2': 'البروفيسور محمد مرزوق',
    'about_title': 'حول PLAGENOR',
    'about_intro': "تستضيف ESSBO منصة PLAGENOR، خدمة بحثية مشتركة ممولة من DGRSDT.",
    'about_genoclab': "تستضيف PLAGENOR شركة GENOCLAB، الفرع التجاري لـ ESSBO، الخاضع لقانون التجارة الجزائري.",
    'about_plagenor': "PLAGENOR 4.0 هي المنصة الرقمية لإدارة جميع أنشطة PLAGENOR، تعمل كنظام ERP داخلي لتنظيم سير العمل وإدارة طلبات IBTIKAR وعملاء GENOCLAB.",
    'about_missions_title': 'مهمتان',
    'about_ibtikar_mission': "القناة الأكاديمية: إجراء تحاليل جينومية لطلبة نهاية الدراسة (ماستر، مهندس) وطلبة الدكتوراه من جميع الجامعات الجزائرية لتعزيز البحث العلمي في الجزائر. لكل طالب مؤهل ميزانية افتراضية سنوية قدرها 200،000 دج تديرها DGRSDT.",
    'about_genoclab_mission': "القناة التجارية: تقديم نفس التحاليل الجينومية للعملاء الخارجيين (شركات، مستشفيات، مخابر خاصة، أفراد) على أساس تجاري مع فوترة ورسم القيمة المضافة 19٪ ودفع فعلي.",
    'about_services_title': 'الخدمات',
    'about_services_desc': "التعرف على الميكروبات (MALDI-TOF)، التسلسل Sanger و Illumina، PCR، مراقبة جودة الأحماض النووية، التجفيف بالتجميد، تركيب البادئات.",
    'about_contact_title': 'الاتصال',
    'about_contact_name': 'البروفيسور محمد مرزوق',
    'about_contact_email': 'mohamed.merzouge.essbo@email.com',
    'about_contact_phone': '041 24 63 59',
    'about_contact_address': 'حي الأمير عبد القادر، 31000 وهران',
    'contact_title': 'اتصل بنا',
    'contact_subtitle': "لأي استفسار، لا تتردد في الاتصال بنا.",
    'contact_institution': "ESSBO — المدرسة العليا للعلوم البيولوجية بوهران",
    'contact_address': "جامعة وهران، وهران، الجزائر",
    'contact_email': 'genomicsplatform.essbo@gmail.com',
    'contact_phone': '+213 (0) 41 XX XX XX',
    'contact_name': 'البروفيسور محمد مرزوق',
    'contact_platform': 'PLAGENOR 4.0',
    'login_title': 'تسجيل الدخول',
    'login_subtitle': 'ادخل إلى مساحتك في PLAGENOR',
    'login_logo_text': 'PLAGENOR 4.0',
    'login_logo_sub': 'منصة إدارة العمليات',
    'login_footer_1': "ESSBO — جامعة وهران",
    'login_footer_2': 'تصميم البروفيسور محمد مرزوق',
}

DEFAULTS_BY_LANG = {
    'fr': DEFAULTS_FR,
    'en': DEFAULTS_EN,
    'ar': DEFAULTS_AR,
}


class Command(BaseCommand):
    help = 'Seed default PlatformContent entries for every supported language'

    def handle(self, *args, **options):
        total = 0
        for lang, entries in DEFAULTS_BY_LANG.items():
            for key, value in entries.items():
                obj, created = PlatformContent.objects.get_or_create(
                    key=key,
                    lang=lang,
                    defaults={'value': value},
                )
                status = 'Created' if created else 'Exists'
                self.stdout.write(f'  [{status}] {key} [{lang}]')
                total += 1
        self.stdout.write(self.style.SUCCESS(f'Done: {total} content entries across {len(DEFAULTS_BY_LANG)} languages'))
