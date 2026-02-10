from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/signup/", views.signup, name="signup"),
    path("settings/modal/", views.settings_modal, name="settings_modal"),
    path("settings/save/", views.save_settings, name="save_settings"),
    path("settings/import-upload/", views.import_user_compendium_xml, name="import_user_compendium_xml"),
    path("settings/import-remove/", views.remove_user_imported_xml, name="remove_user_imported_xml"),
]
