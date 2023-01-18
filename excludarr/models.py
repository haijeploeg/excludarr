from django.db import models
from django.contrib.auth.models import User


TASK_KIND_CHOICES = [
    ("MOVIE", "Movie"),
    ("SERIE", "Serie")
]

TASK_STATUS_CHOICES = [
    ("SUCCESS", "Success"),
    ("FAILED", "Failed"),
    ("RUNNING", "Running")
]


class GeneralSettings(models.Model):
    id = models.IntegerField(default=1, null=False, primary_key=True)
    locale = models.CharField(max_length=5)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)


class Providers(models.Model):
    id = models.IntegerField(primary_key=True)
    technical_name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=50)
    clear_name = models.CharField(max_length=50)
    active = models.BooleanField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.clear_name 


class RadarrSettings(models.Model):
    id = models.IntegerField(default=1, null=False, primary_key=True)
    host = models.CharField(max_length=50)
    api_key = models.CharField(max_length=32)
    verify_ssl = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)


class SonarrSettings(models.Model):
    id = models.IntegerField(default=1, null=False, primary_key=True)
    host = models.CharField(max_length=50)
    api_key = models.CharField(max_length=32)
    verify_ssl = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)


class Movies(models.Model):
    radarr_id = models.IntegerField(null=False)
    title = models.CharField(max_length=512)
    tmdb_id = models.IntegerField(null=True, blank=True)
    imdb_id = models.CharField(max_length=20, null=True, blank=True)
    size = models.BigIntegerField(null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    quality_available = models.CharField(max_length=50, null=True, blank=True)
    poster = models.CharField(max_length=512, null=True, blank=True)
    tags = models.CharField(max_length=1024, null=True, blank=True)
    monitored = models.BooleanField()
    excluded = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)


class Tasks(models.Model):
    kind = models.CharField(
        max_length=10,
        choices=TASK_KIND_CHOICES
    )
    status = models.CharField(
        max_length=10,
        choices=TASK_STATUS_CHOICES
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
