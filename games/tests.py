from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compendium.models import GameObject

from .models import Game, GameObjectInstance


class GameObjectInstanceIsolationTests(TestCase):
    def test_game_copy_remains_unchanged_when_global_object_changes(self):
        user = User.objects.create_user(username="dm", password="pw")
        game = Game.objects.create(title="Campaign", created_by=user)
        global_object = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="Orc",
            source=GameObject.SourceType.CUSTOM,
            data={"hp": 15},
        )

        copy = GameObjectInstance.objects.create(
            game=game,
            base_object=global_object,
            name=global_object.name,
            object_type=global_object.object_type,
            description=global_object.description,
            data=global_object.data,
        )

        global_object.data = {"hp": 30}
        global_object.save(update_fields=["data"])

        copy.refresh_from_db()
        self.assertEqual(copy.data["hp"], 15)


class GameAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pw12345!")
        self.other = User.objects.create_user(username="other", password="pw12345!")
        self.game = Game.objects.create(title="Private Campaign", created_by=self.owner)
        self.base = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Owner Item",
            source=GameObject.SourceType.CUSTOM,
            data={"value": 1},
        )
        self.instance = GameObjectInstance.objects.create(
            game=self.game,
            base_object=self.base,
            name=self.base.name,
            object_type=self.base.object_type,
            description="",
            data=self.base.data,
        )

    def test_non_owner_cannot_view_owner_game_detail(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("games:detail", args=[self.game.pk]))
        self.assertEqual(response.status_code, 403)

    def test_non_owner_cannot_edit_owner_instance(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("games:edit_instance", args=[self.game.pk, self.instance.pk]),
            data={"name": "Intrusion", "description": "", "data_text": "{}"},
        )
        self.assertEqual(response.status_code, 403)

    def test_non_owner_cannot_remove_owner_instance(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("games:remove_instance", args=[self.game.pk, self.instance.pk]))
        self.assertEqual(response.status_code, 403)

    def test_game_list_only_shows_user_games_for_non_staff(self):
        Game.objects.create(title="Other Campaign", created_by=self.other)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("games:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Private Campaign")
        self.assertNotContains(response, "Other Campaign")
