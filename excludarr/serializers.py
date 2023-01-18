from rest_framework import serializers
from excludarr.models import Tasks


class TasksSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Tasks
        fields = ["kind", "status", "created", "updated"]
