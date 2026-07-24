from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.views import (
    LoginView, LogoutView,
    PasswordResetView, PasswordResetDoneView,
    PasswordResetConfirmView, PasswordResetCompleteView,
)
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.generic import CreateView
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from .models import User
from .forms import RegistrationForm

_GUEST_TOKEN_SALT = 'guest-conversion'
_GUEST_TOKEN_TTL = 24 * 60 * 60  # 24 hours


# Brute-force lockout: after MAX_LOGIN_ATTEMPTS consecutive failures the
# account is locked for LOCKOUT_MINUTES. The User model has carried
# ``login_attempts`` / ``locked_until`` since the start — this wires them up.
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        from django.utils import timezone
        user = form.get_user()
        if user.locked_until and user.locked_until > timezone.now():
            remaining = int((user.locked_until - timezone.now()).total_seconds() // 60) + 1
            form.add_error(None, _(
                "Compte temporairement verrouillé suite à des tentatives "
                "échouées. Réessayez dans %(minutes)d minute(s)."
            ) % {'minutes': remaining})
            # super() on purpose: a correct-password attempt during the lock
            # window must not be counted as another failure.
            return super().form_invalid(form)
        # Successful login within an unlocked window → reset the counters.
        if user.login_attempts or user.locked_until:
            user.login_attempts = 0
            user.locked_until = None
            user.save(update_fields=['login_attempts', 'locked_until'])
        return super().form_valid(form)

    def form_invalid(self, form):
        from django.utils import timezone
        username = (self.request.POST.get('username') or '').strip()
        if username:
            # Count the failure for the targeted account (if it exists) and
            # lock after the threshold. Never leaks whether the account
            # exists: the response is the same generic form error either way.
            user = User.objects.filter(username__iexact=username).first()
            if user is not None:
                user.login_attempts = (user.login_attempts or 0) + 1
                fields = ['login_attempts']
                if user.login_attempts >= MAX_LOGIN_ATTEMPTS:
                    user.locked_until = timezone.now() + timezone.timedelta(
                        minutes=LOCKOUT_MINUTES)
                    user.login_attempts = 0
                    fields.append('locked_until')
                user.save(update_fields=fields)
        return super().form_invalid(form)


class CustomLogoutView(LogoutView):
    next_page = '/'


# ── Self-service password reset (Django-native: signed, expiring, one-time
#    token). Subclassed only to point at our styled templates + reset the
#    lockout counters on completion. Never reveals whether an email exists.
class ForgotPasswordView(PasswordResetView):
    template_name = 'accounts/password_reset_form.html'
    email_template_name = 'accounts/email/password_reset_email.txt'
    html_email_template_name = 'accounts/email/password_reset_email.html'
    subject_template_name = 'accounts/email/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')


