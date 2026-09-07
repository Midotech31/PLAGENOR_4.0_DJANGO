from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.http import HttpResponseForbidden
from django.utils import timezone

from core.audit import log_action
from core.models import FinancialSettings, FinancialAudit, Request, Service, PlatformContent
from dashboard.views.admin_ops import admin_required


class PolicyForm(forms.ModelForm):
    class Meta:
        model = FinancialSettings
        fields = ['show_estimates', 'invoice_payment_method', 'invoice_payment_days']


class IssuerForm(forms.Form):
    issuer_name = forms.CharField(label=_("Raison sociale / établissement"), max_length=250)
    issuer_address1 = forms.CharField(label=_("Adresse"), max_length=250)
    issuer_address2 = forms.CharField(label=_("Complément d’adresse"), required=False, max_length=250)
    issuer_address3 = forms.CharField(label=_("Code postal et ville"), max_length=250)
    issuer_nif = forms.CharField(label=_("Identification fiscale"), required=False, max_length=250)
    issuer_treasury = forms.CharField(label=_("Compte bancaire / Trésor"), required=False, max_length=250)
    issuer_ccp = forms.CharField(label=_("Compte CCP"), required=False, max_length=250)
    issuer_phone = forms.CharField(label=_("Téléphone"), required=False, max_length=250)
    footer_office = forms.CharField(label=_("Adresse en pied de page"), required=False, max_length=500)
    footer_contact = forms.CharField(label=_("Contact en pied de page"), required=False, max_length=500)


@admin_required
def index(request):
    policy = FinancialSettings.objects.filter(pk=1).first() or FinancialSettings()
    action = request.POST.get('action', 'policy')
    form = PolicyForm(request.POST if request.method == 'POST' and action == 'policy' else None, instance=policy)
    from documents.genoclab_layout import CMS_DEFAULTS, cms_get
    issuer_forms = []
    for channel, label in [('genoclab', 'GenoClab'), ('ohb', 'OHB — ESSBO')]:
        defaults = {key: (CMS_DEFAULTS.get('genoclab_' + key, '') if channel == 'ohb' else cms_get('genoclab_' + key)) for key in IssuerForm.base_fields}
        defaults.update({row.key[len(channel) + 1:]: row.value for row in PlatformContent.objects.filter(key__startswith=channel+'_', lang='fr')})
        issuer_form = IssuerForm(request.POST if request.method == 'POST' and action == channel else None, prefix=channel, initial=defaults)
        if channel == 'ohb':
            issuer_form.fields['issuer_name'].disabled = True
            issuer_form.initial['issuer_name'] = 'École Supérieure en Sciences Biologiques d’Oran'
        if issuer_form.is_bound and issuer_form.is_valid():
            with transaction.atomic():
                for key, value in issuer_form.cleaned_data.items():
                    PlatformContent.objects.update_or_create(key=channel+'_'+key, lang='fr', defaults={'value':value,'updated_by':request.user})
                log_action('INVOICE_ISSUER_SETTINGS', 'ISSUER', channel, request.user, details={'before': defaults, 'after': issuer_form.cleaned_data})
            messages.success(request, _('Paramètres enregistrés.'))
            return redirect('dashboard:financial_settings')
        issuer_forms.append({'channel': channel, 'label': label, 'form': issuer_form})
    if request.method == 'POST' and action == 'policy' and form.is_valid():
        with transaction.atomic():
            current = form.save(commit=False)
            current.updated_by = request.user
            current.save()
            log_action('ESTIMATE_POLICY', 'FINANCIAL_SETTINGS', '1', request.user,
                       details={'show_estimates': current.show_estimates})
        messages.success(request, _('Paramètres enregistrés.'))
        return redirect('dashboard:financial_settings')
    return render(request, 'dashboard/financial_settings.html', {
        'form': form, 'issuer_forms': issuer_forms, 'services': Service.objects.order_by('code'),
        'audit_entries': FinancialAudit.objects.select_related('actor')[:50],
    })


