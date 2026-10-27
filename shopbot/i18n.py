import json
from functools import lru_cache
from pathlib import Path
from string import Formatter

from .db import get_language, set_language as save_language

_LOCALE_PATH = Path(__file__).resolve().parent / "locales.json"
with _LOCALE_PATH.open(encoding="utf-8") as locale_file:
    _TRANSLATIONS = json.load(locale_file)

_EXPECTED_LANGUAGES = {"ru", "uz", "en"}
if set(_TRANSLATIONS) != _EXPECTED_LANGUAGES:
    raise ValueError(f"{_LOCALE_PATH} must define exactly: {sorted(_EXPECTED_LANGUAGES)}")

_KEYS = set(_TRANSLATIONS["en"])
_FORMAT_FIELDS = {
    key: {field for _, field, _, _ in Formatter().parse(template) if field}
    for key, template in _TRANSLATIONS["en"].items()
}
for _language, _messages in _TRANSLATIONS.items():
    if set(_messages) != _KEYS:
        raise ValueError(f"Locale {_language} has missing or extra translation keys.")
    for _key, _template in _messages.items():
        fields = {field for _, field, _, _ in Formatter().parse(_template) if field}
        if fields != _FORMAT_FIELDS[_key]:
            raise ValueError(
                f"Locale {_language} has incompatible format fields for {_key}."
            )

def set_language(user_id: int, language: str):
    save_language(user_id, language)
    _language_for_user.cache_clear()


@lru_cache(maxsize=4096)
def _language_for_user(user_id: int) -> str:
    return get_language(user_id)


def translate(user_id: int, key: str, **values) -> str:
    language = _language_for_user(user_id)
    template = _TRANSLATIONS[language][key]
    return template.format(**values)
