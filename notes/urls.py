from django.urls import path

from . import views

app_name = "notes"

urlpatterns = [
    path("modal/", views.modal, name="modal"),
    path("create/", views.create_note, name="create"),
    path("<int:pk>/update/", views.update_note, name="update"),
    path("<int:pk>/delete/", views.delete_note, name="delete"),
]
