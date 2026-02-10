from django.contrib import admin

from .models import Game, GameObjectInstance, GamePlayer


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("title", "created_by", "updated_at")
    search_fields = ("title",)


@admin.register(GameObjectInstance)
class GameObjectInstanceAdmin(admin.ModelAdmin):
    list_display = ("name", "game", "object_type", "updated_at")
    search_fields = ("name",)
    list_filter = ("object_type",)


@admin.register(GamePlayer)
class GamePlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "game", "ac", "updated_at")
    search_fields = ("name",)
