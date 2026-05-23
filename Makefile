# PLAGENOR 4.0 — common developer commands.
#
# Phase 3.0 (localization) targets:
#   make i18n-extract   — refresh locale/<lang>/LC_MESSAGES/*.po from source.
#   make i18n-compile   — build .mo catalogs from .po files (run on deploy).
#   make i18n-upload    — push the French source .po files to Crowdin.
#   make i18n-download  — pull translated en/ar .po files from Crowdin.
#   make i18n-cycle     — full round-trip (extract → upload).

.PHONY: i18n-extract i18n-compile i18n-upload i18n-download i18n-cycle

LANGS = fr en ar

i18n-extract:
	@for lang in $(LANGS); do \
		python manage.py makemessages -l $$lang \
			--ignore=venv --ignore=staticfiles --ignore=node_modules \
			--ignore=data --ignore=media; \
	done
	@for lang in $(LANGS); do \
		python manage.py makemessages -d djangojs -l $$lang \
			--ignore=venv --ignore=staticfiles --ignore=node_modules \
			--ignore=data --ignore=media; \
	done

i18n-compile:
	python manage.py compilemessages

i18n-upload:
	crowdin upload sources

i18n-download:
	crowdin download

i18n-cycle: i18n-extract i18n-upload
