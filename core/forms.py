"""The catalogue requires explicit translations, without language fallbacks."""
from django import forms
from .models import Service, ServiceFormField

SERVICE_TEXT_FIELDS = tuple(f'{field}_{lang}' for lang in ('fr', 'ar', 'en')
                            for field in ('name', 'description'))


class ServiceAdminForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in SERVICE_TEXT_FIELDS:
            self.fields[name].required = True
            self.fields[name].strip = True


class ServiceTextForm(ServiceAdminForm):
    class Meta(ServiceAdminForm.Meta):
        fields = SERVICE_TEXT_FIELDS


class ServiceCreateForm(ServiceAdminForm):
    class Meta(ServiceAdminForm.Meta):
        fields = ('code', *SERVICE_TEXT_FIELDS, 'channel_availability',
                  'ibtikar_price', 'genoclab_price', 'turnaround_days', 'image')


class ServiceFieldAdminForm(forms.ModelForm):
    class Meta:
        model = ServiceFormField
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for lang in ('fr', 'ar', 'en'):
            self.fields[f'label_{lang}'].required = True
