from django.shortcuts import render, redirect
from django.views import View
from django.core import exceptions

from excludarr.models import GeneralSettings, Providers, RadarrSettings, SonarrSettings
from excludarr.forms import GeneralSettingsForm, RadarrSettingsForm, SonarrSettingsForm
from excludarr.modules.justwatch import JustWatch
        
        
class SettingsView(View):
    template_name = "settings.html"
    general_prefix = "general"
    radarr_prefix = "radarr"
    sonarr_prefix = "sonarr"
    
    def get(self, request):
        # Check if there is a GeneralSettings object available
        try:
            general_settings = GeneralSettings.objects.get(user=request.user.id)
        except exceptions.ObjectDoesNotExist:
            general_settings = None
            
        # Check if there is a RadarrSettings object available
        try:
            radarr_settings = RadarrSettings.objects.get(user=request.user.id)
        except exceptions.ObjectDoesNotExist:
            radarr_settings = None
            
        # Check if there is a RadarrSettings object available
        try:
            sonarr_settings = SonarrSettings.objects.get(user=request.user.id)
        except exceptions.ObjectDoesNotExist:
            sonarr_settings = None
        
        general_settings_form = GeneralSettingsForm(instance=general_settings, prefix=self.general_prefix)
        providers = Providers.objects.all()
        radarr_settings_form = RadarrSettingsForm(instance=radarr_settings, prefix=self.radarr_prefix)
        sonarr_settings_form = SonarrSettingsForm(instance=sonarr_settings, prefix=self.sonarr_prefix)

        context = {
            "general_settings_form": general_settings_form,
            "providers": providers,
            "radarr_settings_form": radarr_settings_form,
            "sonarr_settings_form": sonarr_settings_form
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request):
        post_data = request.POST.dict()

        # Check if there is a GeneralSettings object available
        try:
            general_settings = GeneralSettings.objects.get(user=request.user.id)
        except exceptions.ObjectDoesNotExist:
            general_settings = None
            
        # Check if there is a RadarrSettings object available
        try:
            radarr_settings = RadarrSettings.objects.get(user=request.user.id)
        except exceptions.ObjectDoesNotExist:
            radarr_settings = None
            
        # Check if there is a RadarrSettings object available
        try:
            sonarr_settings = SonarrSettings.objects.get(user=request.user.id)
        except exceptions.ObjectDoesNotExist:
            sonarr_settings = None
        
        # Setup all the forms
        general_settings_form = GeneralSettingsForm(
            request.POST, 
            instance=general_settings,
            prefix=self.general_prefix
        )
        radarr_settings_form = RadarrSettingsForm(
            request.POST,
            instance=radarr_settings,
            prefix=self.radarr_prefix
        )
        sonarr_settings_form = SonarrSettingsForm(
            request.POST,
            instance=sonarr_settings,
            prefix=self.sonarr_prefix
        )
        
        if general_settings_form.is_valid():
            # Save the form
            general_settings_form.save()
            
            # Get the just set locale
            locale = request.POST["locale"]
            
            # Clear the DB
            Providers.objects.all().delete()
            
            # Write the set of providers into the DB
            jw_client = JustWatch(locale)
            jw_providers = jw_client.get_providers()
            
            for provider in jw_providers:
                if isinstance(provider["monetization_types"], list):
                    if "flatrate" in provider["monetization_types"]:
                        streaming_provider = Providers(
                            id=provider["id"],
                            technical_name=provider["technical_name"],
                            short_name=provider["short_name"],
                            clear_name=provider["clear_name"],
                            active=False)
                            
                        streaming_provider.save()

        if "providers_form" in post_data:
            post_data.pop("csrfmiddlewaretoken")
            post_data.pop("providers_form")

            for provider in Providers.objects.all():
                active = False
                if str(provider.id) in post_data.keys():
                    active = True
                    
                provider.active = active
                provider.save()
            
        if radarr_settings_form.is_valid():
            radarr_settings_form.save()
            
        if sonarr_settings_form.is_valid():
            sonarr_settings_form.save()

        return redirect("settings")
