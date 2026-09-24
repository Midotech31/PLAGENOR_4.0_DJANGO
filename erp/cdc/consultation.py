"""Canonical consultation metadata and conservative source-bound substitutions."""
from __future__ import annotations
import copy
import re
from .docengine import DocumentError

SCHEMA = 2
FIELDS = (
    'object_fr','object_ar','operation_fr','financing_label','budget_year',
    'preparation_days','preparation_fr','preparation_ar',
    'deposit_time','opening_time','validity_months','validity_fr','validity_ar',
    'withdrawal_fr','withdrawal_ar','confirmed',
)

DEFAULTS = {
    'equipment': {
        'object_fr': "Acquisition, installation et mise en service d’équipements scientifiques au profit du FABLAB de l’École Supérieure en Sciences Biologiques d’Oran en 02 lots",
        'object_ar': "اقتناء، تركيب ووضع في الخدمة للأجهزة العلمية المخبرية للقيام بالأشغال التطبيقية والورشات لفائدة مخبر التصنيع (FABLAB) بالمدرسة العليا في العلوم البيولوجية بوهران، مكونة من (02) حصتين",
        'operation_fr': "Acquisition des équipements et appareillages pour le FABLAB de l’ESSBO",
        'financing_label': "Budget d’investissement", 'budget_year': 2026,
        'preparation_days': 21, 'preparation_fr': "Vingt-et-un (21) jours",
        'preparation_ar': "واحد وعشرون (21) يوما", 'deposit_time': '12:00',
        'opening_time': '12:15', 'validity_months': 3,
        'validity_fr': "Trois (03) mois", 'validity_ar': "ثلاثة (03) أشهر",
        'withdrawal_fr': "Les candidats intéressés peuvent directement ou par le bais d’un représentant dûment mandaté par leur soin, retirer le cahier des charges auprès de l’Ecole Supérieure en Sciences Biologiques d’Oran, Cité Emir Abdelkader, Ex-INESSMO, 31000, BP 1042 Saim Mohamed contre paiement de Cinq mille (5000) Dinars Algériens, non remboursables par mandat poste au nom de l’agent comptable de l’Ecole Supérieure en Sciences Biologiques d’Oran, Compte Trésor Numéro du RIB 00831001131000208471. La quittance de paiement constitue une pièce justificative qui doit obligatoirement être jointe au dossier au moment du dépôt de l’offre.",
        'withdrawal_ar': "يتم سحب دفتر الشروط من قبل المرشحين أو ممثليهم الموكلين من طرفهم، من المدرسة العليا في العلوم البيولوجية بوهران - حي الأمير عبد القادر (Ex-INESSMO) ص.ب 1042 صايم محمد 31000 وهران-الجزائر، ابتداء من أول نشر هذا الإعلان في الجرائد الوطنية، مقابل دفع مبلغ خمسة الاف (0005) دينار جزائري غير قابلة للتعويض، مودعة بحوالة بريدية تحت اسم العون المحاسب للمدرسة العليا في العلوم البيولوجية بوهران تحت رقم  00831001131000208471 .",
        'confirmed': False,
    },    'reagents': {
        'object_fr': "Fourniture de réactifs de génomique, de biologie moléculaire et cellulaire, de produits chimiques et de consommables de laboratoire au profit de l’École Supérieure en Sciences Biologiques d’Oran en 04 lots",
        'object_ar': "اقتناء كواشف الجينوميك وكواشف البيولوجيا الجزيئية والخلوية والتسلسل، مواد كيميائية مخبرية ومستلزمات مخبرية لفائدة منصة الجينوميك للمدرسة العليا في العلوم البيولوجية بوهران، موزعة على أربع (04) حصص",
        'operation_fr': "Fourniture de réactifs et consommables de laboratoire",
        'financing_label': "Budget de Fonctionnement", 'budget_year': 2026,
        'preparation_days': 21, 'preparation_fr': "Vingt-et-un (21) jours",
        'preparation_ar': "واحد وعشرون (21) يوماً", 'deposit_time': '12:00',
        'opening_time': '12:15', 'validity_months': 3,
        'validity_fr': "Trois (03) mois", 'validity_ar': "ثلاثة (03) أشهر",
        'withdrawal_fr': "Les candidats intéressés peuvent directement ou par le bais d’un représentant dûment mandaté par leur soin, retirer le cahier des charges auprès de l’Ecole Supérieure en Sciences Biologiques d’Oran, Cité Emir Abdelkader, Ex-INESSMO, 31000, BP 1042 Saim Mohamed contre paiement de Cinq mille (5000) Dinars Algériens, non remboursables par mandat poste au nom de l’agent comptable de l’Ecole Supérieure en Sciences Biologiques d’Oran, Compte Trésor Numéro du RIB 00831001131000208471. La quittance de paiement constitue une pièce justificative qui doit obligatoirement être jointe au dossier au moment du dépôt de l’offre.",
        'withdrawal_ar': "يمكن للمترشحين المهتمين سحب دفتر الشروط من المدرسة العليا في العلوم البيولوجية بوهران – حي الأمير عبد القادر (Ex-INESSMO) ص.ب 1042 صايم محمد، 31000 وهران، ابتداءً من أول نشر لهذا الإعلان في الجرائد الوطنية، مقابل دفع مبلغ خمسة آلاف (5000) دينار جزائري غير قابل للتعويض، يودع في الحساب البريدي الجاري رقم 0000324044 مفتاح 14 باسم العون المحاسب للمدرسة العليا في العلوم البيولوجية بوهران.",
        'confirmed': False,
    },
    'works': {
        'object_fr': "Travaux d’aménagement et de rénovation de l’auditorium au profit de l’Ecole Supérieure en Sciences Biologiques d’Oran en lot unique",
        'object_ar': "أشغال إعادة تأهيل وترميم قاعة المحاضرات (auditorium) الخاصة بالمدرسة العليا في العلوم البيولوجية بوهران، مكونة من حصة واحدة",
        'operation_fr': "Etude et suivi des travaux d’aménagement et de rénovation de l’auditorium au profit de l’Ecole Supérieure en Sciences Biologiques d’Oran en lot unique",
        'financing_label': "investissement", 'budget_year': 2026,
        'preparation_days': 21, 'preparation_fr': "Vingt-et-un (21) jours",
        'preparation_ar': "واحد وعشرون (21) يوما", 'deposit_time': '12:00',
        'opening_time': '12:15', 'validity_months': 3,
        'validity_fr': "Trois (03) mois", 'validity_ar': "ثلاثة (03) أشهر",
        'withdrawal_fr': "Les candidats intéressés peuvent directement ou par le bais d’un représentant dûment mandaté par leur soin, retirer le cahier des charges auprès de l’Ecole Supérieure en Sciences Biologiques d’Oran, Cité Emir Abdelkader, Ex-INESSMO, 31000, BP 1042 Saim Mohamed contre paiement de Cinq mille (5000) Dinars Algériens, non remboursables par mandat poste au nom de l’agent comptable de l’Ecole Supérieure en Sciences Biologiques d’Oran, Compte Trésor Numéro du RIB 00831001131000208471. La quittance de paiement constitue une pièce justificative qui doit obligatoirement être jointe au dossier au moment du dépôt de l’offre.",
        'withdrawal_ar': "يتم سحب دفتر الشروط من قبل المرشحين أو ممثليهم الموكلين من طرفهم، من المدرسة العليا في العلوم البيولوجية بوهران - حي الأمير عبد القادر (Ex-INESSMO) ص.ب 1042 صايم محمد 31000 وهران-الجزائر، ابتداء من أول نشر هذا الإعلان في الجرائد الوطنية، مقابل دفع مبلغ خمسة الاف (0005) دينار جزائري غير قابلة للتعويض، مودعة بحوالة بريدية تحت اسم العون المحاسب للمدرسة العليا في العلوم البيولوجية بوهران تحت رقم  00831001131000208471 .",
        'confirmed': False,
    },
}

