from django.db import models


class GeneralSettings(models.Model):
    id = models.IntegerField(default=1, null=False, primary_key=True)
    locale = models.CharField(max_length=5)


class Providers(models.Model):
    id = models.IntegerField(primary_key=True)
    technical_name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=50)
    clear_name = models.CharField(max_length=50)
    active = models.BooleanField()
