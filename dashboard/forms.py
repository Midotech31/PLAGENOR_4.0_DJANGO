from django import forms

from core.models import HomepageSection, HomepageBlock


class HomepageSectionForm(forms.ModelForm):
    class Meta:
        model = HomepageSection
        fields = [
            'section_type',
            'slug',
            'title',
            'subtitle',
            'description',
            'image',
            'link_url',
            'payload',
            'position',
            'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'payload': forms.Textarea(attrs={'rows': 6, 'placeholder': '{"key": "value"}'}),
        }


class HomepageBlockForm(forms.ModelForm):
    class Meta:
        model = HomepageBlock
        fields = [
            'block_type',
            'title',
            'text',
            'link_url',
            'image',
            'image_alt',
            'cta_style',
            'payload',
            'position',
            'is_active',
        ]
        widgets = {
            'text': forms.Textarea(attrs={'rows': 4}),
            'payload': forms.Textarea(attrs={'rows': 8, 'placeholder': '{"text": "...", "link": "https://..."}'}),
        }
