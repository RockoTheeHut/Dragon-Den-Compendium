from django import forms

from compendium.models import GameObject
from games.models import GamePlayer

from .models import TurnTrackerEntry


class TurnTrackerEntryForm(forms.ModelForm):
    """Base tracker entry form used for manual add/edit."""
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
        """Normalize player rows by clearing non-player-only fields."""
        cleaned = super().clean()
        entry_type = cleaned.get("entry_type")
        if entry_type == TurnTrackerEntry.EntryType.PLAYER:
            cleaned["hp_current"] = None
            cleaned["hp_max"] = None
            cleaned["items_text"] = ""
        return cleaned


class AddFromCompendiumForm(forms.Form):
    """Create tracker entries from global monster objects."""
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


class AddFromGamePlayerForm(forms.Form):
    """Create tracker entries from game-scoped player rows."""
    source = forms.ModelChoiceField(queryset=GamePlayer.objects.none())
    name = forms.CharField(required=False, max_length=255)
    initiative = forms.IntegerField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        """Restrict selectable players to games owned by the current user."""
        user = kwargs.pop("user", None)
        game = kwargs.pop("game", None)
        super().__init__(*args, **kwargs)
        queryset = GamePlayer.objects.select_related("game").order_by("name", "id")
        if user and user.is_authenticated:
            queryset = queryset.filter(game__created_by=user)
            if game is not None:
                queryset = queryset.filter(game=game)
        else:
            queryset = queryset.none()
        self.fields["source"].queryset = queryset
