import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from compendium.models import Favorite, GameObject
from games.models import Game
from .models import UserImportedObject, UserSettings


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
        self.assertContains(response, "Roll Dice")
        self.assertContains(response, "Random Item")


class UserSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="settings-user", password="pw12345!")
        self.client.force_login(self.user)

    def test_settings_modal_renders(self):
        self.assertFalse(UserSettings.objects.filter(user=self.user).exists())
        response = self.client.get(reverse("core:settings_modal"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OpenAI API Key")
        self.assertContains(response, "Import User XML")
        self.assertContains(response, "Use server-wide XML")
        self.assertContains(response, "Logout")
        self.assertFalse(UserSettings.objects.filter(user=self.user).exists())

    @override_settings(SERVER_COMPENDIUM_XML_PATH="/tmp/server.xml", SERVER_COMPENDIUM_SYSTEM="dnd5e")
    def test_use_server_xml_toggle_defaults_on_when_server_path_exists(self):
        response = self.client.get(reverse("core:settings_modal"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="use_server_xml"', html=False)
        self.assertContains(response, 'id="id_use_server_xml" checked', html=False)

    @override_settings(SERVER_COMPENDIUM_XML_PATH="", SERVER_COMPENDIUM_SYSTEM="dnd5e")
    def test_use_server_xml_toggle_disabled_when_server_path_missing(self):
        response = self.client.get(reverse("core:settings_modal"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="use_server_xml"', html=False)
        self.assertContains(response, 'name="use_server_xml" disabled="disabled"', html=False)

    def test_save_settings_stores_openai_api_key(self):
        response = self.client.post(
            reverse("core:save_settings"),
            data={"openai_api_key": "sk-user-abc123"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        settings_row = UserSettings.objects.get(user=self.user)
        self.assertEqual(settings_row.openai_api_key, "sk-user-abc123")

    def test_save_settings_can_clear_openai_api_key(self):
        UserSettings.objects.create(user=self.user, openai_api_key="sk-user-existing")

        self.client.post(
            reverse("core:save_settings"),
            data={"openai_api_key": ""},
            HTTP_HX_REQUEST="true",
        )

        settings_row = UserSettings.objects.get(user=self.user)
        self.assertEqual(settings_row.openai_api_key, "")

    def test_import_user_compendium_xml_from_upload(self):
        xml_payload = b"""
        <compendium>
          <monster>
            <name>Upload Goblin</name>
            <text>Imported from user upload</text>
          </monster>
        </compendium>
        """
        upload = SimpleUploadedFile("upload.xml", xml_payload, content_type="application/xml")

        response = self.client.post(
            reverse("core:import_user_compendium_xml"),
            data={"system": "dnd5e", "xml_file": upload},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(GameObject.objects.filter(name="Upload Goblin", object_type=GameObject.ObjectType.MONSTER).exists())
        imported_object = GameObject.objects.get(name="Upload Goblin", object_type=GameObject.ObjectType.MONSTER)
        self.assertTrue(UserImportedObject.objects.filter(user=self.user, game_object=imported_object).exists())
        self.assertContains(response, "Import complete.")
        self.assertEqual(response.headers.get("HX-Trigger"), "compendiumReloadRequested")

    @override_settings(SERVER_COMPENDIUM_XML_PATH="", SERVER_COMPENDIUM_SYSTEM="dnd5e")
    def test_server_import_requires_server_path(self):
        response = self.client.post(
            reverse("core:import_user_compendium_xml"),
            data={"system": "dnd5e", "use_server_xml": "on"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Server compendium path is not configured.")

    def test_import_server_compendium_xml_uses_configured_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "server.xml"
            xml_path.write_text(
                """
                <compendium>
                  <item>
                    <name>Server Lantern</name>
                    <text>Imported from server path</text>
                  </item>
                </compendium>
                """.strip(),
                encoding="utf-8",
            )

            with self.settings(SERVER_COMPENDIUM_XML_PATH=str(xml_path), SERVER_COMPENDIUM_SYSTEM="dnd5e"):
                response = self.client.post(
                    reverse("core:import_user_compendium_xml"),
                    data={"system": "dnd5e", "use_server_xml": "on"},
                    HTTP_HX_REQUEST="true",
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(GameObject.objects.filter(name="Server Lantern", object_type=GameObject.ObjectType.ITEM).exists())
        self.assertContains(response, "Import complete.")

    def test_remove_user_imported_xml_deletes_user_linked_objects(self):
        imported_object = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="User Import Blade",
            source=GameObject.SourceType.IMPORTED,
        )
        UserImportedObject.objects.create(user=self.user, game_object=imported_object)

        response = self.client.post(
            reverse("core:remove_user_imported_xml"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(GameObject.objects.filter(pk=imported_object.pk).exists())
        self.assertContains(response, "Removed 1 imported objects")
        self.assertEqual(response.headers.get("HX-Trigger"), "compendiumReloadRequested")

    def test_remove_user_imported_xml_keeps_shared_objects(self):
        other_user = User.objects.create_user(username="settings-other", password="pw12345!")
        shared_object = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.MONSTER,
            name="Shared Import Orc",
            source=GameObject.SourceType.IMPORTED,
        )
        UserImportedObject.objects.create(user=self.user, game_object=shared_object)
        UserImportedObject.objects.create(user=other_user, game_object=shared_object)

        response = self.client.post(
            reverse("core:remove_user_imported_xml"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(GameObject.objects.filter(pk=shared_object.pk).exists())
        self.assertFalse(UserImportedObject.objects.filter(user=self.user, game_object=shared_object).exists())
        self.assertContains(response, "Kept 1 shared imported objects")

    def test_remove_user_imported_xml_legacy_fallback_without_mapping_rows(self):
        legacy_import = GameObject.objects.create(
            system="dnd5e",
            object_type=GameObject.ObjectType.ITEM,
            name="Legacy Import Trinket",
            source=GameObject.SourceType.IMPORTED,
        )

        response = self.client.post(
            reverse("core:remove_user_imported_xml"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(GameObject.objects.filter(pk=legacy_import.pk).exists())
        self.assertContains(response, "Removed 1 legacy imported objects.")
