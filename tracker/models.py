from django.conf import settings
from django.db import models
from django.db.models import Q

from games.models import Encounter


class TurnTrackerEntry(models.Model):
    """One initiative-row entity in a user's turn tracker."""
    class EntryType(models.TextChoices):
        PLAYER = "player", "Player"
        NPC = "npc", "NPC"
        ENEMY = "enemy", "Enemy"

    class SourceKind(models.TextChoices):
        MANUAL = "manual", "Manual"
        COMPENDIUM_MONSTER = "compendium_monster", "Compendium Monster"
        GAME_INSTANCE = "game_instance", "Game Object Instance"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tracker_entries")
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="tracker_entries", null=True, blank=True)
    name = models.CharField(max_length=255)
    entry_type = models.CharField(max_length=16, choices=EntryType.choices)
    initiative = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_current = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    hp_current = models.IntegerField(null=True, blank=True)
    hp_max = models.IntegerField(null=True, blank=True)
    items_text = models.TextField(blank=True)

    source_kind = models.CharField(max_length=32, choices=SourceKind.choices, default=SourceKind.MANUAL)
    source_name = models.CharField(max_length=255, blank=True)
    source_snapshot = models.JSONField(default=dict, blank=True)

    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["user", "sort_order"]),
            models.Index(fields=["user", "encounter", "sort_order"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_current=True, encounter__isnull=True),
                name="unique_current_global_tracker_entry_per_user",
            ),
            models.UniqueConstraint(
                fields=["user", "encounter"],
                condition=Q(is_current=True, encounter__isnull=False),
                name="unique_current_encounter_tracker_entry_per_user",
            )
        ]

    def save(self, *args, **kwargs):
        """Players do not track shared HP/items in this tracker representation."""
        if self.entry_type == self.EntryType.PLAYER:
            self.hp_current = None
            self.hp_max = None
            self.items_text = ""
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.entry_type})"


class StatusEffect(models.Model):
    """Round-based effect tied to a tracker entry."""
    entry = models.ForeignKey(TurnTrackerEntry, on_delete=models.CASCADE, related_name="status_effects")
    name = models.CharField(max_length=120)
    duration_rounds = models.PositiveIntegerField()
    remaining_rounds = models.PositiveIntegerField()
    is_running = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name} ({self.remaining_rounds}/{self.duration_rounds})"
