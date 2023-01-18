from django import forms

from excludarr.models import GeneralSettings, RadarrSettings, SonarrSettings
from excludarr.services.justwatch import get_jw_providers_form_choices


class GeneralSettingsForm(forms.ModelForm):
    locale = forms.ChoiceField(
        widget=forms.Select(
            attrs={
                "class": "form-select"
            }
        ),
        choices=get_jw_providers_form_choices()
    )

    class Meta:
        model = GeneralSettings
        fields = ("locale",)


class RadarrSettingsForm(forms.ModelForm):
    host = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control"
            }
        )
    )
    api_key = forms.CharField(
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "class": "form-control"
            }
        )
    )
    verify_ssl = forms.BooleanField(
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input"
            }
        )
    )
    
    class Meta:
        model = RadarrSettings
        fields = ("host", "api_key", "verify_ssl",)
        
        
class SonarrSettingsForm(forms.ModelForm):
    host = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control"
            }
        )
    )
    api_key = forms.CharField(
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "class": "form-control"
            }
        )
    )
    verify_ssl = forms.BooleanField(
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input"
            }
        )
    )
    
    class Meta:
        model = SonarrSettings
        fields = ("host", "api_key", "verify_ssl",)
