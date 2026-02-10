from django.conf import settings
from django.db import models
from django.db.models import Q

SHARED_NOTE_CONTENT_MAX_LENGTH = 65535
SCRATCHPAD_CHAR_BUFFER = 64
SCRATCHPAD_MAX_LENGTH = SHARED_NOTE_CONTENT_MAX_LENGTH - SCRATCHPAD_CHAR_BUFFER


class SharedNoteQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Return public notes for guests; public + owned notes for authenticated users."""
        if not user.is_authenticated:
            return self.filter(visibility=SharedNote.Visibility.PUBLIC)
        return self.filter(Q(visibility=SharedNote.Visibility.PUBLIC) | Q(created_by=user))


class SharedNote(models.Model):
    """Simple note model used for scratchpad and potentially shared notes."""
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    title = models.CharField(max_length=255)
    content = models.CharField(max_length=SHARED_NOTE_CONTENT_MAX_LENGTH, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shared_notes")
    visibility = models.CharField(max_length=16, choices=Visibility.choices, default=Visibility.PUBLIC)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SharedNoteQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title
