"""Translation options for the core catalog models.

Registered fields gain `<field>_fr`, `<field>_en`, `<field>_ar` companions
managed by django-modeltranslation. Reads of the original attribute return
the active-locale value (with fall-back per MODELTRANSLATION_FALLBACK_LANGUAGES);
writes populate both the per-language column and the original column
(MODELTRANSLATION_AUTO_POPULATE='default').

NOT registered: PlatformContent. That model is a key/value CMS — adding
three columns to every row is the wrong shape. It receives a `(key, lang)`
composite-key migration in Phase 3.5 instead.
"""
from modeltranslation.translator import register, TranslationOptions

from accounts.models import Technique
from core.models import Service, ServicePricing, ServiceFormField


@register(Service)
class ServiceTR(TranslationOptions):
    fields = ('name', 'description')


@register(ServicePricing)
class ServicePricingTR(TranslationOptions):
    fields = ('name', 'description')


@register(ServiceFormField)
class ServiceFormFieldTR(TranslationOptions):
    fields = ('label',)


@register(Technique)
class TechniqueTR(TranslationOptions):
    fields = ('name', 'category')
