from django.contrib import admin

from .models import SharedNote


@admin.register(SharedNote)
class SharedNoteAdmin(admin.ModelAdmin):
    list_display = ("title", "created_by", "visibility", "updated_at")
    list_filter = ("visibility",)
    search_fields = ("title", "content")
