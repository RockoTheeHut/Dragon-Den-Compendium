from django.contrib import admin

from .models import StatusEffect, TurnTrackerEntry


class StatusEffectInline(admin.TabularInline):
    model = StatusEffect
    extra = 0


@admin.register(TurnTrackerEntry)
class TurnTrackerEntryAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "entry_type", "initiative", "is_active", "is_current", "sort_order")
    list_filter = ("entry_type", "is_active", "is_current", "source_kind")
    search_fields = ("name", "notes", "source_name")
    inlines = [StatusEffectInline]


@admin.register(StatusEffect)
class StatusEffectAdmin(admin.ModelAdmin):
    list_display = ("name", "entry", "remaining_rounds", "duration_rounds", "is_running")
    list_filter = ("is_running",)
    search_fields = ("name",)
