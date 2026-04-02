"""API endpoints for service form fields and dynamic form rendering."""
import json
import logging
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)


def _get_service_params(service, channel='BOTH'):
    """Get parameter fields from DB (ServiceFormField), filtered by channel."""
    from core.models import ServiceFormField
    return list(
        service.form_fields.filter(
            field_category='parameter'
        ).filter(
            models.Q(channel='BOTH') | models.Q(channel=channel)
        ).order_by('order', 'sort_order', 'pk')
    )


def _get_sample_columns(service, channel='BOTH'):
    """Get sample table column fields from DB (ServiceFormField), filtered by channel."""
    from core.models import ServiceFormField
    return list(
        service.form_fields.filter(
            field_category='sample_table'
        ).filter(
            models.Q(channel='BOTH') | models.Q(channel=channel)
        ).order_by('order', 'sort_order', 'pk')
    )


def _get_additional_info(service, channel='BOTH'):
    """Get additional_info fields from DB, filtered by channel."""
    from core.models import ServiceFormField
    return list(
        service.form_fields.filter(
            field_category='additional_info'
        ).filter(
            models.Q(channel='BOTH') | models.Q(channel=channel)
        ).order_by('order', 'sort_order', 'pk')
    )


def _serialize_field_for_template(field):
    """Serialize a ServiceFormField to dict for template rendering."""
    choices = field.get_choices() or []
    
    # Include pricing modifier info if available
    pricing_info = None
    if getattr(field, 'affects_pricing', False) and field.price_modifier_type:
        pricing_info = {
            'affects_pricing': True,
            'modifier_type': field.price_modifier_type,
            'modifier_value': float(field.price_modifier_value) if field.price_modifier_value else None,
            'condition_note_fr': field.condition_note_fr or '',
            'condition_note_en': field.condition_note_en or '',
        }
    
    return {
        'name': field.name,
        'type': field.field_type,
        'label': field.label_fr or field.label or field.name,
        'label_fr': field.label_fr,
        'label_en': field.label_en,
        'options': choices,
        'required': field.is_required or field.required,
        'help_text': field.help_text_fr or '',
        'channel': getattr(field, 'channel', 'BOTH') or 'BOTH',
        'pricing_info': pricing_info,
    }


def _serialize_sample_column(col):
    """Serialize a sample table column to dict for template rendering."""
    choices = col.get_choices() or []
    
    # Include pricing modifier info if available
    pricing_info = None
    if getattr(col, 'affects_pricing', False) and col.price_modifier_type:
        pricing_info = {
            'affects_pricing': True,
            'modifier_type': col.price_modifier_type,
            'modifier_value': float(col.price_modifier_value) if col.price_modifier_value else None,
            'condition_note_fr': col.condition_note_fr or '',
            'condition_note_en': col.condition_note_en or '',
        }
    
    return {
        'name': col.name,
        'label': col.label_fr or col.label or col.name,
        'type': col.field_type,
        'options': choices,
        'required': col.is_required or col.required,
        'channel': getattr(col, 'channel', 'BOTH') or 'BOTH',
        'pricing_info': pricing_info,
    }


def _get_pricing(service):
    """Get pricing from YAML (used for cost estimation in the form)."""
    try:
        from core.registry import get_service_def
        definition = get_service_def(service.code)
        return definition.get('pricing', {}) if definition else {}
    except Exception:
        return {}


