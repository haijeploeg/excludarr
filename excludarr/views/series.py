from django.shortcuts import render
from django.views import View
        

class SeriesView(View):
        
    def get(self, request):
        return render(request, "series.html")
