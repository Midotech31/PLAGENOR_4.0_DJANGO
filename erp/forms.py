from django import forms
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import (AccessGrant, Article, ArticleConversion, Capability, Category,
                     Location, LocationType, Party, PriceObservation, Unit)
from .permissions import TEAM_ROLES, catalog_scope, storage_scope


class VersionedForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['expected_version'].initial = self.instance.version
        if 'code' in self.fields and not self.instance._state.adding:
            self.fields['code'].widget.attrs['readonly'] = True
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.HiddenInput, forms.CheckboxInput)):
                field.widget.attrs['class'] = 'form-control'
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()


class UnitForm(VersionedForm):
    class Meta:
        model = Unit
        fields = ['code', 'name', 'name_en', 'name_ar', 'dimension', 'factor', 'active']


class CategoryForm(VersionedForm):
    class Meta:
        model = Category
        fields = ['code', 'name', 'name_en', 'name_ar', 'parent', 'active']


class PartyForm(VersionedForm):
    class Meta:
        model = Party
        fields = ['code', 'name', 'name_en', 'name_ar', 'is_supplier', 'is_manufacturer',
                  'email', 'phone', 'country', 'address', 'notes', 'active']


class LocationTypeForm(VersionedForm):
    class Meta:
        model = LocationType
        fields = ['code', 'name', 'name_en', 'name_ar', 'can_store', 'cold_storage', 'active']


class ArticleForm(VersionedForm):
    class Meta:
        model = Article
        exclude = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = catalog_scope(Category.objects.filter(active=True), self.user,
                                                         Capability.EDIT_CATALOG, field='pk')
        self.fields['manufacturer'].queryset = Party.objects.filter(is_manufacturer=True, active=True)
        self.fields['preferred_supplier'].queryset = Party.objects.filter(is_supplier=True, active=True)
        self.fields['base_unit'].queryset = Unit.objects.filter(active=True)
        for name in ('purchase_unit', 'consumption_unit', 'concentration_unit'):
            self.fields[name].queryset = Unit.objects.filter(active=True)
        groups = [
            (_('Identification'), ['code', 'name', 'category', 'manufacturer', 'manufacturer_reference', 'catalog_reference', 'base_unit', 'criticality', 'active']),
            (_('Informations scientifiques'), ['name_en', 'name_ar', 'cas', 'concentration_value', 'concentration_unit', 'grade', 'format', 'specifications']),
            (_('Approvisionnement'), ['preferred_supplier', 'packaging', 'purchase_unit', 'consumption_unit', 'minimum_stock', 'safety_stock', 'reorder_point', 'target_stock', 'order_multiple', 'lead_time_days']),
            (_('Conservation'), ['shelf_life_days', 'after_open_days', 'temperature_min', 'temperature_max', 'light_sensitive', 'storage_instructions']),
        ]
        self.groups = [{'title': title, 'fields': [self[name] for name in names]} for title, names in groups]


class LocationForm(VersionedForm):
    class Meta:
        model = Location
        exclude = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = storage_scope(Location.objects.filter(active=True), self.user, Capability.EDIT_STORAGE)
        self.fields['parent'].queryset = Location.objects.filter(
            Q(pk__in=allowed.values('pk')) | Q(pk=self.instance.parent_id)).exclude(pk=self.instance.pk)
        self.fields['kind'].queryset = LocationType.objects.filter(active=True)


class GrantForm(VersionedForm):
    class Meta:
        model = AccessGrant
        fields = ['user', 'capability', 'location', 'category', 'active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = get_user_model().objects.filter(is_active=True, role__in=TEAM_ROLES)


class ConversionForm(VersionedForm):
    class Meta:
        model = ArticleConversion
        fields = ['unit', 'factor', 'justification', 'active']


class PriceForm(forms.ModelForm):
    class Meta:
        model = PriceObservation
        fields = ['supplier', 'unit', 'amount', 'currency', 'observed_on', 'source']
        widgets = {'observed_on': forms.DateInput(attrs={'type': 'date'})}