def initial_consultation(family):
    if family not in DEFAULTS:
        raise DocumentError('Famille de consultation inconnue.')
    return {'schema': SCHEMA, **copy.deepcopy(DEFAULTS[family])}


def _upgrade(value, family):
    if not isinstance(value, dict):
        raise DocumentError('Fiche de consultation invalide.')
    if value.get('schema') == SCHEMA:
        return copy.deepcopy(value)
    if value.get('schema') == 1:
        upgraded=copy.deepcopy(value);upgraded['schema']=SCHEMA
        upgraded['withdrawal_fr']=DEFAULTS[family]['withdrawal_fr']
        upgraded['withdrawal_ar']=DEFAULTS[family]['withdrawal_ar']
        upgraded['confirmed']=False
        return upgraded
    raise DocumentError('Fiche de consultation invalide.')

def consultation_value(data, family):
    value = data.get('consultation')
    if value is None:
        return initial_consultation(family)
    normalized=_upgrade(value,family)
    validate_consultation(normalized, family)
    return normalized


def validate_consultation(value, family):
    value=_upgrade(value,family)
    if set(value) != {'schema', *FIELDS}:
        raise DocumentError('La fiche de consultation contient des champs manquants ou inconnus.')
    for key in ('object_fr','object_ar','operation_fr','financing_label','preparation_fr','preparation_ar','validity_fr','validity_ar','withdrawal_fr','withdrawal_ar'):
        text = value.get(key)
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise DocumentError(f'Champ de consultation invalide : {key}.')
    if not isinstance(value.get('budget_year'), int) or not 2000 <= value['budget_year'] <= 2100:
        raise DocumentError('Exercice budgétaire invalide.')
    for key, limit in [('preparation_days',365),('validity_months',60)]:
        if not isinstance(value.get(key), int) or not 1 <= value[key] <= limit:
            raise DocumentError(f'Valeur de délai invalide : {key}.')
    if type(value.get('confirmed')) is not bool:
        raise DocumentError('État de validation de la fiche Informations invalide.')
    for key in ('deposit_time','opening_time'):
        if not isinstance(value.get(key), str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value[key]):
            raise DocumentError(f'Heure invalide : {key}.')
    if str(value['preparation_days']).zfill(2) not in value['preparation_fr'] and str(value['preparation_days']) not in value['preparation_fr']:
        raise DocumentError('Le libellé français du délai de préparation ne correspond pas à sa valeur numérique.')
    if str(value['preparation_days']).zfill(2) not in value['preparation_ar'] and str(value['preparation_days']) not in value['preparation_ar']:
        raise DocumentError('Le libellé arabe du délai de préparation ne correspond pas à sa valeur numérique.')
    if str(value['validity_months']).zfill(2) not in value['validity_fr'] and str(value['validity_months']) not in value['validity_fr']:
        raise DocumentError('Le libellé français de validité ne correspond pas à sa valeur numérique.')
    if str(value['validity_months']).zfill(2) not in value['validity_ar'] and str(value['validity_months']) not in value['validity_ar']:
        raise DocumentError('Le libellé arabe de validité ne correspond pas à sa valeur numérique.')
    if family=='reagents' and value['confirmed']:
        account=lambda t:set(re.findall(r'(?<!\d)\d{8,24}(?!\d)',t))
        fr,ar=account(value['withdrawal_fr']),account(value['withdrawal_ar'])
        if not fr or not ar or not (fr & ar):
            raise DocumentError('Les modalités de retrait françaises et arabes doivent utiliser le même numéro de compte.')
    return value


