from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import SharedNote


class SharedNoteTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="a", password="pw")
        self.user_b = User.objects.create_user(username="b", password="pw")

    def test_visibility_filtering(self):
        public_note = SharedNote.objects.create(
            title="Public",
            content="all",
            created_by=self.user_a,
            visibility=SharedNote.Visibility.PUBLIC,
        )
        private_a = SharedNote.objects.create(
            title="Private A",
            content="a",
            created_by=self.user_a,
            visibility=SharedNote.Visibility.PRIVATE,
        )
        private_b = SharedNote.objects.create(
            title="Private B",
            content="b",
            created_by=self.user_b,
            visibility=SharedNote.Visibility.PRIVATE,
        )

        visible_for_a = SharedNote.objects.visible_to(self.user_a)
        self.assertIn(public_note, visible_for_a)
        self.assertIn(private_a, visible_for_a)
        self.assertNotIn(private_b, visible_for_a)

    def test_only_creator_can_update(self):
        note = SharedNote.objects.create(
            title="Private",
            content="secret",
            created_by=self.user_a,
            visibility=SharedNote.Visibility.PRIVATE,
        )

        self.client.force_login(self.user_b)
        response = self.client.post(
            reverse("notes:update", args=[note.pk]),
            data={"title": "Hacked", "content": "x", "visibility": "public"},
        )

        self.assertEqual(response.status_code, 403)
        note.refresh_from_db()
        self.assertEqual(note.title, "Private")
