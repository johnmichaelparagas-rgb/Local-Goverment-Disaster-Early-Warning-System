from django import forms
from django.forms import inlineformset_factory

from .models import HazardImage, Incident


class IncidentForm(forms.ModelForm):
    class Meta:
        model = Incident
        fields = [
            'type', 'municipality', 'barangay', 'severity', 'status',
            'summary', 'public_summary',
            'dispatcher_name', 'dispatcher_phone', 'dispatcher_email',
            'reporter_name', 'reporter_contact', 'internal_notes',
            'lat', 'lng',
        ]
        widgets = {
            'summary': forms.Textarea(attrs={'rows': 2}),
            'public_summary': forms.Textarea(attrs={'rows': 2}),
            'internal_notes': forms.Textarea(attrs={'rows': 2}),
        }


class IncidentStatusForm(forms.ModelForm):
    """Dispatchers may only move an incident through its status lifecycle."""
    class Meta:
        model = Incident
        fields = ['status', 'internal_notes']
        widgets = {'internal_notes': forms.Textarea(attrs={'rows': 3})}


class HazardImageForm(forms.ModelForm):
    class Meta:
        model = HazardImage
        fields = ['image', 'caption']


# Inline formset: one Incident -> many HazardImages, edited in a single submit.
# Images are optional (min_num=0); add up to `extra` new rows at a time.
HazardImageFormSet = inlineformset_factory(
    Incident,
    HazardImage,
    form=HazardImageForm,
    extra=3,
    can_delete=True,
    min_num=0,
    validate_min=False,
)
