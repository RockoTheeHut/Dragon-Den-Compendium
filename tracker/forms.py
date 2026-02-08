from django import forms

from games.models import GameObjectInstance

from .models import TurnEntry


class TurnEntryForm(forms.ModelForm):
    class Meta:
        model = TurnEntry
        fields = [
            "entity_type",
            "object_instance",
            "display_name",
            "initiative",
            "is_active",
            "hp_current",
            "hp_max",
            "notes",
        ]

    def __init__(self, *args, game=None, **kwargs):
        super().__init__(*args, **kwargs)
        if game is not None:
            self.fields["object_instance"].queryset = GameObjectInstance.objects.filter(game=game).order_by("name")
        else:
            self.fields["object_instance"].queryset = GameObjectInstance.objects.none()
        self.fields["display_name"].required = False

    def clean(self):
        cleaned_data = super().clean()
        object_instance = cleaned_data.get("object_instance")
        display_name = (cleaned_data.get("display_name") or "").strip()
        if object_instance and not display_name:
            cleaned_data["display_name"] = object_instance.name
        if not cleaned_data.get("display_name"):
            self.add_error("display_name", "Display name is required when no object instance is selected.")
        return cleaned_data
