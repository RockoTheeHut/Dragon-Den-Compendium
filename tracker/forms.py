from django import forms

from compendium.models import GameObject
from games.models import GameObjectInstance

from .models import TurnTrackerEntry


class TurnTrackerEntryForm(forms.ModelForm):
    class Meta:
        model = TurnTrackerEntry
        fields = [
            "name",
            "entry_type",
            "initiative",
            "is_active",
            "hp_current",
            "hp_max",
            "items_text",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
            "items_text": forms.Textarea(attrs={"rows": 2, "placeholder": "Shortsword, Potion of Healing"}),
        }

    def clean(self):
        cleaned = super().clean()
        entry_type = cleaned.get("entry_type")
        if entry_type == TurnTrackerEntry.EntryType.PLAYER:
            cleaned["hp_current"] = None
            cleaned["hp_max"] = None
            cleaned["items_text"] = ""
        return cleaned


class AddFromCompendiumForm(forms.Form):
    source = forms.ModelChoiceField(queryset=GameObject.objects.none())
    entry_type = forms.ChoiceField(
        choices=[
            (TurnTrackerEntry.EntryType.NPC, "NPC"),
            (TurnTrackerEntry.EntryType.ENEMY, "Enemy"),
        ]
    )
    name = forms.CharField(required=False, max_length=255)
    initiative = forms.IntegerField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)
    hp_current = forms.IntegerField(required=False)
    hp_max = forms.IntegerField(required=False)
    items_text = forms.CharField(required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = GameObject.objects.filter(object_type=GameObject.ObjectType.MONSTER).order_by("name")


class AddFromGameInstanceForm(forms.Form):
    source = forms.ModelChoiceField(queryset=GameObjectInstance.objects.none())
    entry_type = forms.ChoiceField(
        choices=[
            (TurnTrackerEntry.EntryType.NPC, "NPC"),
            (TurnTrackerEntry.EntryType.ENEMY, "Enemy"),
        ]
    )
    name = forms.CharField(required=False, max_length=255)
    initiative = forms.IntegerField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)
    hp_current = forms.IntegerField(required=False)
    hp_max = forms.IntegerField(required=False)
    items_text = forms.CharField(required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        queryset = GameObjectInstance.objects.select_related("game").order_by("name")
        if user and user.is_authenticated:
            queryset = queryset.filter(game__created_by=user)
        else:
            queryset = queryset.none()
        self.fields["source"].queryset = queryset
