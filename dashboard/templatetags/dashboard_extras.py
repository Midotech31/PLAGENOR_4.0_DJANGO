import json

from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Access a dictionary item by key in templates."""
    if dictionary is None:
        return None
    if not hasattr(dictionary, 'get'):
        return None
    return dictionary.get(key)


@register.filter
def as_json(value):
    """Serialize a dict/list to a valid JSON string for an HTML data-attribute.

    ``{{ value|safe }}`` would emit a Python repr (single quotes) that
    ``JSON.parse`` rejects. This emits proper JSON so the client-side cost
    calculator and conditional-logic engine can parse the attribute.
    """
    if value is None:
        return ''
    # Return an ordinary string so Django's normal contextual HTML escaping
    # remains active.  Marking JSON as safe lets quotes or ``</script>`` from
    # editable service configuration break out of attributes/script blocks.
    return json.dumps(value, ensure_ascii=False)


@register.filter
def multiply(value, arg):
    """Multiply the value by the argument."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def percentage(value, total):
    """Calculate percentage of value / total."""
    try:
        return round(float(value) / float(total) * 100, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def filename(path):
    """Extract filename from a file path."""
    if not path:
        return ""
    # Handle both string paths and Path objects
    from pathlib import Path
    if isinstance(path, Path):
        return path.name
    # Handle string paths
    return path.split('/')[-1].split('\\')[-1]
