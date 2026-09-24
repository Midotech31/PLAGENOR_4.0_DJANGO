from decimal import Decimal, InvalidOperation, localcontext

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from erp.models import Article, ArticleConversion, Category, LocationType, Party, PriceObservation, Unit, Capability
from erp.permissions import require
from .common import assign, audit, check_version, lock_tree, snapshot


@transaction.atomic
def save_reference(user, model, values, *, pk=None, expected=None):
    if model not in (Unit, Category, Party, LocationType):
        raise ValidationError(_('Type de référentiel non autorisé.'))
    require(user, Capability.EDIT_STORAGE if model is LocationType else Capability.EDIT_CATALOG)
    lock_tree('references')
    obj = model.objects.select_for_update().get(pk=pk) if pk else model()
    before = snapshot(obj) if pk else {}
    if pk:
        check_version(obj, expected)
    assign(obj, values)
    if model is Unit and pk and (before['dimension'] != obj.dimension or Decimal(before['factor']) != obj.factor):
        raise ValidationError(_('La dimension et le facteur d’une unité existante sont immuables.'))
    if model is Unit and obj.dimension in (Unit.Dimension.PACKAGE, Unit.Dimension.OTHER) and obj.factor != 1:
        raise ValidationError(_('Cette unité nécessite une conversion propre à chaque article.'))
    if model is Category:
        current = obj.parent
        seen = {obj.pk}
        while current is not None:
            if current.pk in seen:
                raise ValidationError(_('Une hiérarchie ne peut pas contenir de cycle.'))
            seen.add(current.pk)
            current = current.parent
    obj.full_clean()
    if pk:
        obj.version += 1
    obj.save()
    audit(user, obj, 'updated' if pk else 'created', before)
    return obj


@transaction.atomic
def save_article(user, values, *, pk=None, expected=None):
    obj = Article.objects.select_for_update().get(pk=pk) if pk else Article()
    before = snapshot(obj) if pk else {}
    if pk:
        require(user, Capability.EDIT_CATALOG, category=obj.category)
        check_version(obj, expected)
    assign(obj, values)
    require(user, Capability.EDIT_CATALOG, category=obj.category)
    obj.manufacturer_reference = obj.manufacturer_reference.strip()
    if not obj.base_unit.active or not obj.category.active:
        raise ValidationError(_('Sélectionnez une unité et une catégorie actives.'))
    if pk and str(obj.base_unit_id) != before['base_unit']:
        raise ValidationError(_('L’unité de gestion d’un article existant ne peut pas être remplacée.'))
    if obj.manufacturer and (not obj.manufacturer.active or not obj.manufacturer.is_manufacturer):
        raise ValidationError(_('Le fabricant sélectionné n’est pas actif ou n’a pas cette qualité.'))
    if obj.preferred_supplier and (not obj.preferred_supplier.active or not obj.preferred_supplier.is_supplier):
        raise ValidationError(_('Le fournisseur sélectionné n’est pas actif ou n’a pas cette qualité.'))
    obj.full_clean()
    if obj.active:
        for selected_unit in (obj.purchase_unit, obj.consumption_unit):
            if selected_unit is not None:
                convert_quantity(obj, 1, selected_unit)
    if pk:
        obj.version += 1
    obj.save()
    audit(user, obj, 'updated' if pk else 'created', before)
    return obj


@transaction.atomic
def save_conversion(user, article, values, *, pk=None, expected=None):
    article = Article.objects.select_for_update().get(pk=article.pk)
    require(user, Capability.EDIT_CATALOG, category=article.category)
    obj = ArticleConversion.objects.get(pk=pk, article=article) if pk else ArticleConversion(article=article)
    before = snapshot(obj) if pk else {}
    if pk:
        check_version(obj, expected)
    assign(obj, values)
    if obj.article_id != article.pk or obj.unit_id == article.base_unit_id:
        raise ValidationError(_('La conversion doit concerner une unité alternative du même article.'))
    if not obj.unit.active or not obj.justification.strip():
        raise ValidationError(_('Une unité active et une justification sont obligatoires.'))
    obj.full_clean()
    if pk:
        obj.version += 1
    obj.save()
    audit(user, obj, 'updated' if pk else 'created', before)
    return obj


def quantity(value):
    try:
        if isinstance(value, bool) or len(str(value)) > 64:
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal('999999999999.999999') or (result != 0 and result.adjusted() < -60):
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(_('Saisissez une quantité finie, positive ou nulle, dans les limites autorisées.'))
    return result


def convert_quantity(article, value, unit):
    amount = quantity(value)
    if not article.active or not unit.active or not article.base_unit.active:
        raise ValidationError(_('L’article et les unités doivent être actifs.'))
    with localcontext() as context:
        context.prec = 60
        if unit.pk == article.base_unit_id:
            factor = Decimal(1)
        else:
            explicit = article.conversions.filter(unit=unit, active=True).first()
            if explicit:
                factor = explicit.factor
            elif unit.dimension == article.base_unit.dimension and unit.dimension not in (Unit.Dimension.PACKAGE, Unit.Dimension.OTHER):
                factor = unit.factor / article.base_unit.factor
            else:
                raise ValidationError(_('Aucune conversion validée ne relie ces unités pour cet article.'))
        converted = quantity(amount * factor)
        precise = converted.quantize(Decimal('0.000001'))
        if precise != converted:
            raise ValidationError(_('La conversion dépasse la précision de six décimales ; aucun arrondi silencieux n’est appliqué.'))
    return precise, factor


@transaction.atomic
def record_price(user, article, values):
    article = Article.objects.select_for_update().get(pk=article.pk)
    require(user, Capability.EDIT_COST, category=article.category)
    observation = PriceObservation(article=article, actor=user)
    assign(observation, values)
    if observation.article_id != article.pk or observation.actor_id != user.pk:
        raise ValidationError(_('Une observation ne peut pas être attribuée à un autre article ou utilisateur.'))
    convert_quantity(article, 1, observation.unit)
    if observation.supplier and not observation.supplier.is_supplier:
        raise ValidationError(_('Sélectionnez un fournisseur.'))
    observation.source = observation.source.strip()
    observation.currency = observation.currency.strip().upper()
    if len(observation.currency) != 3 or not observation.currency.isalpha():
        raise ValidationError(_('Code de devise à trois lettres requis.'))
    observation.snapshot = {'article_code': article.code, 'article_name': article.name,
                            'unit_code': observation.unit.code}
    observation.full_clean()
    observation.save()
    audit(user, observation, 'recorded')
    return observation
