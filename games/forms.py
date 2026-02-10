import json

from django import forms

from compendium.forms import JSONTextareaField

from .models import Encounter, Game, GameObjectInstance, GamePlayer


class GameForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = ["title"]


class GameObjectInstanceEditForm(forms.ModelForm):
    """Edit per-game instance fields while keeping JSON data validated."""
    data_text = JSONTextareaField(required=False, widget=forms.Textarea(attrs={"rows": 10}))

    class Meta:
        model = GameObjectInstance
        fields = ["name", "description", "data_text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["data_text"].initial = json.dumps(self.instance.data, indent=2, ensure_ascii=True)

    def save(self, commit=True):
        """Persist parsed JSON textarea content back into instance data."""
        instance = super().save(commit=False)
        instance.data = self.cleaned_data.get("data_text") or {}
        if commit:
            instance.save()
        return instance


class EncounterForm(forms.ModelForm):
    class Meta:
        model = Encounter
        fields = ["title"]


class GamePlayerForm(forms.ModelForm):
    class Meta:
        model = GamePlayer
        fields = [
            "name",
            "notes",
            "ac",
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
