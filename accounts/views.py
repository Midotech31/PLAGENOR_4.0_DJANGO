from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import CreateView
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
