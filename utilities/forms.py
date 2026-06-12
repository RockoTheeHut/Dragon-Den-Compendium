import json

from django import forms
from django.conf import settings

from games.models import Game

ALLOWED_DICE_SIDES = (4, 6, 8, 10, 12, 20, 100)


class MagicItemGeneratorForm(forms.Form):
    """Prompt fields for LLM-based magic item generation."""
    item_type = forms.CharField(max_length=100)
    rarity = forms.CharField(max_length=100)
    theme = forms.CharField(max_length=150)
    constraints = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    more_detail = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    model = forms.ChoiceField(choices=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        options = [(item, item) for item in settings.OPENAI_MODEL_OPTIONS]
        self.fields["model"].choices = options
        self.fields["model"].initial = settings.OPENAI_DEFAULT_MODEL


class DiceToolForm(forms.Form):
    """Validate the client-generated roll plan JSON payload."""
    roll_plan = forms.CharField()

    def clean_roll_plan(self):
        """Parse and validate each dice-group entry."""
        raw_plan = self.cleaned_data.get("roll_plan", "")
        try:
            decoded = json.loads(raw_plan)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Invalid roll plan JSON.") from exc

        if not isinstance(decoded, list) or not decoded:
            raise forms.ValidationError("Roll plan must include at least one dice entry.")

        validated = []
        for entry in decoded:
            if not isinstance(entry, dict):
                raise forms.ValidationError("Each roll plan entry must be an object.")

            try:
                quantity = int(entry.get("quantity"))
                sides = int(entry.get("sides"))
            except (TypeError, ValueError) as exc:
                raise forms.ValidationError("Dice quantity and sides must be integers.") from exc

            if quantity < 1:
                raise forms.ValidationError("Dice quantity must be at least 1.")
            if sides not in ALLOWED_DICE_SIDES:
                raise forms.ValidationError(
                    f"Unsupported die type d{sides}. Allowed: {', '.join(f'd{value}' for value in ALLOWED_DICE_SIDES)}."
                )

            validated.append({"quantity": quantity, "sides": sides})

        return validated


class MagicItemSaveFormBase(forms.Form):
    """Shared validation for the user-editable hidden payload field."""

    generated_payload = forms.CharField(widget=forms.HiddenInput)

    def clean_generated_payload(self):
        """Ensure generated payload remains a JSON object before persistence."""
        payload = self.cleaned_data["generated_payload"]
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Generated payload is invalid JSON.") from exc
        if not isinstance(data, dict):
            raise forms.ValidationError("Generated payload must be an object.")
        return payload


class MagicItemSaveGlobalForm(MagicItemSaveFormBase):
    pass


class MagicItemSaveGameForm(MagicItemSaveFormBase):
    game = forms.ModelChoiceField(queryset=Game.objects.order_by("title"))

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        queryset = Game.objects.order_by("title")
        if user and user.is_authenticated:
            queryset = queryset.filter(created_by=user)
        else:
            queryset = queryset.none()
        self.fields["game"].queryset = queryset
