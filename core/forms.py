from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


DEFAULT_COMPENDIUM_SYSTEM_CHOICES = [
    ("dnd5e", "dnd5e"),
]


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")


class UserSettingsForm(forms.Form):
    """Settings fields stored in UserSettings (currently only OpenAI key)."""
    openai_api_key = forms.CharField(
        required=False,
        label="OpenAI API Key",
        widget=forms.PasswordInput(
            render_value=True,
            attrs={
                "placeholder": "sk-...",
                "autocomplete": "off",
            },
        ),
    )


class CompendiumUploadImportForm(forms.Form):
    """Validate either server-path import mode or uploaded XML mode."""
    system = forms.ChoiceField(choices=DEFAULT_COMPENDIUM_SYSTEM_CHOICES, initial="dnd5e")
    use_server_xml = forms.BooleanField(required=False, label="Use server-wide XML")
    xml_file = forms.FileField(label="Fight Club XML File", required=False)

    def clean(self):
        """Require an XML upload unless the server-wide toggle is enabled."""
        cleaned_data = super().clean()
        use_server_xml = bool(cleaned_data.get("use_server_xml"))
        xml_file = cleaned_data.get("xml_file")

        if use_server_xml:
            return cleaned_data

        if not xml_file:
            self.add_error("xml_file", "Please upload an .xml file or enable server-wide XML.")
            return cleaned_data

        file_name = (xml_file.name or "").lower()
        if not file_name.endswith(".xml"):
            self.add_error("xml_file", "Please upload an .xml file.")
        return cleaned_data
