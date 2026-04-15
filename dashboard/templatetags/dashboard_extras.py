from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Access a dictionary item by key in templates."""
    if dictionary is None:
        return None
    value = dictionary.get(key)
    # Convert floats to locale-independent string representation
    if isinstance(value, float):
        # Use Python's default string representation (always uses .)
        return str(value)
    return value


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


@register.filter
def min_filter(value, arg):
    """Return minimum of value and arg."""
    try:
        return min(float(value), float(arg))
    except (ValueError, TypeError):
        return value


@register.filter
def max_filter(value, arg):
    """Return maximum of value and arg."""
    try:
        return max(float(value), float(arg))
    except (ValueError, TypeError):
        return value


@register.filter
def in_list(value, csv_values):
    """Check if value exists in a comma-separated list."""
    if value is None:
        return False
    if not csv_values:
        return False
    values = [item.strip() for item in str(csv_values).split(',') if item.strip()]
    return str(value) in values
