"""Populate the eight existing services in French, Arabic and English.

Only empty fields or copies of the original untranslated text are replaced.
Administrator-authored translations and all financial data are preserved.
"""
from django.db import migrations

TRANSLATIONS = {'EGTP-CAN': {'description_ar': 'مراقبة جودة الأحماض النووية (DNA أو RNA)، وتشمل القياس الكمي بالتألق وتقييم '
                                'سلامتها بالرحلان الكهربائي على هلام الأغاروز. تهدف هذه الخدمة إلى تقييم مدى '
                                'ملاءمة العينات للتحليلات الجزيئية اللاحقة.',
              'description_en': 'Quality control of nucleic acids (DNA or RNA) including fluorimetric '
                                'quantification and integrity assessment by agarose gel electrophoresis. '
                                'This service is intended to assess sample suitability prior to downstream '
                                'molecular analyses.',
              'description_fr': 'Contrôle qualité des acides nucléiques (ADN ou ARN), comprenant la '
                                'quantification fluorimétrique et l’évaluation de l’intégrité par '
                                'électrophorèse sur gel d’agarose. Cette prestation permet d’évaluer '
                                'l’adéquation des échantillons avant les analyses moléculaires ultérieures.',
              'name_ar': 'مراقبة جودة الأحماض النووية',
              'name_en': 'Nucleic Acid Quality Control',
              'name_fr': 'Contrôle qualité des acides nucléiques'},
 'EGTP-IMT': {'description_ar': 'التعرّف السريع والموثوق على البكتيريا والخمائر والعفن باستخدام مطيافية '
                                'الكتلة MALDI-TOF (البصمة البروتينية) على منصة MALDI Biotyper.',
              'description_en': 'Rapid and reliable identification of bacteria, yeasts and moulds by '
                                'MALDI-TOF mass spectrometry (protein profiling) on the MALDI Biotyper '
                                'platform.',
              'description_fr': 'Identification microbienne rapide et fiable des bactéries, levures et '
                                'moisissures par spectrométrie de masse MALDI-TOF (profil protéique) sur '
                                'plateforme MALDI Biotyper.',
              'name_ar': 'التعرّف على الكائنات الحية الدقيقة بتقنية MALDI-TOF MS',
              'name_en': 'Microbial Identification by MALDI-TOF MS',
              'name_fr': 'Identification microbienne via MALDI-TOF MS'},
 'EGTP-Illumina-Microbial-WGS': {'description_ar': 'تسلسل الجينوم الكامل (WGS) للعزلات الميكروبية بتقنية '
                                                   'Illumina عالية الإنتاجية. تشمل الخدمة استخلاص الحمض '
                                                   'النووي الجينومي من مزارع نقية، ومراقبة جودة الأحماض '
                                                   'النووية، وتحضير مكتبات Illumina، والتسلسل بقراءات مزدوجة '
                                                   'النهاية، وتسليم بيانات التسلسل الخام.',
                                 'description_en': 'Whole Genome Sequencing (WGS) of microbial isolates '
                                                   'using Illumina high-throughput sequencing technology. '
                                                   'The service includes genomic DNA extraction from pure '
                                                   'cultures, nucleic acid quality control, Illumina library '
                                                   'preparation, paired-end sequencing, and delivery of raw '
                                                   'sequencing data.',
                                 'description_fr': 'Séquençage du génome entier (WGS) d’isolats microbiens '
                                                   'par la technologie Illumina à haut débit. La prestation '
                                                   'comprend l’extraction de l’ADN génomique à partir de '
                                                   'cultures pures, le contrôle qualité des acides '
                                                   'nucléiques, la préparation des banques Illumina, le '
                                                   'séquençage à lectures appariées et la remise des données '
                                                   'brutes de séquençage.',
                                 'name_ar': 'تسلسل الجينوم الميكروبي الكامل (Illumina)',
                                 'name_en': 'Microbial Whole Genome Sequencing (Illumina)',
                                 'name_fr': 'Séquençage du génome entier microbien (Illumina)'},
 'EGTP-Lyoph': {'description_ar': 'تجفيف العينات البيولوجية بالتجميد لإزالة الماء بالتسامي تحت التفريغ وفي '
                                  'درجة حرارة منخفضة، باستخدام جهاز التجفيف بالتجميد Beta 2-8 LSCplus '
                                  '(Martin Christ، ألمانيا).',
                'description_en': 'Freeze-drying of biological samples to remove water by sublimation under '
                                  'vacuum at low temperature, using the Beta 2-8 LSCplus freeze dryer '
                                  '(Martin Christ, Germany).',
                'description_fr': 'Lyophilisation (séchage à froid sous vide) d’échantillons biologiques '
                                  'afin d’éliminer l’eau par sublimation sous vide à basse température, en '
                                  'utilisant le lyophilisateur Beta 2-8 LSCplus (Martin Christ, Allemagne).',
                'name_ar': 'التجفيف بالتجميد تحت التفريغ',
                'name_en': 'Freeze-drying — Lyophilisation',
                'name_fr': 'Séchage à froid sous vide – Lyophilisation'},
 'EGTP-PCR': {'description_ar': 'تفاعل البوليميراز المتسلسل (PCR) تقنية في البيولوجيا الجزيئية لتضخيم '
                                'تسلسلات محددة من الحمض النووي DNA. تشمل الخدمة تحضير التفاعل باستخدام '
                                'البادئات التي يقدّمها صاحب الطلب، والتضخيم بجهاز تدوير حراري ذي تدرّج '
                                'حراري، والتحقق بالرحلان الكهربائي على هلام الأغاروز.',
              'description_en': 'PCR (Polymerase Chain Reaction) is a molecular biology technique used to '
                                'amplify specific DNA sequences. The service includes reaction setup using '
                                'requester-supplied primers, amplification on a gradient thermal cycler, and '
                                'verification by agarose gel electrophoresis.',
              'description_fr': 'La réaction en chaîne par polymérase (PCR) est une technique de biologie '
                                'moléculaire permettant d’amplifier des séquences d’ADN spécifiques. La '
                                'prestation comprend la préparation de la réaction avec les amorces fournies '
                                'par le demandeur, l’amplification sur un thermocycleur à gradient et la '
                                'vérification par électrophorèse sur gel d’agarose.',
              'name_ar': 'تفاعل البوليميراز المتسلسل (PCR)',
              'name_en': 'PCR (Polymerase Chain Reaction)',
              'name_fr': 'PCR — Réaction en chaîne par polymérase'},
 'EGTP-PS': {'description_ar': 'تصنيع أزواج من بادئات الحمض النووي DNA (أمامية وعكسية) حسب الطلب باستخدام '
                               'جهاز MerMade 4 القائم على كيمياء الفوسفوراميديت. تُصنّع البادئات حصراً وفق '
                               'التسلسلات التي يقدّمها صاحب الطلب. تشمل الخدمة التنقية القياسية بإزالة '
                               'الأملاح بالبوتانول والتسليم بتركيز محدد. لا تشمل الخدمة تصميم البادئات أو '
                               'اعتماد التسلسلات أو التحقق منها.',
             'description_en': 'Custom synthesis of DNA oligonucleotide primer pairs (Forward + Reverse) '
                               'performed on a MerMade 4 phosphoramidite synthesizer. Primers are '
                               'synthesized strictly according to sequences provided by the requester. The '
                               'service includes standard butanol desalting purification and delivery at '
                               'defined concentration. No primer design, validation, or sequence '
                               'verification is performed.',
             'description_fr': 'Synthèse sur mesure de paires d’amorces oligonucléotidiques d’ADN (sens et '
                               'antisens) sur un synthétiseur à phosphoramidites MerMade 4. Les amorces sont '
                               'synthétisées strictement selon les séquences fournies par le demandeur. La '
                               'prestation comprend une purification standard par dessalage au butanol et '
                               'une livraison à concentration définie. Aucune conception d’amorces, '
                               'validation ou vérification des séquences n’est réalisée.',
             'name_ar': 'تصنيع بادئات الحمض النووي DNA حسب الطلب',
             'name_en': 'Custom DNA Primer Synthesis',
             'name_fr': 'Synthèse d’amorces d’ADN sur mesure'},
 'EGTP-Seq02': {'description_ar': 'التعرّف التصنيفي على الكائنات الحية الدقيقة بتسلسل سانغر لنواتج تضخيم '
                                  'PCR، باستخدام واسمات جينية عامة مثل الرنا الريبوسومي 16S وITS والرنا '
                                  'الريبوسومي 18S. تشمل الخدمة استخلاص DNA، والتضخيم بتقنية PCR، وتنقية '
                                  'نواتج التضخيم، وتسلسل سانغر. يُحدّد الكائن على مستوى النوع عندما تسمح '
                                  'جودة التسلسل وتغطية قواعد البيانات بذلك.',
                'description_en': 'Accurate taxonomic identification of microorganisms using PCR amplicon '
                                  'Sanger sequencing with universal genetic markers such as 16S rRNA, ITS, '
                                  'and 18S rRNA. The workflow includes DNA extraction, PCR amplification, '
                                  'amplicon cleanup, and Sanger sequencing. Identification is reported at '
                                  'species level when sequence quality and database coverage allow.',
                'description_fr': 'Identification taxonomique des microorganismes par séquençage Sanger '
                                  'd’amplicons PCR, à l’aide de marqueurs génétiques universels tels que '
                                  'l’ARNr 16S, l’ITS et l’ARNr 18S. La prestation comprend l’extraction de '
                                  'l’ADN, l’amplification PCR, la purification des amplicons et le '
                                  'séquençage Sanger. L’identification est rapportée au niveau de l’espèce '
                                  'lorsque la qualité des séquences et la couverture des bases de données le '
                                  'permettent.',
                'name_ar': 'التعرّف على الكائنات الحية الدقيقة بالتسلسل',
                'name_en': 'Microbial Identification via Sequencing',
                'name_fr': 'Identification microbienne par séquençage'},
 'EGTP-SeqS': {'description_ar': 'تسلسل عالي الجودة للحمض النووي DNA بطريقة سانغر لنواتج تضخيم PCR. تدعم '
                                 'الخدمة نواتج PCR المنقّاة وغير المنقّاة، بقراءات أمامية أو عكسية أو في '
                                 'الاتجاهين. تُسلّم النتائج في صورة مخططات كروماتوغرافية وملفات تسلسل FASTA. '
                                 'لا تشمل الخدمة التعرّف على الكائنات أو تفسير النتائج.',
               'description_en': 'High-quality DNA sequencing using the Sanger method for PCR amplicons. The '
                                 'service supports sequencing of purified or non-purified PCR products using '
                                 'forward, reverse, or bidirectional reads. Results are delivered as '
                                 'chromatograms and FASTA sequence files. No identification or '
                                 'interpretation is included.',
               'description_fr': 'Séquençage de haute qualité de l’ADN par la méthode Sanger pour les '
                                 'amplicons PCR. La prestation prend en charge les produits PCR purifiés ou '
                                 'non purifiés, avec des lectures sens, antisens ou bidirectionnelles. Les '
                                 'résultats sont remis sous forme de chromatogrammes et de fichiers de '
                                 'séquences FASTA. Aucune identification ni interprétation n’est incluse.',
               'name_ar': 'تسلسل الحمض النووي DNA بطريقة سانغر',
               'name_en': 'DNA Sequencing via Sanger Method',
               'name_fr': 'Séquençage de l’ADN par la méthode Sanger'}}


def translate_catalogue(apps, schema_editor):
    Service = apps.get_model('core', 'Service')
    for code, translations in TRANSLATIONS.items():
        source_values = set(translations.values())
        for service in Service.objects.using(schema_editor.connection.alias).filter(code=code):
            changes = {}
            for field, value in translations.items():
                current = getattr(service, field)
                if not current or not current.strip() or current.strip() in source_values:
                    changes[field] = value
            Service.objects.using(schema_editor.connection.alias).filter(pk=service.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [('core', '0030_issued_document_archive')]
    operations = [migrations.RunPython(translate_catalogue, migrations.RunPython.noop)]