def _display_time(value, arabic=False):
    hour, minute = value.split(':')
    if arabic:
        return f'{int(hour):02d}:{minute}'
    return f'{int(hour):02d}h{minute}'

OBJECT_ALIASES = {
    'equipment': [
        DEFAULTS['equipment']['object_fr'],
        "Acquisition, Acquisition, installation et mise en service d’équipements scientifiques au profit du FABLAB de l’École Supérieure en Sciences Biologiques d’Oran en 02 lots",
        "l’acquisition, l’installation et la mise en service d’équipements scientifiques pour le renforcement des travaux pratiques au profit des étudiants de l’École Supérieure en Sciences Biologiques d’Oran",
    ],
    'reagents': [
        DEFAULTS['reagents']['object_fr'],
        "Fourniture de réactifs de génomique, de biologie moléculaire et cellulaire, de produits chimiques et de consommables de laboratoire au profit de la plateforme de génomique de l’École Supérieure en Sciences Biologiques d’Oran en 04 lots",
    ],
    'works': [
        DEFAULTS['works']['object_fr'],
        DEFAULTS['works']['object_fr'].replace("l'Ecole", 'l’École'),
        DEFAULTS['works']['object_fr'].replace('auditorium au', 'auditorium  au'),
    ],
}

REAGENT_OBJECT_FRAGMENTS = {
    'Le présent cahier des charges a pour objet la fourniture de réactifs de génomique, de biologie moléculaire et cellulaire, de produits chimiques et de consommables de laboratoire au profit de l’École Supérieure en Sciences Biologiques d’Oran en 04 lots indépendants, répartis comme suit\u00a0:': 'cps',
    'La fourniture de réactifs de génomique, de biologie moléculaire et cellulaire, de produits chimiques et de consommables de laboratoire au profit de l’École Supérieure en Sciences Biologiques d’Oran en 04 lots.': 'sentence',
    'Projet\u00a0: Fourniture de réactifs de génomique, de biologie moléculaire et cellulaire, de produits chimiques et de consommables de laboratoire au ': 'project',
    '                 profit de la plateforme de génomique de l’École Supérieure en Sciences Biologiques d’Oran en 04 lots.': 'continuation',
    'Projet\u00a0: Fourniture de réactifs de génomique, de biologie moléculaire et cellulaire, de produits chimiques et de consommables de ': 'project',
    '              laboratoire au profit de l’École Supérieure en Sciences Biologiques d’Oran en 04 lots.': 'continuation',
    'Projet\u00a0: Fourniture de réactifs de génomique, de biologie moléculaire et cellulaire, de produits chimiques et de consommables de     ': 'project',
    '            laboratoire au profit de l’École Supérieure en Sciences Biologiques d’Oran en 04 lots.': 'continuation',
    'Projet : Fourniture de réactifs de génomique, de biologie moléculaire et cellulaire, de produits chimiques et de consommables de laboratoire au profit de l’École Supérieure en Sciences Biologiques d’Oran en 04 lots.': 'project',
}

