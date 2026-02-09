from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("entries/add/", views.add_entry, name="add_entry"),
    path("entries/add-from-compendium/", views.add_from_compendium, name="add_from_compendium"),
    path("entries/add-from-instance/", views.add_from_game_instance, name="add_from_instance"),
    path("entries/<int:entry_id>/remove/", views.remove_entry, name="remove_entry"),
    path("entries/<int:entry_id>/toggle-active/", views.toggle_active, name="toggle_active"),
    path("entries/<int:entry_id>/set-current/", views.set_current, name="set_current"),
    path("entries/<int:entry_id>/move-up/", views.move_up, name="move_up"),
    path("entries/<int:entry_id>/move-down/", views.move_down, name="move_down"),
    path("reorder/", views.reorder_entries, name="reorder"),
    path("advance-turn/", views.advance_turn, name="advance_turn"),
    path("entries/<int:entry_id>/status/add/", views.add_status_effect, name="add_status_effect"),
    path("status/<int:effect_id>/play/", views.play_status_effect, name="play_status_effect"),
    path("status/<int:effect_id>/pause/", views.pause_status_effect, name="pause_status_effect"),
    path("status/<int:effect_id>/reset/", views.reset_status_effect, name="reset_status_effect"),
    path("status/<int:effect_id>/remove/", views.remove_status_effect, name="remove_status_effect"),
]
