from django import forms

from .models import GeneralSettings, Providers


class GeneralSettingsForm(forms.ModelForm):
    locale = forms.CharField(
        min_length=2,
        max_length=5,
        widget=forms.TextInput(
            attrs={
                "class": "form-control"
            }
        )
    )

    class Meta:
        model = GeneralSettings
        fields = ("locale",)
        

class ProvidersForm(forms.ModelForm):
    providers = forms.ModelMultipleChoiceField(queryset=Providers.objects.all())

    class Meta:
        model = Providers
        fields = ("providers",)
