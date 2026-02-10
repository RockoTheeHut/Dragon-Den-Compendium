from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("compendium/", include("compendium.urls")),
    path("games/", include("games.urls")),
    path("tracker/", include("tracker.urls")),
    path("notes/", include("notes.urls")),
    path("utilities/", include("utilities.urls")),
]
