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

        self.assertEqual(
            GameObject.objects.filter(object_type=GameObject.ObjectType.CONDITION, system="dnd5e").count(),
            15,
        )
        self.assertEqual(GameObject.objects.count(), 22)
        goblin = GameObject.objects.get(name="Goblin")
        first_external_id = goblin.external_id
        self.assertTrue(first_external_id)
        poisoned = GameObject.objects.get(name="Poisoned", object_type=GameObject.ObjectType.CONDITION)
        self.assertEqual(poisoned.source, GameObject.SourceType.OFFICIAL)
        wizard = GameObject.objects.get(name="Wizard")
        self.assertEqual(wizard.object_type, GameObject.ObjectType.CLASS)
        self.assertEqual(GameObject.objects.get(name="Elf").object_type, GameObject.ObjectType.RACE)
        self.assertEqual(GameObject.objects.get(name="Alert").object_type, GameObject.ObjectType.FEAT)
        self.assertEqual(GameObject.objects.get(name="Acolyte").object_type, GameObject.ObjectType.BACKGROUND)

        self._write_xml("Updated creature text")
        call_command("import_fightclub_xml", file=str(self.xml_path), system="dnd5e")

        self.assertEqual(GameObject.objects.count(), 22)
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

    def test_condition_preview_renders_effect_sections(self):
        self.client.force_login(self.user)
        obj = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.CONDITION,
            name="Stunned",
            source=GameObject.SourceType.OFFICIAL,
            description="A stunned creature is incapacitated and cannot move.",
            data={
                "impact": "A stunned creature is incapacitated and cannot move.",
                "ends_when": "The effect causing stun ends.",
                "effects": [
                    "The creature cannot move.",
                    "It automatically fails Strength and Dexterity saving throws.",
                ],
            },
        )

        response = self.client.get(reverse("compendium:object_preview_modal", args=[obj.pk]), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Summary")
        self.assertContains(response, "Effects")
        self.assertContains(response, "Stunned")

    def test_object_detail_links_referenced_entries_to_preview_modal(self):
        self.client.force_login(self.user)
        spell = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.SPELL,
            name="Magic Missile",
            source=GameObject.SourceType.IMPORTED,
            data={"level": "1", "text": ["You create darts of force."]},
        )
        condition = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.CONDITION,
            name="Poisoned",
            source=GameObject.SourceType.OFFICIAL,
            description="A poisoned creature has disadvantage on attack rolls and ability checks.",
            data={"impact": "A poisoned creature has disadvantage on attack rolls and ability checks."},
        )
        class_obj = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.CLASS,
            name="Battle Mage",
            source=GameObject.SourceType.CUSTOM,
            description="Battle Mages are known for casting Magic Missile and leaving foes poisoned in close combat.",
            data={"hd": "8"},
        )

        response = self.client.get(reverse("compendium:object_detail", args=[class_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Magic Missile")
        self.assertContains(response, "poisoned")
        self.assertContains(response, f"openCompendiumPreviewModal({spell.pk})")
        self.assertContains(response, f"openCompendiumPreviewModal({condition.pk})")
        self.assertContains(response, "compendium-inline-ref")
        self.assertNotContains(response, "Linked Entries")
        self.assertNotContains(response, "Add To Game")


class CompendiumSortOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sorter", password="pw12345!")
        ordered_types = [
            GameObject.ObjectType.BACKGROUND,
            GameObject.ObjectType.SPELL,
            GameObject.ObjectType.ITEM,
            GameObject.ObjectType.FEAT,
            GameObject.ObjectType.CLASS,
            GameObject.ObjectType.MONSTER,
            GameObject.ObjectType.RACE,
        ]
        for object_type in ordered_types:
            GameObject.objects.create(
                system="dnd5e",
                object_type=object_type,
                name=f"{object_type.title()} Entry",
                source=GameObject.SourceType.CUSTOM,
            )

    def test_compendium_default_sort_uses_custom_type_priority(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("compendium:list"))
        self.assertEqual(response.status_code, 200)

        object_types = [obj.object_type for obj in response.context["objects"]]
        self.assertEqual(
            object_types,
            [
                GameObject.ObjectType.CLASS,
                GameObject.ObjectType.FEAT,
                GameObject.ObjectType.ITEM,
                GameObject.ObjectType.MONSTER,
                GameObject.ObjectType.SPELL,
                GameObject.ObjectType.RACE,
                GameObject.ObjectType.BACKGROUND,
            ],
        )


class CompendiumSearchPreviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="searcher", password="pw12345!")
        self.object = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.SPELL,
            name="Magic Missile",
            source=GameObject.SourceType.CUSTOM,
        )

    def test_search_preview_rows_open_modal(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("compendium:search_preview"),
            data={"q": "Magic"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "search-preview-open")
        self.assertContains(response, f"openCompendiumPreviewModal({self.object.pk})")

    def test_search_preview_prioritizes_exact_match(self):
        self.client.force_login(self.user)
        GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.SPELL,
            name="Magic Missile Volley",
            source=GameObject.SourceType.CUSTOM,
        )

        response = self.client.get(
            reverse("compendium:search_preview"),
            data={"q": "Magic Missile"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertLess(html.find("Magic Missile"), html.find("Magic Missile Volley"))


class CompendiumCachingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cache-user", password="pw12345!")
        self.object = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Cache Blade",
            source=GameObject.SourceType.CUSTOM,
            description="First version",
            data={"text": ["First version"]},
        )
        self.client.force_login(self.user)

    def test_object_detail_refreshes_after_object_update(self):
        first_response = self.client.get(reverse("compendium:object_detail", args=[self.object.pk]))
        self.assertContains(first_response, "First version")

        self.object.description = "Second version"
        self.object.data = {"text": ["Second version"]}
        self.object.save(update_fields=["description", "data", "updated_at"])

        second_response = self.client.get(reverse("compendium:object_detail", args=[self.object.pk]))
        self.assertContains(second_response, "Second version")
        self.assertNotContains(second_response, "First version")


class TagPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="tag-owner", password="pw12345!")
        self.other = User.objects.create_user(username="tag-other", password="pw12345!")
        self.tag = Tag.objects.create(
            name="Owner Tag",
            color="#123456",
            system="dnd5e",
            created_by=self.owner,
            is_system_tag=False,
        )

    def test_non_owner_cannot_edit_other_users_tag(self):
        self.client.force_login(self.other)

        response = self.client.post(
            reverse("compendium:tag_update", args=[self.tag.pk]),
            data={"name": "Hijacked", "color": "#654321", "system": "dnd5e"},
        )

        self.assertEqual(response.status_code, 403)
        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, "Owner Tag")

    def test_non_owner_cannot_delete_other_users_tag(self):
        self.client.force_login(self.other)

        response = self.client.post(reverse("compendium:tag_remove", args=[self.tag.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Tag.objects.filter(pk=self.tag.pk).exists())

    def test_tag_list_hides_edit_controls_for_read_only_tags(self):
        self.client.force_login(self.other)

        response = self.client.get(reverse("compendium:tags"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Read only")
        self.assertNotContains(response, 'name="is_system_tag"', html=False)
