from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compendium.models import GameObject

from .models import Encounter, Game, GameObjectInstance, GamePlayer


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
        self.player = GamePlayer.objects.create(
            game=self.game,
            name="Owner PC",
            notes="",
            ac=15,
            strength=14,
            dexterity=12,
            constitution=13,
            intelligence=10,
            wisdom=11,
            charisma=9,
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

    def test_non_owner_cannot_edit_owner_player(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("games:edit_player", args=[self.game.pk, self.player.pk]),
            data={"name": "Intrusion", "notes": "", "ac": "12", "strength": "10"},
        )
        self.assertEqual(response.status_code, 403)

    def test_non_owner_cannot_delete_owner_player(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("games:delete_player", args=[self.game.pk, self.player.pk]))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_create_player(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("games:create_player", args=[self.game.pk]),
            data={
                "name": "New PC",
                "notes": "Frontliner",
                "ac": "17",
                "strength": "16",
                "dexterity": "14",
                "constitution": "15",
                "intelligence": "12",
                "wisdom": "13",
                "charisma": "11",
            },
        )
        self.assertEqual(response.status_code, 302)
        player = GamePlayer.objects.get(game=self.game, name="New PC")
        self.assertEqual(player.ac, 17)
        self.assertEqual(player.strength, 16)
        self.assertEqual(player.dexterity, 14)
        self.assertEqual(player.constitution, 15)
        self.assertEqual(player.intelligence, 12)
        self.assertEqual(player.wisdom, 13)
        self.assertEqual(player.charisma, 11)

    def test_game_list_only_shows_user_games_for_non_staff(self):
        Game.objects.create(title="Other Campaign", created_by=self.other)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("games:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Private Campaign")
        self.assertNotContains(response, "Other Campaign")

    def test_owner_can_create_encounter_and_open_tracker(self):
        self.client.force_login(self.owner)
        create_response = self.client.post(
            reverse("games:create_encounter", args=[self.game.pk]),
            data={"title": "Goblin Ambush"},
        )
        self.assertEqual(create_response.status_code, 302)
        encounter = Encounter.objects.get(game=self.game, title="Goblin Ambush")

        tracker_response = self.client.get(
            reverse("games:open_encounter_tracker", args=[self.game.pk, encounter.pk]),
            follow=True,
        )
        self.assertEqual(tracker_response.status_code, 200)
        self.assertContains(tracker_response, "Turn Tracker: Goblin Ambush")

    def test_non_owner_cannot_open_owner_encounter_tracker(self):
        encounter = Encounter.objects.create(game=self.game, title="Owner Encounter")
        self.client.force_login(self.other)
        response = self.client.get(reverse("games:open_encounter_tracker", args=[self.game.pk, encounter.pk]))
        self.assertEqual(response.status_code, 403)

    def test_games_list_redirects_to_last_open_game(self):
        self.client.force_login(self.owner)
        self.client.get(reverse("games:detail", args=[self.game.pk]))

        response = self.client.get(reverse("games:list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("games:detail", args=[self.game.pk]))

    def test_games_list_all_parameter_bypasses_last_open_redirect(self):
        self.client.force_login(self.owner)
        self.client.get(reverse("games:detail", args=[self.game.pk]))

        response = self.client.get(f"{reverse('games:list')}?all=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Existing Games")

    def test_owner_can_delete_game(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("games:delete", args=[self.game.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("games:list"))
        self.assertFalse(Game.objects.filter(pk=self.game.pk).exists())

    def test_owner_can_delete_encounter(self):
        encounter = Encounter.objects.create(game=self.game, title="Doomed Encounter")
        self.client.force_login(self.owner)

        response = self.client.post(reverse("games:delete_encounter", args=[self.game.pk, encounter.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("games:detail", args=[self.game.pk]))
        self.assertFalse(Encounter.objects.filter(pk=encounter.pk).exists())

    def test_owner_can_edit_player(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("games:edit_player", args=[self.game.pk, self.player.pk]),
            data={
                "name": "Renamed PC",
                "notes": "Now a backliner",
                "ac": "18",
                "strength": "8",
                "dexterity": "16",
                "constitution": "12",
                "intelligence": "17",
                "wisdom": "14",
                "charisma": "10",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("games:detail", args=[self.game.pk]))
        self.player.refresh_from_db()
        self.assertEqual(self.player.name, "Renamed PC")
        self.assertEqual(self.player.notes, "Now a backliner")
        self.assertEqual(self.player.ac, 18)
        self.assertEqual(self.player.strength, 8)
        self.assertEqual(self.player.intelligence, 17)

    def test_owner_can_delete_player(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("games:delete_player", args=[self.game.pk, self.player.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("games:detail", args=[self.game.pk]))
        self.assertFalse(GamePlayer.objects.filter(pk=self.player.pk).exists())

    def test_edit_player_modal_returns_form_for_owner(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("games:edit_player_modal", args=[self.game.pk, self.player.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner PC")
        self.assertContains(response, 'name="name"', html=False)
        self.assertContains(response, 'name="ac"', html=False)