@admin_required
@require_POST
@transaction.atomic
def request_visibility(request, pk):
    req = get_object_or_404(Request.objects.select_for_update(), pk=pk)
    req.estimate_hidden = request.POST.get('estimate_hidden') == 'on'
    req.save(update_fields=['estimate_hidden'])
    log_action('ESTIMATE_REQUEST', 'REQUEST', str(pk), request.user,
               details={'hidden': req.estimate_hidden})
    return redirect('dashboard:admin_request_detail', pk=pk)


@admin_required
@require_POST
@transaction.atomic
def assign_billing_channel(request, pk):
    if request.user.role != 'PLATFORM_ADMIN':
        return HttpResponseForbidden()
    req = get_object_or_404(Request.objects.select_for_update(), pk=pk, channel='GENOCLAB')
    channel = request.POST.get('billing_channel')
    if channel not in dict(Request.BILLING_CHANNEL_CHOICES):
        return HttpResponseForbidden()
    if req.quote_issued_at or req.invoice_set.exists() or req.status not in ('REQUEST_CREATED', 'QUOTE_DRAFT'):
        messages.error(request, _('Le circuit est verrouillé après émission du devis.'))
        return redirect('dashboard:admin_request_detail', pk=pk)
    previous = req.billing_channel
    req.billing_channel = channel
    req.billing_assigned_by = request.user
    req.billing_assigned_at = timezone.now()
    # A draft prepared for the other entity must be recalculated/reviewed.
    if previous != channel:
        req.quote_detail = {}
        req.quote_amount = 0
        # The unused draft number is retired, never reused by the allocator.
        req.quote_number = ''
    req.save(update_fields=['billing_channel', 'billing_assigned_by', 'billing_assigned_at', 'quote_detail', 'quote_amount', 'quote_number'])
    log_action('INVOICE_CHANNEL_ASSIGNED', 'REQUEST', str(pk), request.user,
               details={'before': previous, 'after': channel})
    messages.success(request, _('Circuit de facturation enregistré.'))
    return redirect('dashboard:admin_request_detail', pk=pk)


class EmailTemplateForm(forms.Form):
    subject = forms.CharField(label=_("Objet"), max_length=180)
    body = forms.CharField(label=_("Contenu du message"), max_length=5000, widget=forms.Textarea)


@admin_required
def email_templates(request):
    from notifications.emails import EVENT_TEXT
    from django.utils.translation import override, gettext
    language = request.GET.get('language', 'fr')
    event = request.GET.get('event', 'submission_confirmation')
    if language not in ('fr', 'en', 'ar') or event not in EVENT_TEXT:
        return HttpResponseForbidden()
    subject_key, body_key = f'email_{event}_subject', f'email_{event}_body'
    existing = dict(PlatformContent.objects.filter(lang=language, key__in=[subject_key, body_key]).values_list('key', 'value'))
    with override(language):
        title, body = EVENT_TEXT[event]
        defaults = {'subject': existing.get(subject_key) or gettext(title), 'body': existing.get(body_key) or gettext(body)}
    form = EmailTemplateForm(request.POST if request.method == 'POST' else None, initial=defaults)
    if request.method == 'POST' and form.is_valid():
        if '\n' in form.cleaned_data['subject'] or '\r' in form.cleaned_data['subject']:
            form.add_error('subject', _('L’objet doit tenir sur une seule ligne.'))
        else:
            with transaction.atomic():
                for key, name in [(subject_key, 'subject'), (body_key, 'body')]:
                    PlatformContent.objects.update_or_create(key=key, lang=language, defaults={'value': form.cleaned_data[name], 'updated_by': request.user})
                FinancialAudit.objects.create(action='NOTIFICATION_TEMPLATE_UPDATED', entity_type='EMAIL_TEMPLATE', entity_id=event, actor=request.user, details={'language': language, 'before': defaults, 'after': form.cleaned_data})
            messages.success(request, _('Paramètres enregistrés.'))
    return render(request, 'dashboard/email_templates.html', {'form': form, 'event': event, 'language': language, 'events': [(key, gettext(value[0])) for key, value in EVENT_TEXT.items()]})