AR_OBJECT_MARKERS = {
    'equipment': ('اقتناء, تركيب ووضع في الخدمة', 'مكونة من  (02) حصتين'),
    'reagents': ('اقتناء كواشف الجينوميك', 'موزعة على أربع (04) حصص'),
    'works': ('لأشغال إعادة تأهيل وترميم', 'مكونة من حصة واحدة'),
}

def _split_ar(value):
    marker = '(FABLAB)'
    if marker in value:
        left, right = value.split(marker, 1)
        return left.rstrip(), (marker + right).lstrip()
    words = value.split()
    cut = max(1, min(len(words)-1, round(len(words)*0.62)))
    return ' '.join(words[:cut]), ' '.join(words[cut:])


def _replace_object(text, family, value):
    if family == 'reagents' and text in REAGENT_OBJECT_FRAGMENTS:
        kind=REAGENT_OBJECT_FRAGMENTS[text]
        if kind=='cps': return 'Le présent cahier des charges a pour objet : '+value+', répartis comme suit :'
        if kind=='sentence': return value+'.'
        if kind=='project': return ('Projet\u00a0: ' if text.startswith('Projet\u00a0:') else 'Projet : ')+value+'.'
        if kind=='continuation': return ''
    out = text
    for old in sorted(OBJECT_ALIASES[family], key=len, reverse=True):
        if old in out:
            out = out.replace(old, value)
    return out


