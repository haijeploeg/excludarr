from django.shortcuts import render
from django.http import JsonResponse
from django.views import View

from excludarr.models import Movies


class ListsView(View):
        
    def get(self, request):        
        movies = Movies.objects.all()        
        
        context = {
            "movies": movies
        }
        
        return render(request, "lists.html", context)
