from django.conf import settings
from django.db import models

from compendium.models import GameObject


class Game(models.Model):
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="games")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class GameObjectInstance(models.Model):
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
