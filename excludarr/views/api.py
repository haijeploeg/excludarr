from rest_framework.viewsets import ReadOnlyModelViewSet, ViewSet
from rest_framework.response import Response
from rest_framework import status

from excludarr.models import Tasks
from excludarr.serializers import TasksSerializer


class ApiTasksViewSet(ReadOnlyModelViewSet):
    http_method_names = ["get"]
    queryset = Tasks.objects.all()
    serializer_class = TasksSerializer


class ApiSyncViewSet(ViewSet):
    
    def list(self, request):
        queryset = Tasks.objects.filter(kind="MOVIE")
        serializer = TasksSerializer(queryset, many=True)
        return Response(serializer.data)
        
    def post(self, request):
        print(request.POST)