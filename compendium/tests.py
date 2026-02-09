import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .models import Favorite, GameObject, Tag


class CompendiumModelTests(TestCase):
    def test_tag_color_must_be_hex(self):
        tag = Tag(name="bad", color="blue", system="dnd5e")
        with self.assertRaises(ValidationError):
            tag.full_clean()

    def test_favorite_is_unique_per_user_and_object(self):
        user = User.objects.create_user(username="tester", password="pw")
        obj = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="Goblin",
            source=GameObject.SourceType.CUSTOM,
        )

        Favorite.objects.create(user=user, game_object=obj)
        with self.assertRaises(IntegrityError):
            Favorite.objects.create(user=user, game_object=obj)


class FightClubImportTests(TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.xml_path = self.temp_dir / "sample.xml"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_xml(self, description_text):
        xml = f"""
        <compendium>
          <monster>
            <name>Goblin</name>
            <text>{description_text}</text>
          </monster>
          <spell>
            <name>Magic Missile</name>
            <text>Arcane darts</text>
          </spell>
          <item>
            <name>Health Potion</name>
            <text>Restores HP</text>
          </item>
          <class>
            <name>Wizard</name>
            <hd>6</hd>
            <proficiency>Intelligence, Wisdom</proficiency>
            <autolevel level="1">
              <feature>
                <name>Spellcasting</name>
                <text>Arcane casting focus.</text>
              </feature>
              <feature optional="YES">
                <name>Arcane Tradition: School of Evocation</name>
                <text>Subclass choice.</text>
              </feature>
              <feature optional="YES">
                <name>Sculpt Spells (School of Evocation)</name>
                <text>You can create pockets of safety.</text>
              </feature>
            </autolevel>
          </class>
          <race>
            <name>Elf</name>
            <size>M</size>
            <speed>30</speed>
            <trait>
              <name>Keen Senses</name>
              <text>You have proficiency in Perception.</text>
            </trait>
          </race>
          <feat>
            <name>Alert</name>
            <prerequisite></prerequisite>
            <text>You gain +5 to initiative.</text>
          </feat>
          <background>
            <name>Acolyte</name>
            <proficiency>Insight, Religion</proficiency>
            <trait>
              <name>Shelter of the Faithful</name>
              <text>Those who share your religion support you.</text>
            </trait>
          </background>
        </compendium>
        """
        self.xml_path.write_text(xml.strip(), encoding="utf-8")

    def test_import_is_idempotent_and_updates_existing_rows(self):
        self._write_xml("Sneaky creature")
        call_command("import_fightclub_xml", file=str(self.xml_path), system="dnd5e")

        self.assertEqual(GameObject.objects.count(), 7)
        goblin = GameObject.objects.get(name="Goblin")
        first_external_id = goblin.external_id
        self.assertTrue(first_external_id)
        wizard = GameObject.objects.get(name="Wizard")
        self.assertEqual(wizard.object_type, GameObject.ObjectType.CLASS)
        self.assertEqual(GameObject.objects.get(name="Elf").object_type, GameObject.ObjectType.RACE)
        self.assertEqual(GameObject.objects.get(name="Alert").object_type, GameObject.ObjectType.FEAT)
        self.assertEqual(GameObject.objects.get(name="Acolyte").object_type, GameObject.ObjectType.BACKGROUND)

        self._write_xml("Updated creature text")
        call_command("import_fightclub_xml", file=str(self.xml_path), system="dnd5e")

        self.assertEqual(GameObject.objects.count(), 7)
        goblin.refresh_from_db()
        self.assertEqual(goblin.description, "Updated creature text")
        self.assertEqual(goblin.external_id, first_external_id)


class CompendiumPaginationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="viewer", password="pw12345!")
        GameObject.objects.bulk_create(
            [
                GameObject(
                    system="dnd5e",
                    object_type=GameObject.ObjectType.ITEM,
                    name=f"Item {index:03d}",
                    source=GameObject.SourceType.CUSTOM,
                )
                for index in range(205)
            ]
        )

    def test_first_page_loads_100_objects(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("compendium:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["objects"]), 100)
        self.assertTrue(response.context["has_next"])
        self.assertEqual(response.context["next_page_number"], 2)

    def test_append_request_returns_next_100_objects(self):
        self.client.force_login(self.user)
        response = self.client.get(
            f"{reverse('compendium:list')}?page=2&append=1",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["objects"]), 100)
        self.assertTrue(response.context["has_next"])
        self.assertEqual(response.context["next_page_number"], 3)

    def test_preview_modal_endpoint_returns_partial(self):
        self.client.force_login(self.user)
        obj = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="Preview Goblin",
            source=GameObject.SourceType.CUSTOM,
            data={
                "ac": "15",
                "hp": "7 (2d6)",
                "speed": "30 ft.",
                "action": [{"name": "Scimitar", "text": "Melee Weapon Attack: +4 to hit."}],
            },
        )

        response = self.client.get(reverse("compendium:object_preview_modal", args=[obj.pk]), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview Goblin")
        self.assertContains(response, "Summary")
        self.assertContains(response, "Attacks")

    def test_class_preview_uses_ability_and_subclass_dropdowns(self):
        self.client.force_login(self.user)
        obj = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.CLASS,
            name="Preview Wizard",
            source=GameObject.SourceType.IMPORTED,
            data={
                "hd": "6",
                "autolevel": [
                    {
                        "_attributes": {"level": "1"},
                        "feature": [
                            {"name": "Spellcasting", "text": "You can cast wizard spells."},
                            {
                                "name": "Arcane Tradition: School of Evocation",
                                "text": "Choose evocation specialization.",
                                "_attributes": {"optional": "YES"},
                            },
                            {
                                "name": "Sculpt Spells (School of Evocation)",
                                "text": "Protect allies from your spells.",
                                "_attributes": {"optional": "YES"},
                            },
                        ],
                    }
                ],
            },
        )

        response = self.client.get(reverse("compendium:object_preview_modal", args=[obj.pk]), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class Abilities")
        self.assertContains(response, "Subclasses")
        self.assertContains(response, "School of Evocation")
        self.assertContains(response, "<details", html=False)
