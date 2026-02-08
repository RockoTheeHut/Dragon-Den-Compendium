from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from games.models import Game

from .models import TurnEntry


class TurnTrackerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dm", password="pw")
        self.game = Game.objects.create(title="Campaign", created_by=self.user)

    def test_only_one_current_turn_entry_allowed_per_game(self):
        TurnEntry.objects.create(
            game=self.game,
            entity_type=TurnEntry.EntityType.CUSTOM,
            display_name="A",
            is_current=True,
            sort_order=0,
        )

        with self.assertRaises(IntegrityError):
            TurnEntry.objects.create(
                game=self.game,
                entity_type=TurnEntry.EntityType.CUSTOM,
                display_name="B",
                is_current=True,
                sort_order=1,
            )

    def test_next_and_previous_turn_wrap(self):
        first = TurnEntry.objects.create(
            game=self.game,
            entity_type=TurnEntry.EntityType.CUSTOM,
            display_name="A",
            is_current=True,
            is_active=True,
            sort_order=0,
        )
        second = TurnEntry.objects.create(
            game=self.game,
            entity_type=TurnEntry.EntityType.CUSTOM,
            display_name="B",
            is_current=False,
            is_active=True,
            sort_order=1,
        )

        self.client.force_login(self.user)
        self.client.post(reverse("tracker:next_turn", args=[self.game.pk]))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)

        self.client.post(reverse("tracker:previous_turn", args=[self.game.pk]))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_current)
        self.assertFalse(second.is_current)
