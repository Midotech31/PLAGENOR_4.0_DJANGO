import os
import sys
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from core.models import Request

requests_data = []
for req in Request.objects.all():
    fields = {
        'id': str(req.id),
        'requester_id': str(req.requester_id) if req.requester_id else None,
        'service_id': str(req.service_id) if req.service_id else None,
        'assigned_to_id': str(req.assigned_to_id) if req.assigned_to_id else None,
        'title': req.title,
        'description': req.description,
        'channel': req.channel,
        'status': req.status,

        'quantity': req.quantity,
        'sample_count': req.sample_count,
        'declared_genoclab_balance': str(req.declared_genoclab_balance),
        'declared_ibtikar_balance': str(req.declared_ibtikar_balance),
        'quote_amount': str(req.quote_amount),
        'quote_detail': req.quote_detail,
        'admin_validated_price': str(req.admin_validated_price) if req.admin_validated_price else None,
        'appointment_date': req.appointment_date.isoformat() if req.appointment_date else None,
        'appointment_proposed_by_id': str(req.appointment_proposed_by_id) if req.appointment_proposed_by_id else None,
        'appointment_confirmed': req.appointment_confirmed,
        'appointment_confirmed_at': req.appointment_confirmed_at.isoformat() if req.appointment_confirmed_at else None,
        'alt_date_proposed': req.alt_date_proposed.isoformat() if req.alt_date_proposed else None,
        'alt_date_note': req.alt_date_note,
        'assignment_accepted': req.assignment_accepted,
        'assignment_accepted_at': req.assignment_accepted_at.isoformat() if req.assignment_accepted_at else None,
        'assignment_declined': req.assignment_declined,
        'assignment_decline_reason': req.assignment_decline_reason,
        'report_delivered': req.report_delivered,
        'report_delivered_at': req.report_delivered_at.isoformat() if req.report_delivered_at else None,
        'admin_revision_notes': req.admin_revision_notes,
        'service_rating': req.service_rating,
        'rating_comment': req.rating_comment,
        'rated_at': req.rated_at.isoformat() if req.rated_at else None,
        'receipt_confirmed': req.receipt_confirmed,
        'receipt_confirmed_at': req.receipt_confirmed_at.isoformat() if req.receipt_confirmed_at else None,
        'citation_acknowledged': req.citation_acknowledged,
        'submitted_as_guest': req.submitted_as_guest,
        'guest_token': str(req.guest_token) if req.guest_token else None,
        'guest_name': req.guest_name,
        'guest_email': req.guest_email,
        'guest_phone': req.guest_phone,
        'service_params': req.service_params,
        'pricing': req.pricing,
        'sample_table': req.sample_table,
        'requester_data': req.requester_data,
        'ibtikar_external_code': req.ibtikar_external_code,
        'rejection_reason': req.rejection_reason,
        'archived': req.archived,
        'archived_at': req.archived_at.isoformat() if req.archived_at else None,
        'created_at': req.created_at.isoformat() if req.created_at else None,
        'updated_at': req.updated_at.isoformat() if req.updated_at else None,
    }
    
    # Remove None values for fields that might not exist in the database
    fields = {k: v for k, v in fields.items() if v is not None}
    
    requests_data.append({
        'model': 'core.request',
        'pk': str(req.pk),
        'fields': fields
    })

with open('requests_export.json', 'w', encoding='utf-8') as f:
    json.dump(requests_data, f, ensure_ascii=False, indent=2)

print(f"Exported {len(requests_data)} requests to requests_export.json")
