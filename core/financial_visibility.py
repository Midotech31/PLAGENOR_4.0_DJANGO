"""Server-side disclosure policy for indicative estimates and issued quotes."""
from core.models import FinancialSettings


def estimates_visible(service=None, request_obj=None):
    policy = FinancialSettings.objects.filter(pk=1).values_list('show_estimates', flat=True).first()
    if policy is False or (request_obj and request_obj.estimate_hidden):
        return False
    service = service or (request_obj.service if request_obj else None)
    return not service or service.estimates_enabled


def quote_released(req):
    # Legacy documents have no issuance timestamp; preserve access only where
    # the state/history proves they were already communicated.
    return bool(req.quote_issued_at or req.status in {
        'QUOTE_SENT', 'QUOTE_VALIDATED_BY_CLIENT', 'ORDER_UPLOADED',
        'INVOICE_GENERATED', 'ASSIGNED', 'APPOINTMENT_PROPOSED',
        'APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED', 'ANALYSIS_STARTED',
        'ANALYSIS_FINISHED', 'PAYMENT_PENDING', 'PAYMENT_PROOF_UPLOADED',
        'PAYMENT_CONFIRMED', 'REPORT_UPLOADED', 'REPORT_VALIDATED',
        'SENT_TO_CLIENT', 'COMPLETED', 'ARCHIVED',
    })


def request_financials_visible(req):
    if req.channel == 'IBTIKAR' and req.status in {
        'PLATFORM_NOTE_GENERATED', 'IBTIKAR_SUBMISSION_PENDING', 'IBTIKAR_CODE_SUBMITTED',
        'ASSIGNED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED',
        'ANALYSIS_STARTED', 'ANALYSIS_FINISHED', 'REPORT_UPLOADED', 'REPORT_VALIDATED',
        'SENT_TO_REQUESTER', 'COMPLETED', 'CLOSED',
    }:
        return True
    return quote_released(req) if req.channel == 'GENOCLAB' and req.quote_detail else estimates_visible(request_obj=req)
