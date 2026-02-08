from django.urls import path

from . import views

app_name = "utilities"

urlpatterns = [
    path("magic-item/", views.magic_item_generator, name="magic_item"),
    path("magic-item/save-global/", views.save_magic_item_global, name="save_magic_item_global"),
    path("magic-item/save-game/", views.save_magic_item_to_game, name="save_magic_item_game"),
    path("dice-roll/<int:game_id>/", views.dice_roll, name="dice_roll"),
]
