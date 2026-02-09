from django import forms
from django.db.models import Max

from compendium.models import GameObject
from games.models import GameObjectInstance

from .models import StatusEffect, TurnTrackerEntry


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
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = GameObjectInstance.objects.order_by("name")


class StatusEffectForm(forms.ModelForm):
    class Meta:
        model = StatusEffect
        fields = ["name", "duration_rounds"]

    def save_for_entry(self, entry):
        max_sort = entry.status_effects.aggregate(max_sort=Max("sort_order")).get("max_sort")
        effect = self.save(commit=False)
        effect.entry = entry
        effect.remaining_rounds = effect.duration_rounds
        effect.is_running = True
        effect.sort_order = (max_sort + 1) if max_sort is not None else 0
        effect.save()
        return effect
