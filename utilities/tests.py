from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


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
