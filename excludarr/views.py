from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.core import exceptions

from core.settings import BASE_DIR

from .models import GeneralSettings
from .forms import GeneralSettingsForm, ProvidersForm


class MoviesView(View):
        
    def get(self, request):
        return render(request, "movies.html")
        
    def post(self, request):
        print(request)
        import time
        time.sleep(10)
        return JsonResponse({"foo": "bar"})
        

class SeriesView(View):
        
    def get(self, request):
        return render(request, "series.html")
        
        
class SettingsView(View):
    template_name = "settings.html"
    
    def get(self, request):
        try:
            general_settings = GeneralSettings.objects.get(id=1)
        except exceptions.ObjectDoesNotExist:
            general_settings = None
            
        general_settings_form = GeneralSettingsForm(instance=general_settings)
        providers_form = ProvidersForm()
        
        context = {
            "general_settings_form": general_settings_form,
            "providers_form": providers_form
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request):
        try:
            general_settings = GeneralSettings.objects.get(id=1)
        except exceptions.ObjectDoesNotExist:
            general_settings = None

        general_settings_form = GeneralSettingsForm(request.POST, instance=general_settings)
        
        if general_settings_form.is_valid():
            general_settings_form.save()
            
        return redirect("settings")
            
        
class EventsView(View):
    
    def get(self, request):
        pass


class TasksView(View):
    
    def get(self, request):
        return JsonResponse({"foo": "bar"})

