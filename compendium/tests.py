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
        </compendium>
        """
        self.xml_path.write_text(xml.strip(), encoding="utf-8")

    def test_import_is_idempotent_and_updates_existing_rows(self):
        self._write_xml("Sneaky creature")
        call_command("import_fightclub_xml", file=str(self.xml_path), system="dnd5e")

        self.assertEqual(GameObject.objects.count(), 3)
        goblin = GameObject.objects.get(name="Goblin")
        first_external_id = goblin.external_id
        self.assertTrue(first_external_id)

        self._write_xml("Updated creature text")
        call_command("import_fightclub_xml", file=str(self.xml_path), system="dnd5e")

        self.assertEqual(GameObject.objects.count(), 3)
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
