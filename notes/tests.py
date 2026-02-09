from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import SCRATCHPAD_MAX_LENGTH, SHARED_NOTE_CONTENT_MAX_LENGTH, SharedNote
from .views import SCRATCHPAD_TITLE


class ScratchpadTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="a", password="pw12345!")
        self.user_b = User.objects.create_user(username="b", password="pw12345!")

    def test_modal_creates_private_scratchpad(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("notes:modal"))

        self.assertEqual(response.status_code, 200)
        scratchpad = SharedNote.objects.get(created_by=self.user_a, title=SCRATCHPAD_TITLE)
        self.assertEqual(scratchpad.visibility, SharedNote.Visibility.PRIVATE)

    def test_save_updates_same_scratchpad_record(self):
        self.client.force_login(self.user_a)
        self.client.get(reverse("notes:modal"))

        response = self.client.post(reverse("notes:save"), data={"content": "Session prep"})
        self.assertEqual(response.status_code, 302)

        notes = SharedNote.objects.filter(created_by=self.user_a, title=SCRATCHPAD_TITLE)
        self.assertEqual(notes.count(), 1)
        self.assertEqual(notes.first().content, "Session prep")

    def test_users_have_isolated_scratchpads(self):
        self.client.force_login(self.user_a)
        self.client.post(reverse("notes:save"), data={"content": "A only"})

        self.client.force_login(self.user_b)
        self.client.post(reverse("notes:save"), data={"content": "B only"})

        note_a = SharedNote.objects.get(created_by=self.user_a, title=SCRATCHPAD_TITLE)
        note_b = SharedNote.objects.get(created_by=self.user_b, title=SCRATCHPAD_TITLE)

        self.assertEqual(note_a.content, "A only")
        self.assertEqual(note_b.content, "B only")

    def test_clear_wipes_scratchpad_content(self):
        self.client.force_login(self.user_a)
        self.client.post(reverse("notes:save"), data={"content": "to be cleared"})

        response = self.client.post(reverse("notes:clear"))
        self.assertEqual(response.status_code, 302)

        scratchpad = SharedNote.objects.get(created_by=self.user_a, title=SCRATCHPAD_TITLE)
        self.assertEqual(scratchpad.content, "")

    def test_scratchpad_save_is_limited_to_configured_max_length(self):
        self.client.force_login(self.user_a)
        oversized = "x" * (SCRATCHPAD_MAX_LENGTH + 25)

        self.client.post(reverse("notes:save"), data={"content": oversized})

        scratchpad = SharedNote.objects.get(created_by=self.user_a, title=SCRATCHPAD_TITLE)
        self.assertEqual(len(scratchpad.content), SCRATCHPAD_MAX_LENGTH)

    def test_model_content_column_has_max_length(self):
        field = SharedNote._meta.get_field("content")
        self.assertEqual(field.max_length, SHARED_NOTE_CONTENT_MAX_LENGTH)
