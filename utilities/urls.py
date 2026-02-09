from django.urls import path

from . import views

app_name = "utilities"

urlpatterns = [
    path("magic-item/", views.magic_item_generator, name="magic_item"),
    path("magic-item/save-global/", views.save_magic_item_global, name="save_magic_item_global"),
    path("magic-item/save-game/", views.save_magic_item_to_game, name="save_magic_item_game"),
    path("dice/modal/", views.dice_modal, name="dice_modal"),
    path("dice/roll/", views.dice_roll_tool, name="dice_roll_tool"),
]
