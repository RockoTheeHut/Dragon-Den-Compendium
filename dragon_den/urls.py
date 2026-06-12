from django.contrib import admin
from django.urls import include, path

from core.views import ThrottledLoginView

urlpatterns = [
    path("", include("core.urls")),
    path("admin/", admin.site.urls),
    # Throttled login must be registered before the auth include so it wins.
    path("accounts/login/", ThrottledLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("compendium/", include("compendium.urls")),
    path("games/", include("games.urls")),
    path("tracker/", include("tracker.urls")),
    path("notes/", include("notes.urls")),
    path("utilities/", include("utilities.urls")),
]