class ForgotPasswordDoneView(PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class ForgotPasswordConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')

    def form_valid(self, form):
        # A completed reset clears any brute-force lockout on the account.
        user = form.user
        if user.login_attempts or user.locked_until:
            user.login_attempts = 0
            user.locked_until = None
            user.save(update_fields=['login_attempts', 'locked_until'])
        return super().form_valid(form)


class ForgotPasswordCompleteView(PasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'


class RegisterView(CreateView):
    model = User
    form_class = RegistrationForm
    template_name = 'accounts/register.html'
    success_url = '/dashboard/'

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


@login_required
def profile(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.phone = request.POST.get('phone', user.phone or '')
        user.organization = request.POST.get('organization', user.organization or '')
        user.laboratory = request.POST.get('laboratory', user.laboratory or '')
        user.supervisor = request.POST.get('supervisor', user.supervisor or '')

        # Language preference (Phase 3.1). Empty string means "no preference,
        # follow cookie / Accept-Language". Reject any value not in
        # LANGUAGE_PREFERENCE_CHOICES so a tampered POST cannot store garbage.
        pref = (request.POST.get('preferred_language') or '').strip()
        valid_prefs = {code for code, _ in User.LANGUAGE_PREFERENCE_CHOICES}
        if pref in valid_prefs:
            user.preferred_language = pref

        if 'avatar' in request.FILES:
            user.avatar = request.FILES['avatar']
        user.save()

        # Member technique update
        if user.role == 'MEMBER':
            try:
                member_profile = user.member_profile
                technique_ids = request.POST.getlist('techniques')
                member_profile.techniques.set(technique_ids)
            except Exception:
                pass

        messages.success(request, _("Profil mis à jour."))
        return redirect('accounts:profile')

    techniques = None
    if request.user.role == 'MEMBER':
        from accounts.models import Technique
        techniques = Technique.objects.filter(active=True)

    return render(request, 'accounts/profile.html', {
        'techniques': techniques,
        'language_choices': User.LANGUAGE_PREFERENCE_CHOICES,
    })


def convert_guest(request):
    """Stage 1 of guest conversion: request an email-verification link.

    The user enters their email. If guest requests are pending under that
    address, a one-time signed link is emailed. No account is created here.
    The response is identical whether or not the email matches any record so
    that this endpoint cannot be used to enumerate guests.
    """
    email = (request.GET.get('email', '') or '').strip()
    sent = False

    if request.method == 'POST':
        email = (request.POST.get('email', '') or '').strip().lower()
        if not email:
            messages.error(request, _("Email requis."))
            return render(request, 'accounts/convert_guest.html', {'email': email, 'sent': False})
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, _("Un compte avec cet email existe déjà."))
            return render(request, 'accounts/convert_guest.html', {'email': email, 'sent': False})

        from core.models import Request
        has_guest_requests = Request.objects.filter(
            guest_email__iexact=email, submitted_as_guest=True, requester__isnull=True,
        ).exists()

        if has_guest_requests:
            token = TimestampSigner(salt=_GUEST_TOKEN_SALT).sign(email)
            verify_url = request.build_absolute_uri(
                reverse('accounts:convert_guest_verify', args=[token])
            )
            try:
                html_body = render_to_string('accounts/email/guest_conversion_verify.html', {
                    'email': email,
                    'verify_url': verify_url,
                    'platform_name': 'PLAGENOR 4.0',
                }, request=request)
                send_mail(
                    subject=_("Vérification de votre adresse — PLAGENOR 4.0"),
                    message=_("Pour finaliser la création de votre compte, ouvrez ce lien : %(url)s") % {'url': verify_url},
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    html_message=html_body,
                    fail_silently=True,
                )
            except Exception:
                pass

        # Always show the same confirmation, even if no matching guest requests
        # existed — avoid leaking whether a given email is on file.
        sent = True

    return render(request, 'accounts/convert_guest.html', {'email': email, 'sent': sent})


def convert_guest_verify(request, token):
    """Stage 2 of guest conversion: the user clicks the link from their inbox.

    The token proves they own the email address. They set their password and
    a CLIENT account is created with every matching guest request linked.
    """
    signer = TimestampSigner(salt=_GUEST_TOKEN_SALT)
    try:
        email = signer.unsign(token, max_age=_GUEST_TOKEN_TTL).lower()
    except SignatureExpired:
        messages.error(request, _("Lien expiré. Veuillez recommencer."))
        return redirect('accounts:convert_guest')
    except BadSignature:
        messages.error(request, _("Lien invalide."))
        return redirect('accounts:convert_guest')

    # Defence-in-depth: an account may have been created between email and click.
    if User.objects.filter(email__iexact=email).exists():
        messages.info(request, _("Un compte avec cet email existe déjà — veuillez vous connecter."))
        return redirect('accounts:login')

    first_name = (request.POST.get('first_name', '') or '').strip()
    last_name = (request.POST.get('last_name', '') or '').strip()
    phone = (request.POST.get('phone', '') or '').strip()

    if request.method == 'POST':
        password = request.POST.get('password', '') or ''
        try:
            validate_password(password)
        except DjangoValidationError as e:
            messages.error(request, " ".join(e.messages))
            return render(request, 'accounts/convert_guest_verify.html', {
                'email': email, 'first_name': first_name, 'last_name': last_name, 'phone': phone,
            })

        from core.models import Request
        base_username = (email.split('@')[0] or 'user').strip()
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name, phone=phone, role='CLIENT',
        )

        guest_qs = Request.objects.filter(
            guest_email__iexact=email, submitted_as_guest=True, requester__isnull=True,
        )
        # Capture the count BEFORE the update — afterwards the predicate no
        # longer matches the rows and .count() would always be 0.
        linked = guest_qs.count()
        guest_qs.update(requester=user)

        login(request, user)
        messages.success(
            request,
            _("Compte créé ! %(count)d demande(s) liée(s) à votre compte.") % {'count': linked},
        )
        return redirect('dashboard:router')

    return render(request, 'accounts/convert_guest_verify.html', {
        'email': email, 'first_name': first_name, 'last_name': last_name, 'phone': phone,
    })


@login_required
def force_change_password(request):
    """Force logged-in users who must change password to do so immediately."""
    from django import forms as dj_forms

    class ForcePasswordForm(dj_forms.Form):
        new_password1 = dj_forms.CharField(
            label=_('Nouveau mot de passe'),
            widget=dj_forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
            min_length=8,
        )
        new_password2 = dj_forms.CharField(
            label=_('Confirmer le mot de passe'),
            widget=dj_forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        )

        def clean(self):
            cleaned = super().clean()
            p1 = cleaned.get('new_password1')
            p2 = cleaned.get('new_password2')
            if p1 and p2 and p1 != p2:
                raise dj_forms.ValidationError(_('Les deux mots de passe ne correspondent pas.'))
            return cleaned

    if not request.user.must_change_password:
        return redirect('accounts:profile')

    form = ForcePasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        new_password = form.cleaned_data['new_password1']
        try:
            validate_password(new_password, user=request.user)
        except DjangoValidationError as e:
            form.add_error('new_password1', e)
        else:
            request.user.set_password(new_password)
            request.user.must_change_password = False
            request.user.save(update_fields=['password', 'must_change_password'])
            # Re-authenticate so the session stays valid
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, request.user)
            messages.success(request, _('Votre mot de passe a été mis à jour avec succès.'))
            return redirect('dashboard:router')

    return render(request, 'accounts/force_change_password.html', {'form': form})


def check_email(request):
    """AJAX endpoint to check if email is already registered.
    
    Rate-limited: max 20 requests per minute per IP to prevent enumeration.
    """
    from django.http import JsonResponse
    from django.core.cache import cache
    import json
    import time

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # Simple IP-based rate limiting (20 req/min)
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
    ip = ip.split(',')[0].strip()
    rate_key = f'email_check_rate:{ip}'
    now = int(time.time())
    window_key = f'{rate_key}:{now // 60}'  # per-minute window
    count = cache.get(window_key, 0)
    if count >= 20:
        return JsonResponse({'error': 'Too many requests'}, status=429)
    cache.set(window_key, count + 1, timeout=70)

    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()

        if not email:
            return JsonResponse({'exists': False})

        exists = User.objects.filter(email__iexact=email).exists()
        return JsonResponse({'exists': exists})
    except Exception:
        return JsonResponse({'exists': False})
