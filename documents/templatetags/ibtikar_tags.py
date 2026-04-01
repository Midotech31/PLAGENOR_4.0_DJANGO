# documents/templatetags/ibtikar_tags.py
# Template tags for IBTIKAR form functionality

from django import template
from django.utils.translation import gettext_lazy as _

register = template.Library()


@register.inclusion_tag('documents/ibtikar_form_button.html')
def ibtikar_form_button(request_obj, user, show_status=False):
    """
    Render IBTIKAR form download button.
    
    Usage:
        {% load ibtikar_tags %}
        {% ibtikar_form_button req user %}
        
    Args:
        request_obj: Request model instance
        user: User model instance
        show_status: Whether to show template status info
    """
    from documents.pdf_generators import check_template_status
    
    # Check if user can access IBTIKAR form
    is_admin = getattr(user, 'is_admin', False) or getattr(user, 'role', '') in ['SUPER_ADMIN', 'PLATFORM_ADMIN']
    is_requester = user == request_obj.requester
    
    can_access = is_admin or is_requester
    
    # For requesters, form is only available after approval
    approved_states = [
        'IBTIKAR_SUBMISSION_PENDING', 'ASSIGNED', 'SAMPLE_RECEIVED',
        'ANALYSIS_STARTED', 'ANALYSIS_FINISHED', 'REPORT_UPLOADED',
        'ADMIN_REVIEW', 'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'COMPLETED', 'CLOSED'
    ]
    
    if is_requester and not is_admin:
        if request_obj.status not in approved_states and not request_obj.generated_ibtikar_form:
            can_access = False
    
    # Get template status
    form_status = check_template_status(request_obj) if request_obj.channel == 'IBTIKAR' else None
    
    return {
        'request_obj': request_obj,
        'user': user,
        'is_admin': is_admin,
        'can_access': can_access,
        'has_form': bool(request_obj.generated_ibtikar_form),
        'form_url': request_obj.generated_ibtikar_form.url if request_obj.generated_ibtikar_form else None,
        'form_status': form_status,
        'show_status': show_status,
        'lang': getattr(user, 'language', 'fr'),
    }


@register.inclusion_tag('documents/ibtikar_form_status_badge.html')
def ibtikar_form_status_badge(request_obj):
    """
    Render IBTIKAR form status badge.
    
    Usage:
        {% load ibtikar_tags %}
        {% ibtikar_form_status_badge req %}
    """
    from documents.pdf_generators import check_template_status
    
    form_status = check_template_status(request_obj) if request_obj.channel == 'IBTIKAR' else None
    
    return {
        'form_status': form_status,
        'has_form': bool(request_obj.generated_ibtikar_form),
    }
