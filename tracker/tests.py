from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compendium.models import GameObject
from games.models import Game, GameObjectInstance

from .models import StatusEffect, TurnTrackerEntry


class TurnTrackerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dm", password="pw12345!")
        self.client.force_login(self.user)

    def test_player_entry_does_not_persist_hp_or_items(self):
        entry = TurnTrackerEntry.objects.create(
            user=self.user,
            name="Aria",
            entry_type=TurnTrackerEntry.EntryType.PLAYER,
            hp_current=12,
            hp_max=20,
            items_text="Sword",
        )

        self.assertIsNone(entry.hp_current)
        self.assertIsNone(entry.hp_max)
        self.assertEqual(entry.items_text, "")

    def test_add_from_compendium_creates_snapshot_copy(self):
        monster = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="Goblin",
            source=GameObject.SourceType.CUSTOM,
            data={"hp": 7, "ac": 15},
        )

        response = self.client.post(
            reverse("tracker:add_from_compendium"),
            data={
                "source": monster.pk,
                "entry_type": TurnTrackerEntry.EntryType.ENEMY,
                "name": "",
                "initiative": 12,
                "is_active": "on",
                "notes": "Ambush",
            },
        )

        self.assertEqual(response.status_code, 200)
        entry = TurnTrackerEntry.objects.get(user=self.user, name="Goblin")
        self.assertEqual(entry.source_kind, TurnTrackerEntry.SourceKind.COMPENDIUM_MONSTER)
        self.assertEqual(entry.source_snapshot.get("hp"), 7)
        self.assertEqual(entry.source_snapshot.get("_source_object_id"), monster.pk)

        monster.data = {"hp": 30}
        monster.save(update_fields=["data"])
        entry.refresh_from_db()
        self.assertEqual(entry.source_snapshot.get("hp"), 7)

    def test_compendium_tracker_entry_name_opens_monster_modal(self):
        monster = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="Dire Wolf",
            source=GameObject.SourceType.CUSTOM,
            data={"hp": 37},
        )

        response = self.client.post(
            reverse("tracker:add_from_compendium"),
            data={
                "source": monster.pk,
                "entry_type": TurnTrackerEntry.EntryType.ENEMY,
                "name": "",
                "initiative": 12,
                "is_active": "on",
                "notes": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        entry = TurnTrackerEntry.objects.get(user=self.user, name="Dire Wolf")
        self.assertContains(response, f"openTrackerMonsterModal({entry.id})")
        self.assertContains(response, "class=\"tracker-entry-trigger\"")

    def test_monster_modal_renders_stat_block_and_attacks(self):
        monster = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="Skeleton Archer",
            source=GameObject.SourceType.CUSTOM,
            data={
                "size": "Medium",
                "type": "undead",
                "alignment": "lawful evil",
                "ac": "13 (armor scraps)",
                "hp": "13 (2d8+4)",
                "speed": "30 ft.",
                "str": "10",
                "dex": "14",
                "con": "15",
                "int": "6",
                "wis": "8",
                "cha": "5",
                "cr": "1/4",
                "action": [
                    {"name": "Shortsword", "text": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target."},
                    {"name": "Shortbow", "text": "Ranged Weapon Attack: +4 to hit, range 80/320 ft., one target."},
                ],
            },
        )
        self.client.post(
            reverse("tracker:add_from_compendium"),
            data={
                "source": monster.pk,
                "entry_type": TurnTrackerEntry.EntryType.ENEMY,
                "name": "",
                "initiative": 10,
                "is_active": "on",
                "notes": "",
            },
            HTTP_HX_REQUEST="true",
        )
        entry = TurnTrackerEntry.objects.get(user=self.user, name="Skeleton Archer")

        response = self.client.get(
            reverse("tracker:entry_monster_modal", args=[entry.id]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Armor Class:")
        self.assertContains(response, "Hit Points:")
        self.assertContains(response, "Attacks")
        self.assertContains(response, "Shortsword")
        self.assertContains(response, "Shortbow")

    def test_advance_turn_decrements_only_running_status_effects(self):
        first = TurnTrackerEntry.objects.create(
            user=self.user,
            name="Fighter",
            entry_type=TurnTrackerEntry.EntryType.PLAYER,
            is_active=True,
            is_current=True,
            sort_order=0,
        )
        second = TurnTrackerEntry.objects.create(
            user=self.user,
            name="Orc",
            entry_type=TurnTrackerEntry.EntryType.ENEMY,
            is_active=True,
            sort_order=1,
        )

        running = StatusEffect.objects.create(
            entry=first,
            name="Bless",
            duration_rounds=3,
            remaining_rounds=3,
            is_running=True,
        )
        paused = StatusEffect.objects.create(
            entry=second,
            name="Poisoned",
            duration_rounds=4,
            remaining_rounds=4,
            is_running=False,
        )

        self.client.post(reverse("tracker:advance_turn"))

        first.refresh_from_db()
        second.refresh_from_db()
        running.refresh_from_db()
        paused.refresh_from_db()

        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)
        self.assertEqual(running.remaining_rounds, 2)
        self.assertEqual(paused.remaining_rounds, 4)

    def test_reorder_entries_updates_sort_order(self):
        a = TurnTrackerEntry.objects.create(
            user=self.user,
            name="A",
            entry_type=TurnTrackerEntry.EntryType.PLAYER,
            sort_order=0,
        )
        b = TurnTrackerEntry.objects.create(
            user=self.user,
            name="B",
            entry_type=TurnTrackerEntry.EntryType.NPC,
            sort_order=1,
        )

        self.client.post(reverse("tracker:reorder"), data={"order": f"{b.id},{a.id}"})

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.sort_order, 0)
        self.assertEqual(a.sort_order, 1)

    def test_add_from_game_instance_accepts_any_instance_type(self):
        base_object = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Potion of Healing",
            source=GameObject.SourceType.CUSTOM,
            data={"healing": "2d4+2"},
        )
        game = Game.objects.create(title="Campaign", created_by=self.user)
        instance = GameObjectInstance.objects.create(
            game=game,
            base_object=base_object,
            name=base_object.name,
            object_type=base_object.object_type,
            description="",
            data=base_object.data,
        )

        response = self.client.post(
            reverse("tracker:add_from_instance"),
            data={
                "source": instance.pk,
                "entry_type": TurnTrackerEntry.EntryType.NPC,
                "name": "Alchemist",
                "initiative": "",
                "is_active": "on",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        entry = TurnTrackerEntry.objects.get(user=self.user, name="Alchemist")
        self.assertEqual(entry.source_kind, TurnTrackerEntry.SourceKind.GAME_INSTANCE)
        self.assertEqual(entry.source_snapshot.get("healing"), "2d4+2")

    def test_add_from_game_instance_rejects_other_users_instance(self):
        other_user = User.objects.create_user(username="other-dm", password="pw12345!")
        base_object = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Hidden Relic",
            source=GameObject.SourceType.CUSTOM,
            data={"value": 99},
        )
        other_game = Game.objects.create(title="Other Table", created_by=other_user)
        other_instance = GameObjectInstance.objects.create(
            game=other_game,
            base_object=base_object,
            name=base_object.name,
            object_type=base_object.object_type,
            description="",
            data=base_object.data,
        )

        response = self.client.post(
            reverse("tracker:add_from_instance"),
            data={
                "source": other_instance.pk,
                "entry_type": TurnTrackerEntry.EntryType.NPC,
                "name": "Should Fail",
                "initiative": "",
                "is_active": "on",
                "notes": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(TurnTrackerEntry.objects.filter(user=self.user, name="Should Fail").exists())

    def test_dashboard_is_list_first_and_has_add_entry_button(self):
        response = self.client.get(reverse("tracker:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add Entry")
        self.assertContains(response, "Initiative")
        self.assertContains(response, "Loading entry form...")
        self.assertNotContains(response, "Create NPC / Enemy From Compendium Monster")

    def test_add_entry_modal_endpoint_returns_form_content(self):
        response = self.client.get(reverse("tracker:add_entry_modal"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Monster")
        self.assertContains(response, "Add From Monster")

    def test_edit_entry_modal_endpoint_returns_modal_content(self):
        entry = TurnTrackerEntry.objects.create(
            user=self.user,
            name="Scout",
            entry_type=TurnTrackerEntry.EntryType.NPC,
            sort_order=0,
        )
        response = self.client.get(reverse("tracker:edit_entry_modal", args=[entry.id]), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save Changes")
        self.assertContains(response, "Scout")

    def test_quick_update_entry_updates_initiative(self):
        entry = TurnTrackerEntry.objects.create(
            user=self.user,
            name="Rogue",
            entry_type=TurnTrackerEntry.EntryType.PLAYER,
            initiative=12,
            sort_order=0,
        )

        response = self.client.post(
            reverse("tracker:quick_update_entry", args=[entry.id]),
            data={"initiative": "19"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.initiative, 19)

    def test_previous_turn_cycles_backwards(self):
        first = TurnTrackerEntry.objects.create(
            user=self.user,
            name="Alpha",
            entry_type=TurnTrackerEntry.EntryType.PLAYER,
            is_active=True,
            sort_order=0,
        )
        second = TurnTrackerEntry.objects.create(
            user=self.user,
            name="Beta",
            entry_type=TurnTrackerEntry.EntryType.ENEMY,
            is_active=True,
            is_current=True,
            sort_order=1,
        )

        response = self.client.post(reverse("tracker:previous_turn"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_current)
        self.assertFalse(second.is_current)
