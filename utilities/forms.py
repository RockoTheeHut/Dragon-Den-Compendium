import json

from django import forms
from django.conf import settings

from games.models import Game


class MagicItemGeneratorForm(forms.Form):
    item_type = forms.CharField(max_length=100)
    rarity = forms.CharField(max_length=100)
    theme = forms.CharField(max_length=150)
    constraints = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    model = forms.ChoiceField(choices=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        options = [(item, item) for item in settings.OPENAI_MODEL_OPTIONS]
        self.fields["model"].choices = options
        self.fields["model"].initial = settings.OPENAI_DEFAULT_MODEL


class DiceRollForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=100, initial=1)
    die_type = forms.ChoiceField(
        choices=[(str(value), f"d{value}") for value in (4, 6, 8, 10, 12, 20, 100)],
        initial="20",
    )


class MagicItemSaveGlobalForm(forms.Form):
    generated_payload = forms.CharField(widget=forms.HiddenInput)


class MagicItemSaveGameForm(forms.Form):
    generated_payload = forms.CharField(widget=forms.HiddenInput)
    game = forms.ModelChoiceField(queryset=Game.objects.order_by("title"))

    def clean_generated_payload(self):
        payload = self.cleaned_data["generated_payload"]
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Generated payload is invalid JSON.") from exc
        if not isinstance(data, dict):
            raise forms.ValidationError("Generated payload must be an object.")
        return payload
