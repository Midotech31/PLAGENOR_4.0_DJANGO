"""Translate display copy without ever translating stored identifiers or prices."""
import json
from functools import lru_cache
from pathlib import Path
from django.utils.translation import get_language, gettext


@lru_cache(maxsize=1)
def catalogue_translations():
    rows = json.loads((Path(__file__).parent / 'catalogue_translations.json').read_text(encoding='utf-8'))
    return {source: dict(zip(('fr', 'en', 'ar'), row[1:])) for row in rows for source in row}


def catalogue_text(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    translations = catalogue_translations().get(text)
    if translations:
        return translations.get((get_language() or 'fr').split('-')[0], translations['fr'])
    return gettext(text)


def catalogue_items(value):
    """Flatten registry lists and nested headings into readable, escaped bullets."""
    if isinstance(value, dict):
        return [f'{catalogue_text(key)} : {" ; ".join(catalogue_items(items))}'
                for key, items in value.items()]
    if isinstance(value, list):
        return [text for item in value for text in catalogue_items(item)]
    return [str(catalogue_text(value))] if value else []
