from copy import deepcopy
from decimal import Decimal
import hashlib
import json

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from core.ibtikar.models import IbtikarAttachment, IbtikarRevision, IbtikarSubmission
from core.ibtikar.schema import active_data, schema_digest
from core.models import Request, RequestHistory


EDITABLE = {'DRAFT', 'SUBMITTED', 'VALIDATION_PEDAGOGIQUE'}


def serializable(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def snapshot(submission):
    return {'schema': submission.schema, 'schema_hash': submission.schema_hash,
            'applicant': submission.applicant, 'parameters': submission.parameters,
            'samples': submission.samples, 'staff': submission.staff,
            'estimate': submission.estimate, 'legacy_data': submission.legacy_data,
            'attachments': [{'id': str(x.pk), 'field': x.field_name, 'sha256': x.sha256,
                             'name': x.original_name} for x in submission.attachments.filter(active=True)],
            'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at else None}


def save_submission(*, service, schema, applicant, parameters, samples, files,
                    actor=None, req=None, revision=0, draft=False, legacy_data=None):
    from core.pricing import resolve_cost
    from core.services.ibtikar import submit_ibtikar_request
    from django.conf import settings
    created_files = []
    try:
        with transaction.atomic():
            current = None
            if req:
                req = Request.objects.select_for_update().get(pk=req.pk)
                if req.status not in EDITABLE:
                    raise ValidationError(_('Cette demande n’est plus modifiable à ce stade.'))
                current = IbtikarSubmission.objects.select_for_update().filter(request=req).first()
                if (current.revision if current else 0) != revision:
                    raise ValidationError(_('La demande a été modifiée ailleurs. Rechargez-la avant de sauvegarder.'))
            data = serializable({'applicant': applicant, 'parameters': parameters, 'samples': samples})
            estimate = resolve_cost(service, 'IBTIKAR', data['samples'],
                                    {**data['parameters'], '_ibtikar_schema': schema['version']}, ibtikar_schema=schema) if not draft else {
                'status': 'draft', 'total': None, 'source': 'draft', 'reasons': [], 'currency': 'DZD', 'breakdown': []}
            estimate = serializable(estimate)
            balance = Decimal(str(applicant.get('declared_balance') or 0))
            if not balance.is_finite() or balance < 0 or balance > Decimal(str(settings.IBTIKAR_BUDGET_CAP)):
                raise ValidationError(_('Le solde déclaré est hors des limites autorisées.'))
            if estimate.get('total') is not None and Decimal(str(estimate['total'])) > balance and not draft:
                raise ValidationError(_('Le coût calculé dépasse le solde IBTIKAR déclaré.'))
            projected_parameters = {**active_data(schema, 'parameters', data['parameters']), '_ibtikar_schema': schema['version']}
            projected_samples = [active_data(schema, 'samples', row, projected_parameters) for row in data['samples']]
            budget = estimate['total'] if estimate.get('total') is not None else 0
            if req is None:
                import uuid
                req = submit_ibtikar_request({
                    'service_id': str(service.pk), 'title': applicant.get('project_title') or service.name,
                    'budget_amount': budget, 'declared_ibtikar_balance': balance,
                    'service_params': projected_parameters, 'sample_table': projected_samples,
                    'requester_data': data['applicant'], 'pricing': estimate,
                    'status': 'DRAFT' if draft else 'SUBMITTED',
                    'submitted_as_guest': actor is None, 'guest_token': uuid.uuid4() if actor is None else None,
                    'guest_name': applicant.get('full_name', ''), 'guest_email': applicant.get('email', ''),
                    'guest_phone': applicant.get('phone', '')}, user=actor)
            else:
                old_status = req.status
                req.title = applicant.get('project_title') or req.title
                req.service_params = projected_parameters
                req.sample_table = projected_samples
                req.requester_data = data['applicant']
                req.pricing = estimate
                req.budget_amount = budget
                req.declared_ibtikar_balance = balance
                req.admin_validated_price = None
                req.status = 'DRAFT' if draft and old_status == 'DRAFT' else 'SUBMITTED'
                req.save(update_fields=['title', 'service_params', 'sample_table', 'requester_data', 'pricing',
                                        'budget_amount', 'declared_ibtikar_balance', 'admin_validated_price', 'status', 'updated_at'])
                if old_status == 'DRAFT' and not draft:
                    from core.services.ibtikar import _notify_submission
                    transaction.on_commit(lambda: _notify_submission(req), robust=True)
                RequestHistory.objects.create(request=req, from_status=old_status, to_status=req.status,
                                              actor=actor, notes='Formulaire IBTIKAR révisé ; validation à renouveler.')
            submission = current or IbtikarSubmission(request=req, schema=deepcopy(schema), schema_hash=schema_digest(schema))
            if current:
                submission.revision += 1
            submission.applicant = data['applicant']
            submission.parameters = data['parameters']
            submission.samples = data['samples']
            submission.estimate = estimate
            submission.staff = {key: value for key, value in (current.staff if current else {}).items() if key not in ('validated_price', 'price_justification', 'administrative_validation', 'head_visa', 'director_visa', 'technical_validation')}
            if legacy_data and not current:
                submission.legacy_data = deepcopy(legacy_data)
            submission.submitted_at = None if draft else timezone.now()
            submission.save()
            for name, upload in files.items():
                if not upload:
                    continue
                checksum = hashlib.sha256()
                for chunk in upload.chunks():
                    checksum.update(chunk)
                upload.seek(0)
                submission.attachments.filter(field_name=name, active=True).update(active=False)
                attachment = IbtikarAttachment(submission=submission, field_name=name,
                    original_name=getattr(upload, '_ibtikar_original_name', upload.name)[:255],
                    sha256=checksum.hexdigest(), created_by=actor)
                attachment.file.save(upload.name, upload, save=False)
                created_files.append((attachment.file.storage, attachment.file.name))
                attachment.save()
            IbtikarRevision.objects.create(submission=submission, revision=submission.revision,
                data=snapshot(submission), actor=actor, reason='Brouillon' if draft else 'Soumission validée par le demandeur')
            return submission
    except Exception:
        for storage, name in created_files:
            storage.delete(name)
        raise


@transaction.atomic
def save_staff(submission_id, values, actor, revision):
    request_id = IbtikarSubmission.objects.values_list('request_id', flat=True).get(pk=submission_id)
    req = Request.objects.select_for_update().get(pk=request_id)
    current = IbtikarSubmission.objects.select_for_update().get(pk=submission_id)
    if req.status in ('COMPLETED', 'CLOSED', 'ARCHIVED', 'REJECTED'):
        raise ValidationError(_('Un dossier clôturé ne peut plus être modifié.'))
    if current.revision != revision:
        raise ValidationError(_('Une autre modification a été enregistrée. Rechargez cette page.'))
    roles = {'SUPER_ADMIN', 'PLATFORM_ADMIN'}
    if actor.role not in roles and not (actor.role == 'MEMBER' and current.request.assigned_to_id
                                      and current.request.assigned_to.user_id == actor.pk):
        raise ValidationError(_('Modification réservée au personnel habilité.'))
    values = serializable(values)
    if actor.role not in roles:
        for key in ('validated_price', 'price_justification', 'administrative_validation', 'head_visa', 'director_visa'):
            if values.get(key) not in (None, '', current.staff.get(key)):
                raise ValidationError(_('Cette validation relève de l’administration.'))
            values[key] = current.staff.get(key)
    validated = values.get('validated_price')
    if actor.role in roles and validated is not None:
        if len((values.get('price_justification') or '').strip()) < 10:
            raise ValidationError(_('Justifiez la validation tarifaire (au moins 10 caractères).'))
        price = Decimal(str(validated))
        if not price.is_finite() or price < 0:
            raise ValidationError(_('Montant validé invalide.'))
        balance = Decimal(str(current.applicant.get('declared_balance') or 0))
        if price > balance:
            raise ValidationError(_('Le prix validé dépasse le solde déclaré ; demander une mise à jour au demandeur.'))
        current.estimate = {**current.estimate, 'status': 'validated', 'total': str(price),
                            'validated_by': actor.pk, 'validated_at': timezone.now().isoformat(),
                            'justification': values['price_justification']}
        req.admin_validated_price = price
        req.budget_amount = price
        req.pricing = current.estimate
        req.save(update_fields=['admin_validated_price', 'budget_amount', 'pricing', 'updated_at'])
    if actor.role in roles and validated is None and current.staff.get('validated_price') is not None:
        raise ValidationError(_('Un tarif validé ne peut pas être effacé sans une révision de la demande.'))
    current.staff = {**values, 'operator_id': actor.pk, 'operator_name': actor.get_full_name() or actor.username,
                     'updated_at': timezone.now().isoformat()}
    current.revision += 1
    current.save(update_fields=['staff', 'estimate', 'revision', 'updated_at'])
    IbtikarRevision.objects.create(submission=current, revision=current.revision,
                                  data=snapshot(current), actor=actor, reason='Réception / validation PLAGENOR')
    return current


@transaction.atomic
def record_code(req, code, actor=None):
    req = Request.objects.select_for_update().get(pk=req.pk)
    if req.channel != 'IBTIKAR' or (actor is None and not req.submitted_as_guest) or (actor is not None and req.requester_id != actor.pk):
        raise ValidationError(_('Demande invitée IBTIKAR requise.'))
    if not code or len(code) > 50:
        raise ValidationError(_('Référence IBTIKAR invalide.'))
    if req.status not in ('IBTIKAR_SUBMISSION_PENDING', 'IBTIKAR_CODE_SUBMITTED'):
        raise ValidationError(_('La référence ne peut pas être transmise à cette étape.'))
    old = req.status
    req.ibtikar_external_code = code
    req.status = 'IBTIKAR_CODE_SUBMITTED'
    req.save(update_fields=['ibtikar_external_code', 'status', 'updated_at'])
    RequestHistory.objects.create(request=req, from_status=old, to_status=req.status,
                                  actor=actor, notes='Référence IBTIKAR transmise par le demandeur.')
    from core.workflow import _post_commit_transition
    transaction.on_commit(lambda: _post_commit_transition(req, old, req.status, actor, 'Référence IBTIKAR vérifiée', False))
    return req


def record_guest_code(req, code):
    return record_code(req, code)
