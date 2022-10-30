from django.urls import path

from .views import MoviesView, SeriesView, SettingsView, EventsView, TasksView

urlpatterns = [
    path("", MoviesView.as_view(), name="movies"),
    path("movies/", MoviesView.as_view(), name="movies"),
    path("series/", SeriesView.as_view(), name="series"),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("system/events", EventsView.as_view(), name="events"),
    path("tasks/", TasksView.as_view(), name="tasks"),
]
