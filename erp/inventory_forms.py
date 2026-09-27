from django import forms
from django.utils.translation import gettext_lazy as _

from .models import LegacyInventoryRecord


class LegacyInventoryReviewForm(forms.Form):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    review_status = forms.ChoiceField(
        label=_('Conclusion de la revue'),
        choices=[
            (LegacyInventoryRecord.ReviewStatus.CONFIRMED,
             _('Source vérifiée / donnée confirmée')),
            (LegacyInventoryRecord.ReviewStatus.CORRECTED,
             _('Correction reportée dans PLAGENOR')),
            (LegacyInventoryRecord.ReviewStatus.NOT_APPLICABLE,
             _('Non applicable / ne pas importer')),
        ],
    )
    review_note = forms.CharField(
        label=_('Justification / correction effectuée'),
        min_length=5,
        max_length=2000,
        widget=forms.Textarea(attrs={'rows': 5}),
        help_text=_(
            "La donnée source originale reste immuable. Décrivez ici la vérification "
            "ou la correction réellement effectuée dans PLAGENOR."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs['class'] = 'form-control'
