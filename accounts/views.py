import logging
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import CreateView
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, OperationalError
from django.db.models import Count, Q
from .models import User
from .forms import (
    IbtikarRegistrationForm,
    GenoclabRegistrationForm,
    ProfileUpdateForm,
)

logger = logging.getLogger('plagenor')


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    next_page = '/'


class RegisterView(CreateView):
    model = User
    template_name = 'accounts/register.html'
    success_url = '/dashboard/'

    def get_form_class(self):
        channel = self.request.GET.get('channel') or self.request.POST.get('channel')
        if channel == 'IBTIKAR':
            return IbtikarRegistrationForm
        elif channel == 'GENOCLAB':
            return GenoclabRegistrationForm
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        channel = self.request.GET.get('channel') or self.request.POST.get('channel')
        context['channel'] = channel
        context['show_channel_selector'] = not channel
        return context

    def get(self, request, *args, **kwargs):
        channel = request.GET.get('channel')
        if not channel:
            return render(request, 'accounts/register.html', {
                'show_channel_selector': True,
                'channel': None,
            })
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        channel = self.request.GET.get('channel') or self.request.POST.get('channel')

        if channel == 'IBTIKAR':
            first_name, last_name = form.get_first_name_last_name()
            user = User.objects.create_user(
                username=form.cleaned_data['email'].split('@')[0],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                first_name=first_name,
                last_name=last_name,
                phone=form.cleaned_data['phone'],
                organization=form.cleaned_data['institution'],
                laboratory=form.cleaned_data.get('laboratory', ''),
                position=form.cleaned_data['position'],
                role='REQUESTER',
            )
        elif channel == 'GENOCLAB':
            first_name, last_name = form.get_first_name_last_name()
            user = User.objects.create_user(
                username=form.cleaned_data['email'].split('@')[0],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                first_name=first_name,
                last_name=last_name,
                phone=form.cleaned_data['phone'],
                organization=form.cleaned_data['organization'],
                position=form.cleaned_data['sector'],
                role='CLIENT',
            )
        else:
            messages.error(self.request, _('Veuillez sélectionner un canal d\'inscription valide.'))
            return redirect('accounts:register')

        login(self.request, user)
        return redirect(self.success_url)


@login_required
def profile(request):
    user = request.user

    # Handle profile update
    if request.method == 'POST':
        action = request.POST.get('action', 'profile')

        if action == 'profile':
            form = ProfileUpdateForm(request.POST, instance=user)
            if form.is_valid():
                form.save()

                # Member technique update
                if user.role == 'MEMBER':
                    try:
                        member_profile = user.member_profile
                        technique_ids = request.POST.getlist('techniques')
                        member_profile.techniques.set(technique_ids)
                    except (AttributeError, ObjectDoesNotExist):
                        pass
                    except Exception as e:
                        logger.warning(f"Failed to update techniques for user {user.pk}: {e}")

                messages.success(request, _("Profil mis à jour avec succès."))
            else:
                for error in form.errors.values():
                    messages.error(request, error.as_text())

        elif action == 'password':
            form = PasswordChangeForm(user, request.POST)
            if form.is_valid():
                form.save()
                update_session_auth_hash(request, user)
                messages.success(request, _("Mot de passe modifié avec succès."))
            else:
                for error in form.errors.values():
                    messages.error(request, error.as_text())

        return redirect('accounts:profile')

    # Prepare data for profile display
    profile_form = ProfileUpdateForm(instance=user)
    techniques = None
    if user.role == 'MEMBER':
        from accounts.models import Technique
        techniques = Technique.objects.filter(active=True)

    # Activity summary
    activity_summary = _get_user_activity_summary(user)

    # Password change form
    password_form = PasswordChangeForm(user)

    # Language options
    language_choices = [
        ('fr', _('Français')),
        ('en', _('English')),
    ]

    return render(request, 'accounts/profile.html', {
        'profile_form': profile_form,
        'techniques': techniques,
        'activity_summary': activity_summary,
        'password_form': password_form,
        'language_choices': language_choices,
    })


def _get_user_activity_summary(user):
    """Get activity summary for the user based on their role."""
    from core.models import Request
    from notifications.models import Notification
    
    summary = {
        'total_requests': 0,
        'completed_requests': 0,
        'pending_requests': 0,
        'rejected_requests': 0,
        'total_downloads': 0,
        'ratings_given': 0,
        'avg_rating': 0,
        'notifications_count': 0,
        'recent_activity': [],
    }
    
    # For requesters and clients
    if user.role in ['REQUESTER', 'CLIENT']:
        requests = Request.objects.filter(requester=user)
        summary['total_requests'] = requests.count()
        summary['completed_requests'] = requests.filter(status='COMPLETED').count()
        summary['pending_requests'] = requests.exclude(status__in=['COMPLETED', 'REJECTED']).count()
        summary['rejected_requests'] = requests.filter(status='REJECTED').count()
        summary['ratings_given'] = requests.filter(service_rating__isnull=False).count()
        
        # Calculate average rating given
        rated = requests.filter(service_rating__isnull=False)
        if rated.exists():
            summary['avg_rating'] = round(sum(rated.values_list('service_rating', flat=True)) / rated.count(), 1)
        
        # Count reports downloaded (requests with completed status)
        summary['total_downloads'] = requests.filter(status__in=['COMPLETED', 'SENT_TO_REQUESTER', 'SENT_TO_CLIENT']).count()
        
        # Recent activity
        summary['recent_activity'] = list(requests.order_by('-updated_at')[:5].values(
            'display_id', 'title', 'status', 'updated_at', 'service__name'
        ))
    
    # For analysts/members
    elif user.role == 'MEMBER':
        from accounts.models import MemberProfile
        try:
            profile = user.member_profile
            assigned = Request.objects.filter(assigned_to=profile)
            summary['total_requests'] = assigned.count()
            summary['completed_requests'] = assigned.filter(status__in=['COMPLETED', 'REPORT_UPLOADED', 'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'SENT_TO_CLIENT']).count()
            summary['pending_requests'] = assigned.exclude(status__in=['COMPLETED', 'REJECTED']).count()
            summary['rejected_requests'] = assigned.filter(status='REJECTED').count()
            summary['productivity_score'] = profile.productivity_score
            summary['total_points'] = profile.total_points
            summary['total_downloads'] = assigned.filter(report_file__isnull=False).count()
        except (AttributeError, ObjectDoesNotExist):
            pass
        
        # Recent activity
        summary['recent_activity'] = list(assigned.order_by('-updated_at')[:5].values(
            'display_id', 'title', 'status', 'updated_at', 'service__name'
        ))
    
    # For admins
    elif user.role in ['SUPER_ADMIN', 'PLATFORM_ADMIN']:
        total_requests = Request.objects.count()
        summary['total_requests'] = total_requests
        summary['completed_requests'] = Request.objects.filter(status='COMPLETED').count()
        summary['pending_requests'] = Request.objects.exclude(status__in=['COMPLETED', 'REJECTED']).count()
        summary['total_users'] = User.objects.count()
        summary['total_members'] = User.objects.filter(role='MEMBER').count()
    
    # Notifications count
    summary['notifications_count'] = Notification.objects.filter(user=user, read=False).count()
    
    return summary


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
    except (DatabaseError, OperationalError) as e:
        # Database error - return False to be safe
        logger.error(f"Database error checking email existence: {e}")
        return JsonResponse({'exists': False})
