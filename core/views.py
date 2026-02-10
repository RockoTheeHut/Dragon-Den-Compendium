import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.core.management.base import CommandError
from django.db.models import Count

from compendium.management.commands.import_fightclub_xml import import_fightclub_xml_path
from compendium.models import Favorite
from games.models import Game

from .forms import CompendiumUploadImportForm, SignUpForm, UserSettingsForm
from .models import UserImportedObject, UserSettings
from .rendering import render_page


@login_required
def home(request):
    recent_games = Game.objects.filter(created_by=request.user)[:5]
    favorite_objects = (
        Favorite.objects.filter(user=request.user)
        .select_related("game_object")
        .prefetch_related("game_object__tags")
        .order_by("-id")[:8]
    )
    return render_page(
        request,
        "core/home.html",
        {
            "recent_games": recent_games,
            "favorite_objects": favorite_objects,
        },
    )


def signup(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("core:home")
    else:
        form = SignUpForm()

    return render_page(request, "registration/signup.html", {"form": form})


@login_required
def settings_modal(request):
    context = _settings_context(request)
    if context["in_modal"]:
        return render(request, "core/settings_modal_content.html", context)
    return render_page(request, "core/settings_modal_content.html", context)


def _render_settings_modal_response(request, context, trigger_compendium_reload=False):
    if request.headers.get("HX-Request"):
        response = render(request, "core/settings_modal_content.html", context)
        if trigger_compendium_reload:
            response["HX-Trigger"] = "compendiumReloadRequested"
        return response
    return redirect("core:home")


def _settings_context(request, settings_form=None, upload_form=None, import_result_message=""):
    in_modal = bool(request.headers.get("HX-Request"))
    user_settings = UserSettings.for_user(request.user)
    server_xml_path = (settings.SERVER_COMPENDIUM_XML_PATH or "").strip()
    has_server_xml = bool(server_xml_path)
    settings_form = settings_form or UserSettingsForm(
        initial={
            "openai_api_key": user_settings.openai_api_key if user_settings else "",
        }
    )
    upload_form = upload_form or CompendiumUploadImportForm(
        initial={
            "system": settings.SERVER_COMPENDIUM_SYSTEM,
            "use_server_xml": has_server_xml,
        }
    )
    if not has_server_xml:
        upload_form.fields["use_server_xml"].widget.attrs["disabled"] = "disabled"
    return {
        "settings_form": settings_form,
        "compendium_upload_form": upload_form,
        "server_compendium_xml_path": server_xml_path,
        "has_server_compendium_xml_path": has_server_xml,
        "in_modal": in_modal,
        "has_user_openai_api_key": bool(user_settings and user_settings.openai_api_key),
        "import_result_message": import_result_message,
    }


@login_required
@require_POST
def save_settings(request):
    settings_form = UserSettingsForm(request.POST)
    if settings_form.is_valid():
        user_settings = UserSettings.for_user(request.user)
        user_settings.openai_api_key = settings_form.cleaned_data["openai_api_key"].strip()
        user_settings.save(update_fields=["openai_api_key", "updated_at"])
        if user_settings.openai_api_key:
            messages.success(request, "Settings saved.")
        else:
            messages.success(request, "Settings saved. OpenAI API key cleared.")

    context = _settings_context(request, settings_form=settings_form)
    return _render_settings_modal_response(request, context, trigger_compendium_reload=False)


@login_required
@require_POST
def import_user_compendium_xml(request):
    upload_form = CompendiumUploadImportForm(request.POST, request.FILES)
    import_result_message = ""

    if upload_form.is_valid():
        use_server_xml = bool(upload_form.cleaned_data.get("use_server_xml"))
        system = upload_form.cleaned_data["system"]
        if use_server_xml:
            server_xml_path = (settings.SERVER_COMPENDIUM_XML_PATH or "").strip()
            if not server_xml_path:
                import_result_message = "Server compendium path is not configured."
                messages.error(request, import_result_message)
                context = _settings_context(request, upload_form=upload_form, import_result_message=import_result_message)
                return _render_settings_modal_response(request, context, trigger_compendium_reload=False)
            import_path = Path(server_xml_path)
        else:
            uploaded_file = upload_form.cleaned_data["xml_file"]
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(prefix="user-compendium-", suffix=".xml", delete=False) as temp_file:
                    for chunk in uploaded_file.chunks():
                        temp_file.write(chunk)
                    temp_path = Path(temp_file.name)
                import_path = temp_path
            except OSError as exc:
                import_result_message = f"Import failed: {exc}"
                messages.error(request, import_result_message)
                context = _settings_context(request, upload_form=upload_form, import_result_message=import_result_message)
                return _render_settings_modal_response(request, context, trigger_compendium_reload=False)

        should_reload_compendium = False
        try:
            result = import_fightclub_xml_path(file_path=import_path, system=system)
            touched_ids = list(result.get("touched_object_ids") or [])
            if touched_ids:
                UserImportedObject.objects.bulk_create(
                    [UserImportedObject(user=request.user, game_object_id=object_id) for object_id in touched_ids],
                    ignore_conflicts=True,
                )
            import_result_message = (
                f"Import complete. Created={result['created']}, Updated={result['updated']}, Unchanged={result['unchanged']}"
            )
            messages.success(request, import_result_message)
            should_reload_compendium = True
        except CommandError as exc:
            import_result_message = f"Import failed: {exc}"
            messages.error(request, import_result_message)
        finally:
            if not use_server_xml and "temp_path" in locals() and temp_path and temp_path.exists():
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
    else:
        import_result_message = "Import failed. Upload a valid .xml file or enable server-wide XML."
        messages.error(request, import_result_message)
        should_reload_compendium = False

    context = _settings_context(request, upload_form=upload_form, import_result_message=import_result_message)
    return _render_settings_modal_response(request, context, trigger_compendium_reload=should_reload_compendium)


@login_required
@require_POST
def remove_user_imported_xml(request):
    mappings = UserImportedObject.objects.filter(user=request.user)
    mapped_object_ids = list(mappings.values_list("game_object_id", flat=True))
    if not mapped_object_ids:
        # Legacy fallback: if no mapping rows exist at all yet, treat imported rows as pre-tracking legacy data.
        has_any_mapping_rows = UserImportedObject.objects.exists()
        if not has_any_mapping_rows:
            from compendium.models import GameObject

            removed_count = GameObject.objects.filter(
                source=GameObject.SourceType.IMPORTED,
            ).delete()[0]
            import_result_message = f"Removed {removed_count} legacy imported objects."
            messages.success(request, import_result_message)
            context = _settings_context(request, import_result_message=import_result_message)
            return _render_settings_modal_response(request, context, trigger_compendium_reload=True)

        import_result_message = "No imported XML objects are linked to your account."
        messages.warning(request, import_result_message)
        context = _settings_context(request, import_result_message=import_result_message)
        return _render_settings_modal_response(request, context, trigger_compendium_reload=False)

    usage_counts = {
        row["game_object_id"]: row["total_users"]
        for row in UserImportedObject.objects.filter(game_object_id__in=mapped_object_ids)
        .values("game_object_id")
        .annotate(total_users=Count("user", distinct=True))
    }
    deletable_ids = [object_id for object_id in mapped_object_ids if usage_counts.get(object_id, 0) <= 1]
    shared_ids = [object_id for object_id in mapped_object_ids if usage_counts.get(object_id, 0) > 1]

    mappings.delete()

    removed_count = 0
    if deletable_ids:
        from compendium.models import GameObject

        removed_count = GameObject.objects.filter(
            id__in=deletable_ids,
            source=GameObject.SourceType.IMPORTED,
        ).delete()[0]

    import_result_message = f"Removed {removed_count} imported objects linked only to your account."
    if shared_ids:
        import_result_message += f" Kept {len(shared_ids)} shared imported objects used by other users."
    messages.success(request, import_result_message)
    context = _settings_context(request, import_result_message=import_result_message)
    return _render_settings_modal_response(request, context, trigger_compendium_reload=True)
