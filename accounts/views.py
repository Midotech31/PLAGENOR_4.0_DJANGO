from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import CreateView
from django.shortcuts import render, redirect
from django.contrib import messages
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
            except Exception:
                pass

        messages.success(request, "Profil mis à jour.")
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
            messages.error(request, "Email et mot de passe sont obligatoires.")
            return render(request, 'accounts/convert_guest.html', {'email': email})

        if User.objects.filter(email=email).exists():
            messages.error(request, "Un compte avec cet email existe déjà.")
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
        messages.success(request, f"Compte créé! {guest_requests.count()} demande(s) liée(s) à votre compte.")
        return redirect('dashboard:router')

    return render(request, 'accounts/convert_guest.html', {'email': email})
