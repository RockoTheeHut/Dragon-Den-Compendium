from django.contrib import admin

from .models import Favorite, GameObject, GameObjectTag, Tag


@admin.register(GameObject)
class GameObjectAdmin(admin.ModelAdmin):
    list_display = ("name", "system", "object_type", "source", "updated_at")
    search_fields = ("name", "description", "external_id")
    list_filter = ("system", "object_type", "source")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "system", "color", "is_system_tag")
    list_filter = ("system", "is_system_tag")
    search_fields = ("name",)


@admin.register(GameObjectTag)
class GameObjectTagAdmin(admin.ModelAdmin):
    list_display = ("game_object", "tag")


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "game_object")
