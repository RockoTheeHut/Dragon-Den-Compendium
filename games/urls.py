from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.game_list, name="list"),
    path("<int:pk>/", views.game_detail, name="detail"),
    path("<int:pk>/delete/", views.delete_game, name="delete"),
    path("<int:game_id>/encounters/create/", views.create_encounter, name="create_encounter"),
    path("<int:game_id>/encounters/<int:encounter_id>/delete/", views.delete_encounter, name="delete_encounter"),
    path("<int:game_id>/encounters/<int:encounter_id>/tracker/", views.open_encounter_tracker, name="open_encounter_tracker"),
    path("<int:game_id>/players/create/", views.create_player, name="create_player"),
    path("<int:game_id>/players/<int:player_id>/edit-modal/", views.edit_player_modal, name="edit_player_modal"),
    path("<int:game_id>/players/<int:player_id>/edit/", views.edit_player, name="edit_player"),
    path("<int:game_id>/players/<int:player_id>/delete/", views.delete_player, name="delete_player"),
    path("<int:game_id>/instances/<int:instance_id>/edit/", views.edit_instance, name="edit_instance"),
    path("<int:game_id>/instances/<int:instance_id>/remove/", views.remove_instance, name="remove_instance"),
]
