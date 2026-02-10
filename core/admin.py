from django.contrib import admin

from .models import UserImportedObject, UserSettings


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at")
    search_fields = ("user__username",)


@admin.register(UserImportedObject)
class UserImportedObjectAdmin(admin.ModelAdmin):
    list_display = ("user", "game_object", "created_at")
    search_fields = ("user__username", "game_object__name")
