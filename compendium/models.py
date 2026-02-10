from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Color must be in #RRGGBB format.",
)


class GameObject(models.Model):
    """Canonical compendium object shared across games and utilities."""
    class ObjectType(models.TextChoices):
        MONSTER = "monster", "Monster"
        SPELL = "spell", "Spell"
        ITEM = "item", "Item"
        CLASS = "class", "Class"
        RACE = "race", "Race"
        FEAT = "feat", "Feat"
        BACKGROUND = "background", "Background"
        CHARACTER = "character", "Character"
        NPC = "npc", "NPC"
        MISC = "misc", "Misc"

    class SourceType(models.TextChoices):
        OFFICIAL = "official", "Official"
        IMPORTED = "imported", "Imported"
        CUSTOM = "custom", "Custom"

    system = models.CharField(max_length=64, db_index=True)
    object_type = models.CharField(max_length=32, choices=ObjectType.choices, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    source = models.CharField(max_length=32, choices=SourceType.choices, db_index=True)
    external_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField("Tag", through="GameObjectTag", related_name="game_objects", blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["system", "object_type", "name"]),
            models.Index(fields=["system", "external_id"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.object_type})"


class Tag(models.Model):
    """Reusable metadata label scoped by system (for example dnd5e)."""
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, validators=[hex_color_validator])
    system = models.CharField(max_length=64, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tags",
    )
    is_system_tag = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["system", "name"], name="unique_tag_name_per_system"),
        ]
        indexes = [models.Index(fields=["system", "name"])]

    def __str__(self):
        return self.name


class GameObjectTag(models.Model):
    """Explicit through-table joining objects and tags."""
    game_object = models.ForeignKey(GameObject, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game_object", "tag"], name="unique_game_object_tag"),
        ]

    def __str__(self):
        return f"{self.game_object.name} -> {self.tag.name}"


class Favorite(models.Model):
    """User bookmark for a compendium object."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    game_object = models.ForeignKey(GameObject, on_delete=models.CASCADE, related_name="favorited_by")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "game_object"], name="unique_user_game_object_favorite"),
        ]

    def __str__(self):
        return f"{self.user} favorited {self.game_object}"
