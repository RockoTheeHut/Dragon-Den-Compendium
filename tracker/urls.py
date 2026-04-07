from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("entries/add-modal/", views.add_entry_modal, name="add_entry_modal"),
    path("entries/monster-options/", views.monster_options, name="monster_options"),
    path("entries/add/", views.add_entry, name="add_entry"),
    path("entries/add-from-compendium/", views.add_from_compendium, name="add_from_compendium"),
    path("entries/add-from-player/", views.add_from_game_player, name="add_from_player"),
    path("entries/<int:entry_id>/edit-modal/", views.edit_entry_modal, name="edit_entry_modal"),
    path("entries/<int:entry_id>/edit/", views.edit_entry, name="edit_entry"),
    path("entries/<int:entry_id>/quick-update/", views.quick_update_entry, name="quick_update_entry"),
    path("entries/<int:entry_id>/remove/", views.remove_entry, name="remove_entry"),
    path("entries/<int:entry_id>/set-current/", views.set_current, name="set_current"),
    path("reorder/", views.reorder_entries, name="reorder"),
    path("advance-turn/", views.advance_turn, name="advance_turn"),
    path("previous-turn/", views.previous_turn, name="previous_turn"),
    path("clear/", views.clear_entries, name="clear_entries"),
    path("entries/<int:entry_id>/status/modal/", views.entry_status_modal, name="entry_status_modal"),
    path("entries/<int:entry_id>/monster/modal/", views.entry_monster_modal, name="entry_monster_modal"),
    path("entries/<int:entry_id>/player/modal/", views.entry_player_modal, name="entry_player_modal"),
    path("entries/<int:entry_id>/status/add/", views.add_status_effect, name="add_status_effect"),
    path("status/<int:effect_id>/play/", views.play_status_effect, name="play_status_effect"),
    path("status/<int:effect_id>/pause/", views.pause_status_effect, name="pause_status_effect"),
    path("status/<int:effect_id>/reset/", views.reset_status_effect, name="reset_status_effect"),
    path("status/<int:effect_id>/remove/", views.remove_status_effect, name="remove_status_effect"),
]
