from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compendium.models import Favorite, GameObject
from games.models import Game


class HomeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="home-user", password="pw12345!")

    def test_home_context_contains_user_favorites(self):
        game_object = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Orb of Sparks",
            source=GameObject.SourceType.CUSTOM,
        )
        Favorite.objects.create(user=self.user, game_object=game_object)
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["favorite_objects"].count(), 1)
        self.assertContains(response, "Your Favorite Objects")
        self.assertContains(response, "Orb of Sparks")

    def test_home_shows_recent_games(self):
        Game.objects.create(
            title="Stormreach",
            created_by=self.user,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Recent Games")
        self.assertContains(response, "Stormreach")
