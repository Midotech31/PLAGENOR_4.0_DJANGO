"""Canonical shared data projected across the complete cahier.

This module never owns document values. It exposes where canonical values from
Information, Lots/Articles and the approved ESSBO reference are reused.
"""
from __future__ import annotations


def canonical_summary(data):
    from .consultation import consultation_value
    from .lot_catalog import get_catalog
    from .institutional import policy
    consultation=consultation_value(data,data['family'])
    catalog=get_catalog(data)
    institutional=policy()['values'] if data.get('institutional_policy') else {}
    return {
        'reference':data['reference'],
        'object_fr':consultation['object_fr'],
        'object_ar':consultation['object_ar'],
        'operation_fr':consultation['operation_fr'],
        'financing':f"{consultation['financing_label']} {consultation['budget_year']}",
        'preparation':consultation['preparation_fr'],
        'deposit_time':consultation['deposit_time'],
        'opening_time':consultation['opening_time'],
        'validity':consultation['validity_fr'],
        'lots_count':len(catalog['lots']),
        'lots':[{'number':l['number'],'name':l['name'],'name_ar':l['name_ar']} for l in catalog['lots']],
        'postal_code':institutional.get('postal_code',''),
        'phone_fax':institutional.get('phone_fax',''),
    }


def common_ownership(data):
    from .catalog import document, reference_spans
    from .consultation import consultation_managed_paragraphs
    from .institutional import policy
    from .schedule_adapter import lot_label_projection
    doc=document(data['family'])
    result={}
    def add(pid,source,fields):
        entry=result.setdefault(pid,{'sources':[],'fields':[]})
        if source not in entry['sources']: entry['sources'].append(source)
        for field in fields:
            if field not in entry['fields']: entry['fields'].append(field)
    for pid,fields in consultation_managed_paragraphs(data,doc).items():
        add(pid,'Informations',fields)
    for binding in reference_spans(data['family']):
        add(binding['id'],'Informations',['reference'])
    if data.get('institutional_policy'):
        for binding in policy()['bindings'][data['family']]:
            add(binding['id'],'Référentiel ESSBO',binding['keys'])
    _,lot_owners=lot_label_projection(data)
    for pid,owner in lot_owners.items():
        add(pid,owner['source'],owner['fields'])
    return result


def projected_edits(data):
    from .catalog import effective_edits
    from .schedule_adapter import lot_label_projection
    result=dict(effective_edits(data))
    lots,_=lot_label_projection(data)
    result.update(lots)
    return result


def manual_conflicts(data):
    ownership=common_ownership(data)
    conflicts=[]
    for pid in sorted(set(data.get('paragraphs',{})) & set(ownership)):
        owner=ownership[pid]
        conflicts.append({
            'severity':'error','id':'COMMON_DATA_MANUAL_OVERRIDE','block':pid,
            'message':'Ce paragraphe dépend déjà de '+', '.join(owner['sources'])+
                      '. Supprimez sa modification manuelle : la valeur canonique sera réutilisée automatiquement.'})
    return conflicts


def owner_label(owner):
    return ' + '.join(owner.get('sources',[]))
