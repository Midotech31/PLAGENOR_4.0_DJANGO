"""Correct national IBTIKAR scope in existing multilingual CMS content."""
from django.db import migrations

CHANGES = [('fr',
  'ibtikar_description',
  "Canal dédié aux étudiants et chercheurs de l'ESSBO. Soumettez vos demandes d'analyses dans le cadre de "
  'vos projets de recherche avec un financement encadré par le budget IBTIKAR.',
  'IBTIKAR s’adresse aux étudiants algériens, quel que soit leur établissement. Soumettez vos demandes '
  'd’analyses pour vos projets d’études et de recherche, selon les conditions du dispositif IBTIKAR.'),
 ('fr',
  'org_description',
  "L'École Supérieure des Sciences Biologiques d'Oran (ESSBO) héberge la plateforme PLAGENOR, qui gère deux "
  'canaux de service : IBTIKAR pour la communauté académique interne, et GENOCLAB pour les prestations '
  'externes.',
  'PLAGENOR est la plateforme technologique de génomique de l’École Supérieure en Sciences Biologiques '
  'd’Oran (ESSBO). Elle accueille les demandes des étudiants algériens via IBTIKAR et les demandes de '
  'prestations scientifiques et techniques.'),
 ('fr',
  'footer_description',
  "Plateforme de Gestion des Opérations Scientifiques de l'ESSBO. Développée pour la gestion des canaux "
  'IBTIKAR et GENOCLAB.',
  'PLAGENOR — Plateforme technologique de génomique de l’ESSBO. Demandes d’analyses, suivi des prestations '
  'et remise des résultats.'),
 ('fr',
  'about_plagenor',
  'PLAGENOR 4.0 est la plateforme numérique de gestion de toutes les activités de PLAGENOR — agissant comme '
  'un ERP interne pour organiser les flux de travail, gérer les demandes IBTIKAR et les clients GENOCLAB.',
  'PLAGENOR 4.0 permet de soumettre et de suivre les demandes d’analyses, de gérer les prestations et de '
  'consulter les documents et résultats.'),
 ('en',
  'ibtikar_description',
  'Channel dedicated to ESSBO students and researchers. Submit your analysis requests as part of your '
  'research projects with funding framed by the IBTIKAR budget.',
  'IBTIKAR is open to Algerian students, regardless of their institution. Submit analysis requests for your '
  'study and research projects, subject to the IBTIKAR programme’s conditions.'),
 ('en',
  'org_description',
  'The Higher School of Biological Sciences of Oran (ESSBO) hosts the PLAGENOR platform, which manages two '
  'service channels: IBTIKAR for the internal academic community, and GENOCLAB for external services.',
  'PLAGENOR is the genomics technology platform of the Higher School of Biological Sciences of Oran (ESSBO). '
  'It handles requests from Algerian students through IBTIKAR and requests for scientific and technical '
  'services.'),
 ('en',
  'footer_description',
  'ESSBO Scientific Operations Management Platform. Developed for managing the IBTIKAR and GENOCLAB '
  'channels.',
  'PLAGENOR — ESSBO Genomics Technology Platform. Analysis requests, service tracking and delivery of '
  'results.'),
 ('en',
  'about_plagenor',
  'PLAGENOR 4.0 is the digital platform managing all PLAGENOR activities — acting as an internal ERP to '
  'organize workflows, handle IBTIKAR requests and GENOCLAB clients.',
  'PLAGENOR 4.0 lets you submit and track analysis requests, manage services, and access documents and '
  'results.'),
 ('ar',
  'ibtikar_description',
  'قناة مخصصة لطلاب وباحثي ESSBO. أرسل طلبات التحليل في إطار مشاريعك البحثية بتمويل من ميزانية IBTIKAR.',
  'خدمات IBTIKAR متاحة للطلبة الجزائريين، مهما كانت مؤسسة انتمائهم. قدّموا طلبات التحليل لمشاريعكم الدراسية '
  'والبحثية وفق شروط برنامج IBTIKAR.'),
 ('ar',
  'org_description',
  'تستضيف المدرسة العليا للعلوم البيولوجية بوهران (ESSBO) منصة PLAGENOR التي تدير قناتين: IBTIKAR للمجتمع '
  'الأكاديمي الداخلي وGENOCLAB للخدمات الخارجية.',
  'PLAGENOR هي منصة تكنولوجيا الجينوم التابعة للمدرسة العليا للعلوم البيولوجية بوهران (ESSBO). تستقبل طلبات '
  'الطلبة الجزائريين عبر IBTIKAR وطلبات الخدمات العلمية والتقنية.'),
 ('ar',
  'footer_description',
  'منصة إدارة العمليات العلمية لـ ESSBO. مطورة لإدارة قناتي IBTIKAR وGENOCLAB.',
  'PLAGENOR — منصة تكنولوجيا الجينوم التابعة لـ ESSBO. طلبات التحليل ومتابعة الخدمات وتسليم النتائج.'),
 ('ar',
  'about_plagenor',
  'PLAGENOR 4.0 هي المنصة الرقمية لإدارة جميع أنشطة PLAGENOR، تعمل كنظام ERP داخلي لتنظيم سير العمل وإدارة '
  'طلبات IBTIKAR وعملاء GENOCLAB.',
  'تتيح PLAGENOR 4.0 تقديم طلبات التحليل ومتابعتها وإدارة الخدمات والاطلاع على الوثائق والنتائج.')]

def forwards(apps, schema_editor):
    Content = apps.get_model('core', 'PlatformContent')
    for lang, key, old, new in CHANGES:
        rows = Content.objects.filter(key=key, lang=lang)
        if key == 'ibtikar_description':
            # Explicit institutional correction, including previously edited text.
            Content.objects.update_or_create(key=key, lang=lang, defaults={'value': new})
        else:
            rows.filter(value=old).update(value=new)

class Migration(migrations.Migration):
    dependencies = [('core', '0027_financialvisibility_invoice_document_snapshot_and_more')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
