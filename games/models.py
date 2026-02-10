from django.conf import settings
from django.db import models

from compendium.models import GameObject


class Game(models.Model):
    """A DM-owned campaign/workspace that contains object instances."""
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="games")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class GameObjectInstance(models.Model):
    """Per-game snapshot/copy of a base compendium object."""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="object_instances")
    base_object = models.ForeignKey(GameObject, on_delete=models.CASCADE, related_name="game_instances")
    name = models.CharField(max_length=255)
    object_type = models.CharField(max_length=32, choices=GameObject.ObjectType.choices, db_index=True)
    description = models.TextField(blank=True, null=True)
    data = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=32, default="game_copy", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["game", "object_type", "name"])]

    def __str__(self):
        return f"{self.name} ({self.game.title})"


class Encounter(models.Model):
    """One encounter inside a game; each encounter can have its own turn tracker state."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="encounters")
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["game", "title"])]

    def __str__(self):
        return f"{self.title} ({self.game.title})"


class GamePlayer(models.Model):
    """A reusable player record inside a game for quick encounter adds."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="players")
    name = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    ac = models.PositiveSmallIntegerField(null=True, blank=True)
    base_stat_block = models.TextField(blank=True)
    strength = models.PositiveSmallIntegerField(null=True, blank=True)
    dexterity = models.PositiveSmallIntegerField(null=True, blank=True)
    constitution = models.PositiveSmallIntegerField(null=True, blank=True)
    intelligence = models.PositiveSmallIntegerField(null=True, blank=True)
    wisdom = models.PositiveSmallIntegerField(null=True, blank=True)
    charisma = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [models.Index(fields=["game", "name"])]

    def __str__(self):
        return f"{self.name} ({self.game.title})"
