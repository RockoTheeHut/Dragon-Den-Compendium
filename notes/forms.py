from django import forms

from .models import SharedNote


class SharedNoteForm(forms.ModelForm):
    class Meta:
        model = SharedNote
        fields = ["title", "content", "visibility"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 5}),
        }
