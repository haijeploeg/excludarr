from django.urls import path, include
from rest_framework import routers

from excludarr.views.lists import ListsView
from excludarr.views.movies import MoviesView
from excludarr.views.series import SeriesView
from excludarr.views.settings import  SettingsView
from excludarr.views.system import SystemEventsView
from excludarr.views.api import ApiTasksViewSet, ApiSyncViewSet


router = routers.DefaultRouter()
router.register(r"tasks", ApiTasksViewSet)
router.register(r"sync", ApiSyncViewSet, basename="sync")


urlpatterns = [
    path("", MoviesView.as_view(), name="movies"),
    path("lists/", ListsView.as_view(), name="lists"),
    path("movies/", MoviesView.as_view(), name="movies"),
    path("series/", SeriesView.as_view(), name="series"),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("system/events/", SystemEventsView.as_view(), name="events"),
    path("api/", include(router.urls)),
]
