from django.urls import path

from . import views

app_name = "compendium"

urlpatterns = [
    path("", views.object_list, name="list"),
    path("create/", views.object_create, name="object_create"),
    path("tags/", views.tag_list, name="tags"),
    path("tags/<int:pk>/update/", views.tag_update, name="tag_update"),
    path("tags/<int:pk>/remove/", views.remove_tag, name="tag_remove"),
    path("search/preview/", views.search_preview, name="search_preview"),
    path("search/go/", views.quick_search_redirect, name="search_go"),
    path("<int:pk>/preview/modal/", views.object_preview_modal, name="object_preview_modal"),
    path("<int:pk>/", views.object_detail, name="object_detail"),
    path("<int:pk>/edit/", views.object_edit, name="object_edit"),
    path("<int:pk>/favorite/", views.toggle_favorite, name="toggle_favorite"),
]
