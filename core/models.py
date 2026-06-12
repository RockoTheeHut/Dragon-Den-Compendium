import base64
import hashlib
import logging

from django.conf import settings as django_settings
from django.db import models
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class UserSettings(models.Model):
    """Per-user configuration values that should override server defaults."""
    user = models.OneToOneField(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="settings")
    openai_api_key = models.CharField(max_length=1024, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "User settings"

    def __str__(self):
        return f"Settings for {self.user.username}"

    @staticmethod
    def _cipher():
        key_material = getattr(django_settings, "FIELD_ENCRYPTION_KEY", "") or django_settings.SECRET_KEY
        digest = hashlib.sha256(key_material.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    @classmethod
    def encrypt_api_key(cls, value):
        cleaned = (value or "").strip()
        if not cleaned:
            return ""
        token = cls._cipher().encrypt(cleaned.encode("utf-8")).decode("utf-8")
        return f"enc:{token}"

    @classmethod
    def decrypt_api_key(cls, value):
        cleaned = (value or "").strip()
        if not cleaned:
            return ""
        if not cleaned.startswith("enc:"):
            return cleaned
        try:
            return cls._cipher().decrypt(cleaned[4:].encode("utf-8")).decode("utf-8")
        except InvalidToken:
            logger.warning(
                "Could not decrypt a stored API key (was SECRET_KEY/FIELD_ENCRYPTION_KEY rotated?); treating it as unset."
            )
            return ""

    def get_openai_api_key(self):
        return self.decrypt_api_key(self.openai_api_key)

    def set_openai_api_key(self, value):
        self.openai_api_key = self.encrypt_api_key(value)

    @classmethod
    def for_user(cls, user, create=True):
        """Return user settings; optionally create a default row if missing."""
        if not user or not user.is_authenticated:
            return None
        if create:
            user_settings, _created = cls.objects.get_or_create(user=user)
            return user_settings
        return cls.objects.filter(user=user).first()


def get_effective_openai_api_key(user):
    """Prefer user-level OpenAI key, fallback to server-level environment key."""
    user_settings = UserSettings.for_user(user, create=False)
    if user_settings:
        decrypted = user_settings.get_openai_api_key()
        if decrypted:
            return decrypted
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


class CompendiumImportJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="compendium_import_jobs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    system = models.CharField(max_length=64)
    use_server_xml = models.BooleanField(default=False)
    import_path = models.CharField(max_length=1024)
    upload_filename = models.CharField(max_length=255, blank=True, default="")
    result_message = models.TextField(blank=True, default="")
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Import job {self.pk} ({self.status}) for {self.user.username}"
