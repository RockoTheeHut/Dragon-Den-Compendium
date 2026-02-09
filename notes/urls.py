from django.urls import path

from . import views

app_name = "notes"

urlpatterns = [
    path("modal/", views.modal, name="modal"),
    path("save/", views.save_scratchpad, name="save"),
    path("clear/", views.clear_scratchpad, name="clear"),
]