def _replace_ar_object(text, family, value):
    if family == 'reagents':
        # The Arabic notice uses a full object in the announcement and a shorter
        # object in the anonymous-envelope legend. Both are explicitly project data.
        if 'اقتناء كواشف الجينوميك' in text:
            start=text.index('اقتناء كواشف الجينوميك')
            candidates=[
                'موزعة على أربع (04) حصص',
                'العملية موزعة على أربع (04) حصص كما يلي:',
                'للمدرسة العليا في العلوم البيولوجية بوهران.',
            ]
            ends=[]
            for marker in candidates:
                pos=text.find(marker,start)
                if pos!=-1: ends.append((pos+len(marker),marker))
            if ends:
                end=max(ends,key=lambda x:x[0])[0]
                return text[:start]+value+text[end:]
        return text
    if family == 'equipment':
        first, second = _split_ar(value)
        if 'تعلن المدرسة' in text and 'لاقتناء' in text:
            start = text.index('لاقتناء')
            return text[:start] + 'ل' + first
        if text.strip().startswith('( FABLAB)') or text.strip().startswith('(FABLAB)'):
            return second
        if 'لا يفتح إلا' in text and 'لاقتناء' in text:
            start = text.index('لاقتناء')
            end = text.rfind('حصتين') + len('حصتين')
            return text[:start] + 'ل' + value + text[end:]
        return text
    start_marker, end_marker = AR_OBJECT_MARKERS[family]
    if start_marker not in text:
        return text
    start = text.index(start_marker)
    end = text.find(end_marker, start)
    if end == -1:
        return text
    end += len(end_marker)
    prefix = 'ل' if family == 'works' and text[start:start+1] == 'ل' else ''
    replacement = value
    if family == 'works' and text[start:].startswith('لأشغال') and not value.startswith('ل'):
        replacement = 'ل' + value
    return text[:start] + replacement + text[end:]


def _replace_schedule(text, family, value):
    out = text
    if re.search(r'préparation des offres', out, re.I):
        out = re.sub(r'(?:Vingt[- ]et[- ]un|vingt[- ]et[- ]un)\s*(?:jours\s*)?\(21\)\s*jours?',
                     value['preparation_fr'], out)
    if 'تحضير العروض' in out:
        out = re.sub(r'واحد\s+وعشر(?:ون|ين)\s*(?:يو(?:ما|ماً)\s*)?\(21\)\s*يو(?:ما|ماً)', value['preparation_ar'], out)
    if re.search(r'dépôt des offres|date de dépôt', out, re.I):
        out = re.sub(r'(?<!\d)12\s*h(?:00)?(?!\d)', _display_time(value['deposit_time']), out, flags=re.I)
        out = re.sub(r'(?<!\d)12:00(?!\d)', value['deposit_time'], out)
    if 'إيداع العروض' in out and 'فتح الأظرفة' not in out:
        out = re.sub(r'الساعة\s+الثانية\s+عشرة\s*\(12:00\)', 'الساعة '+value['deposit_time'], out)
        out = re.sub(r'12\s*(?:سا|:00)', value['deposit_time'], out)
    if re.search(r'ouverture des plis|ouverture des offres', out, re.I):
        out = re.sub(r'(?<!\d)12\s*h\s*15(?:\s*minutes?|\s*mn)?(?!\d)', _display_time(value['opening_time']), out, flags=re.I)
        out = re.sub(r'(?<!\d)13\s*h?\s*00(?!\d)', _display_time(value['opening_time']), out, flags=re.I)
    if 'فتح الأظرفة' in out:
        out = re.sub(r'الساعة\s+الواحدة\s*\(13:00\)\s*بعد\s+الزوال', 'الساعة '+value['opening_time'], out)
        out = re.sub(r'(?<!\d)13:00(?!\d)', value['opening_time'], out)
        out = re.sub(r'(?<!\d)12\s*[Hh]\s*15(?!\d)', value['opening_time'], out)
        out = re.sub(r'12\s*سا\s*(?:و\s*)?15\s*دقيقة', value['opening_time'], out)
    return out

def _replace_validity(text, value):
    out = text
    if re.search(r'validité des offres|engagés par leurs offres', out, re.I):
        out = re.sub(r'Trois\s*\(03\)\s*mois', value['validity_fr'], out, flags=re.I)
    if 'ملزم' in out and 'عروض' in out:
        out = re.sub(r'ثلاثة\s*\(03\)\s*أشهر', value['validity_ar'], out)
    return out


def _replace_financing(text, family, value):
    if not re.search(r'Financement|Imputation budgétaire', text, re.I):
        return text
    if family == 'works' and text.strip().lower().startswith('imputation budgétaire'):
        rendered=value['financing_label']
        if value['budget_year']:
            rendered=f"{rendered} {value['budget_year']}".strip()
        return text.split(':',1)[0]+': '+rendered
    prefix = text.split(':', 1)[0] + ':' if ':' in text else ''
    rendered = value['financing_label']
    if family != 'works' or value['budget_year']:
        rendered = f"{rendered} {value['budget_year']}".strip()
    return prefix + (' ' if prefix else '') + rendered


