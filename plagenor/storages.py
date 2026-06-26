"""Storage backends for PLAGENOR.

Uploaded media (reports, order/payment files, avatars, gift and service
images, DOCX templates) must survive process restarts. Render's free tier
has an ephemeral disk, so anything written under ``MEDIA_ROOT`` is lost on
every redeploy / restart. ``SupabaseMediaStorage`` keeps the bytes on
Supabase Storage (S3-compatible) instead.

Crucially, file URLs are forced back to the same-origin ``/media/<name>``
path so that **every** file is still served *through Django*
(``serve_media`` for ordinary media, ``protected_report_media`` for report
PDFs). Two reasons:

1. The IBTIKAR citation-clause gate lives in ``protected_report_media`` and
   only works if report links stay under ``/media/reports/...``. Handing the
   browser a direct (or signed) Supabase URL would bypass the gate.
2. The bucket can therefore stay **private** — the browser never talks to
   Supabase Storage directly; Django streams the bytes via the S3 API.
"""

from django.conf import settings
from storages.backends.s3 import S3Storage


class SupabaseMediaStorage(S3Storage):
    """S3 storage on Supabase whose public URL points back at Django."""

    def url(self, name, parameters=None, expire=None, http_method=None):
        # Never expose the Supabase/S3 URL. Serve through Django instead so
        # the citation gate stays effective and the bucket stays private.
        return f"{settings.MEDIA_URL}{str(name).lstrip('/')}"