def service_form_fragment(request, service_code):
    """Return rendered HTML for a service's DB-driven form fields (parameters + sample table).
    
    Query params:
        channel: 'IBTIKAR' or 'GENOCLAB' (default: 'IBTIKAR')
    """
    try:
        from core.models import Service
        svc = Service.objects.filter(code=service_code).first()
        if not svc:
            return HttpResponse('<p class="text-muted">Service non trouve.</p>')
    except Exception as e:
        logger.warning(f"Failed to load service {service_code}: {e}")
        return HttpResponse('<p class="text-muted">Service non trouve.</p>')

    channel = request.GET.get('channel', 'IBTIKAR')
    
    param_fields = _get_service_params(svc, channel)
    parameters = [_serialize_field_for_template(f) for f in param_fields]

    sample_col_fields = _get_sample_columns(svc, channel)
    sample_columns = [_serialize_sample_column(c) for c in sample_col_fields]

    sample_table = {
        'enabled': bool(sample_columns),
        'columns': sample_columns,
        'column_names': [col['name'] for col in sample_columns],
    }

    additional_fields = _get_additional_info(svc, channel)
    db_fields = [_serialize_field_for_template(f) for f in additional_fields]

    pricing = _get_pricing(svc)
    pricing_json = json.dumps(pricing) if pricing else '{}'

    html = render_to_string('includes/service_form_fields.html', {
        'parameters': parameters,
        'sample_table': sample_table,
        'pricing': pricing,
        'pricing_json': pricing_json,
        'service_code': service_code,
        'db_fields': db_fields,
    })
    return HttpResponse(html)


