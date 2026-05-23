"""Atomic sequence allocation for display IDs and invoice numbers.

Drop-in safe replacement for the racy ``Model.objects.filter(...).count() + 1``
pattern. The counter row is locked via ``SELECT … FOR UPDATE`` inside a
transaction — works the same on PostgreSQL (true row lock) and SQLite
(transaction serialization makes it effectively atomic).

Usage::

    from core.sequences import next_display_id
    display_id = next_display_id('GCL', 2026)

For brand-new (prefix, year) combinations that have legacy data the
migration didn't seed, pass ``initial_value_fn`` so the counter starts
from the current high-water mark and we don't collide with existing IDs.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from django.db import IntegrityError, transaction

from core.models import SequenceCounter

logger = logging.getLogger('plagenor.sequences')


def next_value(scope: str, initial_value_fn: Optional[Callable[[], int]] = None) -> int:
    """Atomically return the next integer for ``scope``.

    If the counter row doesn't exist yet, create it seeded from
    ``initial_value_fn()`` (or 0 if omitted), then increment. Two callers
    racing on first-creation are handled via ``IntegrityError`` + retry.
    """
    for _attempt in range(3):
        try:
            with transaction.atomic():
                counter = SequenceCounter.objects.select_for_update().get(scope=scope)
                counter.value = counter.value + 1
                counter.save(update_fields=['value', 'updated_at'])
                return counter.value
        except SequenceCounter.DoesNotExist:
            initial = int(initial_value_fn()) if initial_value_fn else 0
            try:
                SequenceCounter.objects.create(scope=scope, value=initial)
            except IntegrityError:
                # Lost the race; another caller created it. Loop and lock it.
                continue
    raise RuntimeError(f"next_value({scope!r}) failed after retries")


def next_display_id(prefix: str, year: int,
                    initial_value_fn: Optional[Callable[[], int]] = None) -> str:
    """Return the next ``f"{prefix}-{year}-{NNNN}"`` ID atomically."""
    seq = next_value(f"{prefix}-{year}", initial_value_fn)
    return f"{prefix}-{year}-{seq:04d}"
