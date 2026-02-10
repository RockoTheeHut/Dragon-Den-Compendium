from django.conf import settings as django_settings
from django.db import models


class UserSettings(models.Model):
    """Per-user configuration values that should override server defaults."""
    user = models.OneToOneField(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="settings")
    openai_api_key = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "User settings"

    def __str__(self):
        return f"Settings for {self.user.username}"

    @classmethod
    def for_user(cls, user):
        """Return existing settings for a user or create a default row."""
        if not user or not user.is_authenticated:
            return None
        user_settings, _created = cls.objects.get_or_create(user=user)
        return user_settings


def get_effective_openai_api_key(user):
    """Prefer user-level OpenAI key, fallback to server-level environment key."""
    user_settings = UserSettings.for_user(user)
    if user_settings and user_settings.openai_api_key:
        return user_settings.openai_api_key
    return django_settings.OPENAI_API_KEY


class UserImportedObject(models.Model):
    """Mapping between users and imported objects for safe, user-scoped cleanup."""
    user = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="imported_objects")
    game_object = models.ForeignKey("compendium.GameObject", on_delete=models.CASCADE, related_name="imported_by_users")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "game_object"], name="unique_user_imported_object"),
        ]

    def __str__(self):
        return f"{self.user.username} imported {self.game_object_id}"