@login_required
def service_form_fields_api(request, service_id):
    """
    API endpoint to get ServiceFormField entries for a service.
    Returns JSON list of fields for dynamic form rendering.
    
    Query params:
        category: 'parameter', 'sample_table', or 'additional_info' (default)
        lang: 'fr' (default) or 'en' for label language
    """
    try:
        from core.models import Service, ServiceFormField
        
        try:
            service = Service.objects.get(pk=service_id)
        except Service.DoesNotExist:
            return JsonResponse({'error': 'Service not found'}, status=404)
        
        category = request.GET.get('category', 'additional_info')
        lang = getattr(request.user, 'language', 'fr') or 'fr'
        
        fields = ServiceFormField.objects.filter(
            service=service,
            field_category=category
        ).order_by('order')
        
        field_list = []
        for field in fields:
            field_data = {
                'id': field.id,
                'name': field.name,
                'field_type': field.field_type,
                'choices': field.get_choices_list(),
                'is_required': field.is_required or field.required,
                'order': field.order,
            }
            if lang == 'en':
                field_data['label'] = field.label_en or field.label_fr or field.name
            else:
                field_data['label'] = field.label_fr or field.name
            field_list.append(field_data)
        
        return JsonResponse({
            'service_id': service.id,
            'service_code': service.code,
            'category': category,
            'fields': field_list,
            'source': 'db',
        })
        
    except Exception as e:
        logger.error(f"Error fetching service form fields: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required  
def service_sample_table_columns(request, service_id):
    """
    API endpoint to get sample table column definitions for a service.
    Returns JSON list of sample_table fields.
    """
    return service_form_fields_api(request, service_id)


@login_required
def all_service_form_fields(request, service_id):
    """
    API endpoint to get ALL form fields for a service (parameter, sample_table, additional_info).
    DB-driven only — no YAML fallback.
    """
    try:
        from core.models import Service, ServiceFormField
        
        try:
            service = Service.objects.get(pk=service_id)
        except Service.DoesNotExist:
            return JsonResponse({'error': 'Service not found'}, status=404)
        
        lang = getattr(request.user, 'language', 'fr') or 'fr'
        
        sample_fields = list(ServiceFormField.objects.filter(
            service=service,
            field_category='sample_table'
        ).order_by('order'))
        
        param_fields = list(ServiceFormField.objects.filter(
            service=service,
            field_category='parameter'
        ).order_by('order'))
        
        additional_fields = list(ServiceFormField.objects.filter(
            service=service,
            field_category='additional_info'
        ).order_by('order'))
        
        def serialize_field(field):
            field_data = {
                'id': field.id,
                'name': field.name,
                'field_type': field.field_type,
                'choices': field.get_choices_list(),
                'is_required': field.is_required or field.required,
                'order': field.order,
                'field_category': field.field_category,
                'channel': getattr(field, 'channel', 'BOTH') or 'BOTH',
                # Pricing modifier fields
                'affects_pricing': getattr(field, 'affects_pricing', False),
                'price_modifier_type': getattr(field, 'price_modifier_type', '') or '',
                'price_modifier_value': float(field.price_modifier_value) if field.price_modifier_value else None,
                'condition_note_fr': getattr(field, 'condition_note_fr', '') or '',
                'condition_note_en': getattr(field, 'condition_note_en', '') or '',
            }
            if lang == 'en':
                field_data['label'] = field.label_en or field.label_fr or field.name
            else:
                field_data['label'] = field.label_fr or field.name
            return field_data
        
        return JsonResponse({
            'service_id': service.id,
            'service_code': service.code,
            'service_name': service.name,
            'ibtikar_instructions': service.ibtikar_instructions if lang == 'fr' else service.ibtikar_instructions_en,
            'checklist_items': service.checklist_items or [],
            'sample_table_columns': [serialize_field(f) for f in sample_fields],
            'additional_info_fields': [serialize_field(f) for f in additional_fields],
            'parameter_fields': [serialize_field(f) for f in param_fields],
            'source': 'db',
        })
        
    except Exception as e:
        logger.error(f"Error fetching all service form fields: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def service_field_create(request, service_id):
    """Create a new ServiceFormField for a service. JSON body."""
    try:
        import json
        from core.models import Service, ServiceFormField

        try:
            service = Service.objects.get(pk=service_id)
        except Service.DoesNotExist:
            return JsonResponse({'error': 'Service not found'}, status=404)

        data = json.loads(request.body)

        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Field name is required'}, status=400)

        if ServiceFormField.objects.filter(service=service, name=name).exists():
            return JsonResponse({'error': f'Field "{name}" already exists for this service'}, status=400)

        max_order = ServiceFormField.objects.filter(
            service=service,
            field_category=data.get('field_category', 'parameter')
        ).aggregate(models.Max('order'))['order__max'] or 0

        field = ServiceFormField.objects.create(
            service=service,
            name=name,
            label=data.get('label', name),
            label_fr=data.get('label_fr', data.get('label', name)),
            label_en=data.get('label_en', ''),
            field_type=data.get('field_type', 'text'),
            field_category=data.get('field_category', 'parameter'),
            options=data.get('options', []) or [],
            choices_json=data.get('choices_json') or None,
            is_required=data.get('is_required', False),
            required=data.get('is_required', False),
            help_text_fr=data.get('help_text_fr', ''),
            help_text_en=data.get('help_text_en', ''),
            order=max_order + 1,
            channel=data.get('channel', 'BOTH'),
        )

        return JsonResponse({
            'id': str(field.id),
            'name': field.name,
            'label': field.label_fr or field.label,
            'field_type': field.field_type,
            'field_category': field.field_category,
            'channel': getattr(field, 'channel', 'BOTH') or 'BOTH',
            'options': field.options or [],
            'is_required': field.is_required,
            'order': field.order,
            'message': 'Field created successfully',
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error creating service field: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def service_field_update(request, field_id):
    """Update an existing ServiceFormField. JSON body."""
    try:
        import json
        from core.models import ServiceFormField

        try:
            field = ServiceFormField.objects.get(pk=field_id)
        except ServiceFormField.DoesNotExist:
            return JsonResponse({'error': 'Field not found'}, status=404)

        data = json.loads(request.body)

        if 'name' in data:
            name = data['name'].strip()
            if name and name != field.name:
                if ServiceFormField.objects.filter(service=field.service, name=name).exclude(pk=field_id).exists():
                    return JsonResponse({'error': f'Field "{name}" already exists'}, status=400)
                field.name = name

        if 'label_fr' in data:
            field.label_fr = data['label_fr']
        if 'label_en' in data:
            field.label_en = data['label_en']
        if 'label' in data:
            field.label = data['label']
        if 'field_type' in data:
            field.field_type = data['field_type']
        if 'field_category' in data:
            field.field_category = data['field_category']
        if 'options' in data:
            field.options = data['options'] or []
        if 'choices_json' in data:
            field.choices_json = data['choices_json']
        if 'is_required' in data:
            field.is_required = data['is_required']
            field.required = data['is_required']
        if 'help_text_fr' in data:
            field.help_text_fr = data['help_text_fr']
        if 'help_text_en' in data:
            field.help_text_en = data['help_text_en']
        if 'channel' in data:
            field.channel = data['channel']
        # Pricing modifier fields
        if 'affects_pricing' in data:
            field.affects_pricing = bool(data['affects_pricing'])
        if 'price_modifier_type' in data:
            field.price_modifier_type = data['price_modifier_type'] or ''
        if 'price_modifier_value' in data:
            from decimal import Decimal
            val = data['price_modifier_value']
            field.price_modifier_value = Decimal(str(val)) if val else None
        if 'condition_note_fr' in data:
            field.condition_note_fr = data['condition_note_fr'] or ''
        if 'condition_note_en' in data:
            field.condition_note_en = data['condition_note_en'] or ''

        field.save()

        return JsonResponse({
            'id': str(field.id),
            'name': field.name,
            'label': field.label_fr or field.label,
            'field_type': field.field_type,
            'field_category': field.field_category,
            'channel': getattr(field, 'channel', 'BOTH') or 'BOTH',
            'options': field.options or [],
            'is_required': field.is_required,
            'order': field.order,
            'affects_pricing': getattr(field, 'affects_pricing', False),
            'price_modifier_type': getattr(field, 'price_modifier_type', '') or '',
            'price_modifier_value': float(field.price_modifier_value) if field.price_modifier_value else None,
            'condition_note_fr': getattr(field, 'condition_note_fr', '') or '',
            'condition_note_en': getattr(field, 'condition_note_en', '') or '',
            'message': 'Field updated successfully',
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error updating service field: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def service_field_delete(request, field_id):
    """Delete a ServiceFormField."""
    try:
        from core.models import ServiceFormField

        try:
            field = ServiceFormField.objects.get(pk=field_id)
        except ServiceFormField.DoesNotExist:
            return JsonResponse({'error': 'Field not found'}, status=404)

        service_code = field.service.code
        field_name = field.name
        field.delete()

        return JsonResponse({
            'message': f'Field "{field_name}" deleted from {service_code}'
        })

    except Exception as e:
        logger.error(f"Error deleting service field: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def service_field_reorder(request, service_id):
    """Reorder ServiceFormField entries for a service. JSON body: {field_ids: [uuid, ...]}"""
    try:
        import json
        from core.models import Service, ServiceFormField

        try:
            service = Service.objects.get(pk=service_id)
        except Service.DoesNotExist:
            return JsonResponse({'error': 'Service not found'}, status=404)

        data = json.loads(request.body)
        field_ids = data.get('field_ids', [])

        for i, fid in enumerate(field_ids):
            ServiceFormField.objects.filter(pk=fid, service=service).update(order=i)

        return JsonResponse({'message': 'Fields reordered', 'order': field_ids})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error reordering service fields: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def service_field_preview(request, service_id):
    """Return a preview HTML of the service form with current DB fields."""
    try:
        from core.models import Service, ServiceFormField
        from django.template.loader import render_to_string

        try:
            service = Service.objects.get(pk=service_id)
        except Service.DoesNotExist:
            return JsonResponse({'error': 'Service not found'}, status=404)

        param_fields = _get_service_params(service)
        parameters = [_serialize_field_for_template(f) for f in param_fields]

        sample_col_fields = _get_sample_columns(service)
        sample_columns = [_serialize_sample_column(c) for c in sample_col_fields]

        sample_table = {
            'enabled': bool(sample_columns),
            'columns': sample_columns,
            'column_names': [col['name'] for col in sample_columns],
        }

        additional_fields = _get_additional_info(service)
        db_fields = [_serialize_field_for_template(f) for f in additional_fields]

        pricing = _get_pricing(service)
        pricing_json = json.dumps(pricing) if pricing else '{}'

        html = render_to_string('includes/service_form_fields.html', {
            'parameters': parameters,
            'sample_table': sample_table,
            'pricing': pricing,
            'pricing_json': pricing_json,
            'service_code': service.code,
            'db_fields': db_fields,
        })

        return JsonResponse({'html': html, 'service_code': service.code})

    except Exception as e:
        logger.error(f"Error generating form preview: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# PRICING CONFIG API (Superadmin)
# =============================================================================

@login_required
def pricing_configs_list(request, service_pk):
    """Return JSON list of pricing configs for a service."""
    from django.contrib.admin.views.decorators import staff_member_required
    from core.models import Service, ServicePricing
    
    try:
        service = Service.objects.get(pk=service_pk)
    except Service.DoesNotExist:
        return JsonResponse({'error': 'Service not found'}, status=404)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    configs = service.pricing_configs.all().order_by('priority', 'pk')
    data = []
    for cfg in configs:
        data.append({
            'id': str(cfg.pk),
            'name': cfg.name,
            'description': cfg.description,
            'pricing_type': cfg.pricing_type,
            'channel': cfg.channel,
            'amount': float(cfg.amount) if cfg.amount else 0,
            'unit': cfg.unit,
            'is_active': cfg.is_active,
            'priority': cfg.priority,
        })
    
    return JsonResponse({'configs': data, 'service_code': service.code})


@login_required
def pricing_config_create(request, service_pk):
    """Create a new pricing config for a service."""
    from core.models import Service, ServicePricing
    from decimal import Decimal
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        service = Service.objects.get(pk=service_pk)
    except Service.DoesNotExist:
        return JsonResponse({'error': 'Service not found'}, status=404)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    name = request.POST.get('name', '').strip()
    pricing_type = request.POST.get('pricing_type', 'BASE')
    channel = request.POST.get('channel', 'BOTH')
    amount = request.POST.get('amount', '0')
    unit = request.POST.get('unit', '')
    priority = request.POST.get('priority', '0')
    is_active = request.POST.get('is_active', 'true').lower() == 'true'
    
    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)
    
    try:
        amount = Decimal(amount)
        priority = int(priority)
    except (ValueError, InvalidOperation):
        return JsonResponse({'error': 'Invalid amount or priority'}, status=400)
    
    config = ServicePricing.objects.create(
        service=service,
        name=name,
        pricing_type=pricing_type,
        channel=channel,
        amount=amount,
        unit=unit,
        priority=priority,
        is_active=is_active,
        updated_by=request.user,
    )
    
    return JsonResponse({
        'success': True,
        'config': {
            'id': str(config.pk),
            'name': config.name,
            'pricing_type': config.pricing_type,
            'channel': config.channel,
            'amount': float(config.amount),
            'unit': config.unit,
            'is_active': config.is_active,
            'priority': config.priority,
        }
    })


@login_required
def pricing_config_update(request, config_pk):
    """Update a pricing config."""
    from core.models import ServicePricing
    from decimal import Decimal
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        config = ServicePricing.objects.get(pk=config_pk)
    except ServicePricing.DoesNotExist:
        return JsonResponse({'error': 'Config not found'}, status=404)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    name = request.POST.get('name', '').strip()
    pricing_type = request.POST.get('pricing_type', config.pricing_type)
    channel = request.POST.get('channel', config.channel)
    amount = request.POST.get('amount', str(config.amount))
    unit = request.POST.get('unit', config.unit)
    priority = request.POST.get('priority', str(config.priority))
    is_active = request.POST.get('is_active', str(config.is_active)).lower() == 'true'
    
    if name:
        config.name = name
    config.pricing_type = pricing_type
    config.channel = channel
    
    try:
        config.amount = Decimal(amount)
        config.priority = int(priority)
    except (ValueError, InvalidOperation):
        pass
    
    config.unit = unit
    config.is_active = is_active
    config.updated_by = request.user
    config.save()
    
    return JsonResponse({
        'success': True,
        'config': {
            'id': str(config.pk),
            'name': config.name,
            'pricing_type': config.pricing_type,
            'channel': config.channel,
            'amount': float(config.amount),
            'unit': config.unit,
            'is_active': config.is_active,
            'priority': config.priority,
        }
    })


@login_required
def pricing_config_delete(request, config_pk):
    """Delete a pricing config."""
    from core.models import ServicePricing
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        config = ServicePricing.objects.get(pk=config_pk)
    except ServicePricing.DoesNotExist:
        return JsonResponse({'error': 'Config not found'}, status=404)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    service_code = config.service.code
    config.delete()
    
    return JsonResponse({'success': True, 'service_code': service_code})