def _replace_operation(text, family, value):
    stripped = text.strip()
    if family == 'equipment' and stripped.startswith('OPERATION') and ':' in text:
        return text.split(':',1)[0] + ': ' + value['operation_fr']
    if family == 'works' and stripped.startswith('Opération') and ':' in text:
        return text.split(':',1)[0] + ': ' + value['operation_fr']
    return text


def _replace_withdrawal(text, family, value):
    old_fr=DEFAULTS[family]['withdrawal_fr']; old_ar=DEFAULTS[family]['withdrawal_ar']
    if old_fr in text:
        return text.replace(old_fr,value['withdrawal_fr'])
    if old_ar in text:
        return text.replace(old_ar,value['withdrawal_ar'])
    return text

def consultation_edits(data, spans, doc):
    """Add source-pinned span edits only for canonical fields the user changed."""
    if 'consultation' not in data:
        return spans, {'status':'NOT_REQUESTED','fields':{}}
    family=data['family']; value=consultation_value(data,family); baseline=DEFAULTS[family]
    changed={k for k in FIELDS if k!='confirmed' and value[k] != baseline[k]}
    # Reagents source contains 13:00 in Arabic versus 12:15 in French.
    # Once the operator confirms the Information sheet, the selected canonical time wins.
    if value['confirmed'] and family=='reagents': changed.add('opening_time')
    counts={k:0 for k in changed}; result={k:list(v) for k,v in spans.items()}
    if not changed:
        return result, {'status':'UNCHANGED','fields':{}}
    for block in doc.source_index:
        for seg_index,nodes in enumerate(doc.editable_segments(block['id'])):
            before=''.join(n.characters for n in nodes); after=before
            if 'object_fr' in changed:
                updated=_replace_object(after,family,value['object_fr'])
                if updated!=after: counts['object_fr']+=1; after=updated
            if 'object_ar' in changed:
                updated=_replace_ar_object(after,family,value['object_ar'])
                if updated!=after: counts['object_ar']+=1; after=updated
            if 'operation_fr' in changed:
                updated=_replace_operation(after,family,value)
                if updated!=after: counts['operation_fr']+=1; after=updated
            if {'financing_label','budget_year'} & changed:
                updated=_replace_financing(after,family,value)
                if updated!=after:
                    for key in {'financing_label','budget_year'} & changed: counts[key]+=1
                    after=updated
            if {'preparation_days','preparation_fr','preparation_ar','deposit_time','opening_time'} & changed:
                updated=_replace_schedule(after,family,value)
                if updated!=after:
                    for key in {'preparation_days','preparation_fr','preparation_ar','deposit_time','opening_time'} & changed: counts[key]+=1
                    after=updated
            if {'withdrawal_fr','withdrawal_ar'} & changed:
                updated=_replace_withdrawal(after,family,value)
                if updated!=after:
                    if 'withdrawal_fr' in changed and DEFAULTS[family]['withdrawal_fr'] in after: counts['withdrawal_fr']+=1
                    if 'withdrawal_ar' in changed and DEFAULTS[family]['withdrawal_ar'] in after: counts['withdrawal_ar']+=1
                    after=updated
            if {'validity_months','validity_fr','validity_ar'} & changed:
                updated=_replace_validity(after,value)
                if updated!=after:
                    for key in {'validity_months','validity_fr','validity_ar'} & changed: counts[key]+=1
                    after=updated
            if after!=before:
                operations=result.setdefault(block['id'],[])
                existing=next((op for op in operations if op['segment']==seg_index),None)
                if existing:
                    if existing['before']!=before:
                        raise DocumentError('Conflit de liaison sur une variable documentaire.')
                    current=existing['after']
                    transformed=current
                    if 'object_fr' in changed: transformed=_replace_object(transformed,family,value['object_fr'])
                    if 'object_ar' in changed: transformed=_replace_ar_object(transformed,family,value['object_ar'])
                    if 'operation_fr' in changed: transformed=_replace_operation(transformed,family,value)
                    if {'financing_label','budget_year'} & changed: transformed=_replace_financing(transformed,family,value)
                    if {'preparation_days','preparation_fr','preparation_ar','deposit_time','opening_time'} & changed: transformed=_replace_schedule(transformed,family,value)
                    if {'withdrawal_fr','withdrawal_ar'} & changed: transformed=_replace_withdrawal(transformed,family,value)
                    if {'validity_months','validity_fr','validity_ar'} & changed: transformed=_replace_validity(transformed,value)
                    existing['after']=transformed
                else:
                    operations.append({'segment':seg_index,'before':before,'after':after})
    missing=[key for key,count in counts.items() if count==0]
    if missing:
        raise DocumentError('Aucun emplacement documentaire vérifié pour : '+', '.join(missing)+'.')
    return result, {'status':'GENERATED','fields':counts}



