from django import template
from core.financial_visibility import estimates_visible, request_financials_visible, quote_released

register = template.Library()
register.filter('estimates_visible', estimates_visible)
register.filter('financials_visible', request_financials_visible)
register.filter('quote_released', quote_released)
