from django.shortcuts import render
from django.views import View
            
        
class SystemEventsView(View):
    
    def get(self, request):
        return render(request, 'events.html')
