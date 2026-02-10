from django.conf import settings as django_settings
from django.db import models


class UserSettings(models.Model):
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
        if not user or not user.is_authenticated:
            return None
        settings_obj, _created = cls.objects.get_or_create(user=user)
        return settings_obj


def get_effective_openai_api_key(user):
    settings_obj = UserSettings.for_user(user)
    if settings_obj and settings_obj.openai_api_key:
        return settings_obj.openai_api_key
    return django_settings.OPENAI_API_KEY


class UserImportedObject(models.Model):
    user = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="imported_objects")
    game_object = models.ForeignKey("compendium.GameObject", on_delete=models.CASCADE, related_name="imported_by_users")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "game_object"], name="unique_user_imported_object"),
        ]

    def __str__(self):
        return f"{self.user.username} imported {self.game_object_id}"
