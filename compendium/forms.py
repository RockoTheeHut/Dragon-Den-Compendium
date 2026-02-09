import json

from django import forms

from .models import GameObject, Tag


class JSONTextareaField(forms.CharField):
    def to_python(self, value):
        value = super().to_python(value)
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise forms.ValidationError("JSON data must be an object.")
        return parsed


class GameObjectCreateForm(forms.ModelForm):
    data_text = JSONTextareaField(required=False, widget=forms.Textarea(attrs={"rows": 10}))
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = GameObject
        fields = ["system", "object_type", "name", "description", "data_text", "tags"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags"].queryset = Tag.objects.order_by("name")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.source = GameObject.SourceType.CUSTOM
        instance.data = self.cleaned_data.get("data_text") or {}
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class GameObjectEditForm(forms.ModelForm):
    data_text = JSONTextareaField(required=False, widget=forms.Textarea(attrs={"rows": 12}))
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = GameObject
        fields = ["name", "description", "data_text", "tags"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags"].queryset = Tag.objects.order_by("name")
        if self.instance.pk:
            self.fields["data_text"].initial = json.dumps(self.instance.data, indent=2, ensure_ascii=True)
            self.fields["tags"].initial = self.instance.tags.all()

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.data = self.cleaned_data.get("data_text") or {}
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "color", "system", "is_system_tag"]
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
        }