def consultation_managed_paragraphs(data, doc):
    """Return source paragraph ownership for fields controlled by Information.

    Detection uses the same conservative replacement functions as generation,
    but with harmless sentinel values. It never edits a document.
    """
    family=data['family']
    probe=initial_consultation(family)
    probe.update({
        'object_fr':'OBJET CDC SYNCHRONISE',
        'object_ar':'موضوع دفتر الشروط المتزامن',
        'operation_fr':'OPERATION CDC SYNCHRONISEE',
        'financing_label':'BUDGET CDC SYNCHRONISE','budget_year':2099,
        'preparation_days':30,'preparation_fr':'Trente (30) jours',
        'preparation_ar':'ثلاثون (30) يوما','deposit_time':'11:30',
        'opening_time':'11:45','validity_months':4,
        'validity_fr':'Quatre (04) mois','validity_ar':'أربعة (04) أشهر',
        'withdrawal_fr':'MODALITES RETRAIT CDC SYNCHRONISEES',
        'withdrawal_ar':'إجراءات سحب دفتر الشروط المتزامنة',
    })
    managed={}
    for block in doc.source_index:
        keys=set()
        for nodes in doc.editable_segments(block['id']):
            before=''.join(n.characters for n in nodes)
            if _replace_object(before,family,probe['object_fr'])!=before: keys.add('object_fr')
            if _replace_ar_object(before,family,probe['object_ar'])!=before: keys.add('object_ar')
            if _replace_operation(before,family,probe)!=before: keys.add('operation_fr')
            if _replace_financing(before,family,probe)!=before: keys.update(('financing_label','budget_year'))
            scheduled=_replace_schedule(before,family,probe)
            if scheduled!=before: keys.update(('preparation_days','preparation_fr','preparation_ar','deposit_time','opening_time'))
            withdrawn=_replace_withdrawal(before,family,probe)
            if withdrawn!=before: keys.update(('withdrawal_fr','withdrawal_ar'))
            valid=_replace_validity(before,probe)
            if valid!=before: keys.update(('validity_months','validity_fr','validity_ar'))
        if keys: managed[block['id']]=sorted(keys)
    return managed

def consultation_findings(data):
    if 'consultation' not in data:
        return [{'severity':'error','id':'CONSULTATION_REQUIRED',
                 'message':'Renseignez et validez la fiche Informations avant la génération institutionnelle.'}]
    value=consultation_value(data,data['family'])
    findings=[]
    if not value['confirmed']:
        findings.append({'severity':'error','id':'CONSULTATION_CONFIRMATION',
                         'message':'Relisez puis confirmez la fiche Informations. Les valeurs préremplies proviennent des modèles et ne valent pas validation du nouveau dossier.'})
    if value['deposit_time'] >= value['opening_time']:
        findings.append({'severity':'error','id':'CALENDAR_ORDER',
                         'message':'L’heure d’ouverture doit être postérieure à l’heure limite de dépôt.'})
    if data['family']=='reagents':
        account=lambda t:set(re.findall(r'(?<!\d)\d{8,24}(?!\d)',t))
        fr,ar=account(value['withdrawal_fr']),account(value['withdrawal_ar'])
        if not fr or not ar or not (fr & ar):
            findings.append({'severity':'error','id':'WITHDRAWAL_ACCOUNT_BILINGUAL',
                             'message':'Les modalités de retrait FR/AR ne portent pas le même numéro de compte. Corrigez la fiche Informations avant génération.'})
    return findings
