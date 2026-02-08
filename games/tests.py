from django.contrib.auth.models import User
from django.test import TestCase

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
