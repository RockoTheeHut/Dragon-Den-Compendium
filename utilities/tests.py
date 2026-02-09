from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compendium.models import GameObject


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

    def test_random_item_picker_history_is_limited_to_last_two_items(self):
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

        with patch("utilities.views.random.randint", side_effect=[0, 1, 2]):
            self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")
            self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")
            response = self.client.post(reverse("utilities:random_item_pick"), HTTP_HX_REQUEST="true")

        self.assertContains(response, "Lantern of Tides")
        self.assertContains(response, "Charm of Ember")
        history_html = response.content.decode().split('<div id="random-item-history-region"', 1)[1]
        self.assertNotIn("Mask of Echoes", history_html)
