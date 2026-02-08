from django.contrib import admin

from .models import TurnEntry


@admin.register(TurnEntry)
class TurnEntryAdmin(admin.ModelAdmin):
    list_display = ("display_name", "game", "initiative", "is_current", "sort_order")
    list_filter = ("game", "entity_type", "is_current")
    search_fields = ("display_name",)
