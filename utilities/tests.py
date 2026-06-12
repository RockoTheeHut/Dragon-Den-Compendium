from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from compendium.models import GameObject
from core.models import UserSettings
from games.models import Game, GameObjectInstance


class DiceToolTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="roller", password="pw12345!")

    def test_dice_modal_requires_login(self):
        response = self.client.get(reverse("utilities:dice_modal"))
        self.assertEqual(response.status_code, 302)

    def test_dice_modal_loads_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("utilities:dice_modal"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Roll Dice")

    def test_roll_tool_returns_rolls_and_total(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("utilities:dice_roll_tool"),
            data={"roll_plan": '[{"quantity":3,"sides":6},{"quantity":2,"sides":100}]'},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total:")
        self.assertContains(response, "3d6")
        self.assertContains(response, "2d100")

    def test_roll_tool_clusters_same_die_type_entries(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("utilities:dice_roll_tool"),
            data={"roll_plan": '[{"quantity":2,"sides":6},{"quantity":4,"sides":6}]'},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "6d6")

    def test_roll_tool_rejects_unsupported_die_type(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("utilities:dice_roll_tool"), data={"roll_plan": '[{"quantity":2,"sides":21}]'})
        self.assertEqual(response.status_code, 400)

    def test_roll_tool_rejects_empty_roll_plan(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("utilities:dice_roll_tool"), data={"roll_plan": "[]"})
        self.assertEqual(response.status_code, 400)


class RandomItemPickerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="picker", password="pw12345!")

    def test_random_item_modal_requires_login(self):
        response = self.client.get(reverse("utilities:random_item_modal"))
        self.assertEqual(response.status_code, 302)

    def test_random_item_modal_loads_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("utilities:random_item_modal"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pick Random Item")
        self.assertContains(response, "Any type")

    def test_random_item_picker_returns_item_link(self):
        self.client.force_login(self.user)
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Amulet of Mist",
            source=GameObject.SourceType.CUSTOM,
        )

        response = self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Random Pick:")
        self.assertContains(response, "Amulet of Mist")

    def test_random_item_picker_can_pick_any_type(self):
        self.client.force_login(self.user)
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="Clockwork Golem",
            source=GameObject.SourceType.CUSTOM,
        )

        response = self.client.post(
            reverse("utilities:random_item_pick"),
            data={"object_type": ""},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clockwork Golem")

    def test_random_item_picker_filters_selected_type(self):
        self.client.force_login(self.user)
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Ring of Echoes",
            source=GameObject.SourceType.CUSTOM,
        )
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="River Drake",
            source=GameObject.SourceType.CUSTOM,
        )

        response = self.client.post(
            reverse("utilities:random_item_pick"),
            data={"object_type": GameObject.ObjectType.MONSTER},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "River Drake")
        self.assertNotContains(response, "Ring of Echoes")

    def test_random_item_picker_rejects_invalid_type(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("utilities:random_item_pick"),
            data={"object_type": "not-a-real-type"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)

    def test_random_item_picker_empty_state(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("utilities:random_item_pick"),
            data={"object_type": ""},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No objects found in the compendium yet.")

    def test_random_item_picker_shows_recent_history(self):
        self.client.force_login(self.user)
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Blade of Dawn",
            source=GameObject.SourceType.CUSTOM,
        )
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Cloak of Fog",
            source=GameObject.SourceType.CUSTOM,
        )

        with patch("utilities.views.random.randint", side_effect=[0, 1]):
            first_response = self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")
            second_response = self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")

        self.assertNotContains(first_response, "Recent Picks:")
        self.assertNotContains(first_response, "Cloak of Fog")
        self.assertContains(second_response, "Recent Picks:")
        self.assertContains(second_response, "Blade of Dawn")
        second_history_html = second_response.content.decode().split('<div id="random-item-history-region"', 1)[1]
        self.assertNotIn("Cloak of Fog", second_history_html)

    def test_random_item_picker_history_is_limited_to_last_three_items(self):
        self.client.force_login(self.user)
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Charm of Ember",
            source=GameObject.SourceType.CUSTOM,
        )
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Lantern of Tides",
            source=GameObject.SourceType.CUSTOM,
        )
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Mask of Echoes",
            source=GameObject.SourceType.CUSTOM,
        )
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Orb of Gale",
            source=GameObject.SourceType.CUSTOM,
        )

        with patch("utilities.views.random.randint", side_effect=[0, 1, 2, 3]):
            self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")
            self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")
            self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")
            response = self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")

        self.assertContains(response, "Mask of Echoes")
        self.assertContains(response, "Lantern of Tides")
        self.assertContains(response, "Charm of Ember")
        history_html = response.content.decode().split('<div id="random-item-history-region"', 1)[1]
        self.assertNotIn("Orb of Gale", history_html)


class MagicItemSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="mage", password="pw12345!")
        self.client.force_login(self.user)

    @override_settings(OPENAI_API_KEY="", OPENAI_DEFAULT_MODEL="gpt-5-mini")
    def test_magic_item_generator_ready_with_user_api_key(self):
        UserSettings.objects.create(user=self.user, openai_api_key="sk-user-key")

        response = self.client.get(reverse("utilities:magic_item"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "OpenAI is not configured for your account")
        self.assertNotContains(response, '<button class="button" type="submit" disabled>Generate</button>', html=False)

    @override_settings(OPENAI_API_KEY="", OPENAI_DEFAULT_MODEL="gpt-5-mini")
    def test_magic_item_generator_not_ready_without_any_api_key(self):
        response = self.client.get(reverse("utilities:magic_item"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OpenAI is not configured for your account")
        self.assertContains(response, '<button class="button" type="submit" disabled>Generate</button>', html=False)

    def test_magic_item_generator_game_picker_only_shows_users_games(self):
        owned_game = Game.objects.create(title="Owned Game", created_by=self.user)
        other_user = User.objects.create_user(username="other-mage", password="pw12345!")
        other_game = Game.objects.create(title="Other Game", created_by=other_user)

        response = self.client.get(reverse("utilities:magic_item"))

        self.assertEqual(response.status_code, 200)
        game_queryset = response.context["save_game_form"].fields["game"].queryset
        self.assertIn(owned_game, game_queryset)
        self.assertNotIn(other_game, game_queryset)

    def test_save_magic_item_global_creates_custom_item_and_redirects(self):
        response = self.client.post(
            reverse("utilities:save_magic_item_global"),
            data={
                "generated_payload": (
                    '{"name":"Ember Coil","description":"A warm coil of brass.",'
                    '"mechanics":"Sheds dim light.","suggested_tags":["fire","wondrous"]}'
                ),
            },
        )

        item = GameObject.objects.get(name="Ember Coil")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("compendium:object_detail", args=[item.pk]))
        self.assertEqual(item.source, GameObject.SourceType.CUSTOM)
        self.assertEqual(item.object_type, GameObject.ObjectType.ITEM)
        self.assertEqual(item.created_by, self.user)
        self.assertEqual(item.description, "A warm coil of brass.")
        self.assertEqual(item.data.get("mechanics"), "Sheds dim light.")
        self.assertEqual(
            sorted(item.tags.values_list("name", flat=True)),
            ["fire", "wondrous"],
        )

    def test_save_magic_item_global_rejects_malformed_json(self):
        response = self.client.post(
            reverse("utilities:save_magic_item_global"),
            data={"generated_payload": "{not valid json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(GameObject.objects.count(), 0)

    @override_settings(OPENAI_API_KEY="sk-test-env-key", OPENAI_DEFAULT_MODEL="gpt-5-mini")
    def test_magic_item_generator_post_stores_payload_and_redirects(self):
        generated_payload = {
            "name": "Cloak of Whispers",
            "description": "Woven from twilight.",
            "mechanics": "Advantage on Stealth checks.",
            "suggested_tags": ["stealth"],
        }

        with patch("utilities.views._generate_magic_item", return_value=generated_payload) as mock_generate:
            response = self.client.post(
                reverse("utilities:magic_item"),
                data={
                    "item_type": "Cloak",
                    "rarity": "Rare",
                    "theme": "Shadow",
                    "constraints": "",
                    "more_detail": "",
                    "model": "gpt-5-mini",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("utilities:magic_item"))
        mock_generate.assert_called_once()
        self.assertEqual(self.client.session.get("magic_item_generated_payload"), generated_payload)
        # No paid generation is persisted as a compendium object until the user saves it.
        self.assertFalse(GameObject.objects.filter(name="Cloak of Whispers").exists())

    @override_settings(OPENAI_API_KEY="sk-test-env-key", OPENAI_DEFAULT_MODEL="gpt-5-mini")
    def test_magic_item_generator_get_renders_session_payload(self):
        session = self.client.session
        session["magic_item_generated_payload"] = {
            "name": "Cloak of Whispers",
            "description": "Woven from twilight.",
            "mechanics": "Advantage on Stealth checks.",
            "suggested_tags": ["stealth"],
        }
        session.save()

        response = self.client.get(reverse("utilities:magic_item"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cloak of Whispers")
        self.assertContains(response, "Woven from twilight.")
        self.assertContains(response, "Advantage on Stealth checks.")
        self.assertContains(response, "stealth")

    def test_save_magic_item_to_game_rejects_other_users_game(self):
        other_user = User.objects.create_user(username="other-owner", password="pw12345!")
        other_game = Game.objects.create(title="Other Game", created_by=other_user)

        response = self.client.post(
            reverse("utilities:save_magic_item_game"),
            data={
                "generated_payload": '{"name":"Frost Key","description":"Cold.","mechanics":"Unlocks ice.","suggested_tags":[]}',
                "game": other_game.pk,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(GameObject.objects.filter(name="Frost Key").exists())
        self.assertFalse(GameObjectInstance.objects.filter(game=other_game, name="Frost Key").exists())
