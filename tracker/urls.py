from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("<int:game_id>/next/", views.next_turn, name="next_turn"),
    path("<int:game_id>/previous/", views.previous_turn, name="previous_turn"),
    path("<int:game_id>/reorder/", views.reorder_entries, name="reorder"),
    path("<int:game_id>/entries/<int:entry_id>/current/", views.set_current, name="set_current"),
    path("<int:game_id>/entries/<int:entry_id>/remove/", views.remove_entry, name="remove_entry"),
    path("<int:game_id>/entries/<int:entry_id>/toggle-active/", views.toggle_active, name="toggle_active"),
]
