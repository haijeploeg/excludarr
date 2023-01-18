from django.shortcuts import render
from django.http import JsonResponse
from django.views import View

from excludarr.models import Movies, RadarrSettings
from excludarr.services.radarr import Radarr


class MoviesView(View):
        
    def get(self, request):
        # radarr_settings = RadarrSettings.objects.get(user=request.user.id)
        # radarr = Radarr(radarr_settings.host, radarr_settings.api_key)
        # radarr.sync_all_to_db()
        
        movies = Movies.objects.all()
        
        context = {
            "movies": movies
        }
        
        return render(request, "movies.html", context)
