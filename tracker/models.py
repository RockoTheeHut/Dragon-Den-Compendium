from django.db import models
from django.db.models import Q

from games.models import Game, GameObjectInstance


class TurnEntry(models.Model):
    class EntityType(models.TextChoices):
        CHARACTER = "character", "Character"
        NPC = "npc", "NPC"
        MONSTER = "monster", "Monster"
        CUSTOM = "custom", "Custom"

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="turn_entries")
    entity_type = models.CharField(max_length=32, choices=EntityType.choices)
    object_instance = models.ForeignKey(
        GameObjectInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="turn_entries",
    )
    display_name = models.CharField(max_length=255)
    initiative = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_current = models.BooleanField(default=False)
    hp_current = models.IntegerField(null=True, blank=True)
    hp_max = models.IntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["game", "sort_order"])]
        constraints = [
            models.UniqueConstraint(
                fields=["game"],
                condition=Q(is_current=True),
                name="unique_current_turn_entry_per_game",
            )
        ]

    def __str__(self):
        return f"{self.display_name} ({self.game.title})"
