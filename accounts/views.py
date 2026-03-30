from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import CreateView
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, OperationalError
from .models import User
from .forms import RegistrationForm


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    next_page = '/'


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
        if 'avatar' in request.FILES:
            user.avatar = request.FILES['avatar']
        user.save()

        # Member technique update
        if user.role == 'MEMBER':
            try:
                member_profile = user.member_profile
                technique_ids = request.POST.getlist('techniques')
                member_profile.techniques.set(technique_ids)
            except (AttributeError, ObjectDoesNotExist):
                # User doesn't have a member profile
                pass

        messages.success(request, _("Profil mis à jour."))
        return redirect('accounts:profile')

    techniques = None
    if request.user.role == 'MEMBER':
        from accounts.models import Technique
        techniques = Technique.objects.filter(active=True)

    return render(request, 'accounts/profile.html', {
        'techniques': techniques,
    })


def convert_guest(request):
    """Convert a guest into a registered CLIENT account."""
    email = request.GET.get('email', '')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '')
        phone = request.POST.get('phone', '').strip()

        if not email or not password:
            messages.error(request, _("Email et mot de passe sont obligatoires."))
            return render(request, 'accounts/convert_guest.html', {'email': email})

        if User.objects.filter(email=email).exists():
            messages.error(request, _("Un compte avec cet email existe déjà."))
            return render(request, 'accounts/convert_guest.html', {'email': email})

        username = email.split('@')[0]
        # Ensure unique username
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role='CLIENT',
        )

        # Link guest requests to the new account
        from core.models import Request
        guest_requests = Request.objects.filter(guest_email__iexact=email, submitted_as_guest=True, requester__isnull=True)
        guest_requests.update(requester=user)

        login(request, user)
        messages.success(request, _("Compte créé! %(count)d demande(s) liée(s) à votre compte.") % {'count': guest_requests.count()})
        return redirect('dashboard:router')

    return render(request, 'accounts/convert_guest.html', {'email': email})


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
        request.user.set_password(form.cleaned_data['new_password1'])
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
    except (DatabaseError, OperationalError):
        # Database error - return False to be safe
        return JsonResponse({'exists': False})
