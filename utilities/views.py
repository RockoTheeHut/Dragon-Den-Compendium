import json
import random

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from openai import OpenAI

from compendium.models import GameObject, Tag
from core.rendering import render_page
from games.models import GameObjectInstance

from .forms import DiceRollForm, MagicItemGeneratorForm, MagicItemSaveGameForm, MagicItemSaveGlobalForm


def _is_openai_ready():
    return bool(settings.OPENAI_API_KEY and settings.OPENAI_DEFAULT_MODEL)


def _extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Could not parse JSON payload from model output.")
    return json.loads(text[start : end + 1])


def _generate_magic_item(payload, model):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    instructions = (
        "You create tabletop RPG magic items. "
        "Return strict JSON with keys: name (string), description (string), "
        "mechanics (string), suggested_tags (array of strings)."
    )
    user_prompt = (
        f"Item type: {payload['item_type']}\n"
        f"Rarity: {payload['rarity']}\n"
        f"Theme: {payload['theme']}\n"
        f"Constraints: {payload['constraints'] or 'None'}"
    )

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_prompt},
        ],
    )
    output_text = response.output_text
    generated = _extract_json(output_text)

    generated.setdefault("name", "Unnamed Magic Item")
    generated.setdefault("description", "")
    generated.setdefault("mechanics", "")
    tags = generated.get("suggested_tags") or []
    generated["suggested_tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
    return generated


def _build_magic_item_from_payload(generated):
    description = generated.get("description", "")
    mechanics = generated.get("mechanics", "")
    return GameObject.objects.create(
        system="dnd5e",
        object_type=GameObject.ObjectType.ITEM,
        name=generated.get("name", "Unnamed Magic Item"),
        source=GameObject.SourceType.CUSTOM,
        description=description,
        data={
            "mechanics": mechanics,
            "generated": True,
            "suggested_tags": generated.get("suggested_tags", []),
        },
    )


def _attach_tags(game_object, tag_names, user):
    for tag_name in tag_names:
        tag, _ = Tag.objects.get_or_create(
            system=game_object.system,
            name=tag_name,
            defaults={
                "color": "#E67E22",
                "created_by": user,
                "is_system_tag": False,
            },
        )
        game_object.tags.add(tag)


@login_required
def magic_item_generator(request):
    generated = None
    generated_json = ""
    if request.method == "POST":
        form = MagicItemGeneratorForm(request.POST)
        if form.is_valid():
            if not _is_openai_ready():
                messages.error(request, "OpenAI is not configured. Set OPENAI_API_KEY and OPENAI_DEFAULT_MODEL.")
            else:
                try:
                    generated = _generate_magic_item(form.cleaned_data, form.cleaned_data["model"])
                    generated_json = json.dumps(generated)
                except Exception as exc:  # noqa: BLE001
                    messages.error(request, f"Generation failed: {exc}")
        save_global_form = MagicItemSaveGlobalForm()
        save_game_form = MagicItemSaveGameForm()
    else:
        form = MagicItemGeneratorForm()
        save_global_form = MagicItemSaveGlobalForm()
        save_game_form = MagicItemSaveGameForm()

    return render_page(
        request,
        "utilities/magic_item_generator.html",
        {
            "form": form,
            "generated": generated,
            "save_global_form": save_global_form,
            "save_game_form": save_game_form,
            "openai_ready": _is_openai_ready(),
            "generated_json": generated_json,
        },
    )


@login_required
@require_POST
def save_magic_item_global(request):
    form = MagicItemSaveGlobalForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid generated payload.")

    generated = json.loads(form.cleaned_data["generated_payload"])
    game_object = _build_magic_item_from_payload(generated)
    _attach_tags(game_object, generated.get("suggested_tags", []), request.user)
    messages.success(request, "Magic item saved to global compendium.")
    return redirect("compendium:object_detail", pk=game_object.pk)


@login_required
@require_POST
def save_magic_item_to_game(request):
    form = MagicItemSaveGameForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid save request.")

    generated = json.loads(form.cleaned_data["generated_payload"])
    game = form.cleaned_data["game"]

    base_object = _build_magic_item_from_payload(generated)
    _attach_tags(base_object, generated.get("suggested_tags", []), request.user)

    GameObjectInstance.objects.create(
        game=game,
        base_object=base_object,
        name=base_object.name,
        object_type=base_object.object_type,
        description=base_object.description,
        data=base_object.data,
    )
    messages.success(request, f"Magic item added to game '{game.title}'.")
    return redirect("games:detail", pk=game.pk)


@login_required
@require_POST
def dice_roll(request, game_id):
    form = DiceRollForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid dice input.")

    quantity = form.cleaned_data["quantity"]
    sides = int(form.cleaned_data["die_type"])
    rolls = [random.randint(1, sides) for _ in range(quantity)]
    context = {
        "quantity": quantity,
        "sides": sides,
        "rolls": rolls,
        "total": sum(rolls),
    }

    if request.headers.get("HX-Request"):
        return render(request, "utilities/partials/dice_result.html", context)
    return redirect("games:detail", pk=game_id)
