from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.game_list, name="list"),
    path("<int:pk>/", views.game_detail, name="detail"),
    path("<int:pk>/delete/", views.delete_game, name="delete"),
    path("<int:game_id>/add-object/<int:object_id>/", views.add_object_to_game, name="add_object"),
    path("<int:game_id>/instances/<int:instance_id>/edit/", views.edit_instance, name="edit_instance"),
    path("<int:game_id>/instances/<int:instance_id>/remove/", views.remove_instance, name="remove_instance"),
    path("<int:game_id>/turn-entries/add/", views.add_custom_turn_entry, name="add_turn_entry"),
]
