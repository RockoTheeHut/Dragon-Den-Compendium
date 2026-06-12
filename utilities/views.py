import json
import logging
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
from core.models import get_effective_openai_api_key
from games.models import GameObjectInstance

from .forms import ALLOWED_DICE_SIDES, DiceToolForm, MagicItemGeneratorForm, MagicItemSaveGameForm, MagicItemSaveGlobalForm


logger = logging.getLogger(__name__)

RANDOM_ITEM_HISTORY_SESSION_KEY = "random_item_picker_history_ids"
RANDOM_ITEM_HISTORY_LIMIT = 3
GENERATED_ITEM_SESSION_KEY = "magic_item_generated_payload"


def _load_random_item_history_ids(request):
    """Load and sanitize recent random-pick IDs from session storage."""
    raw_values = request.session.get(RANDOM_ITEM_HISTORY_SESSION_KEY, [])
    if not isinstance(raw_values, list):
        return []

    history_ids = []
    for value in raw_values:
        try:
            item_id = int(value)
        except (TypeError, ValueError):
            continue
        if item_id > 0:
            history_ids.append(item_id)
    return history_ids


def _resolve_random_item_history(history_ids):
    """Resolve IDs to objects while preserving original order."""
    history_items = GameObject.objects.filter(pk__in=history_ids).only("id", "name", "object_type", "system", "source")
    items_by_id = {item.pk: item for item in history_items}
    return [items_by_id[item_id] for item_id in history_ids if item_id in items_by_id]


def _resolve_openai_api_key(user):
    return get_effective_openai_api_key(user)


def _extract_json(text):
    """Extract the first JSON object from model output text."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Could not parse JSON payload from model output.")
    return json.loads(text[start : end + 1])


def _generate_magic_item(payload, model, api_key):
    """Call OpenAI and normalize the generated item payload."""
    client = OpenAI(api_key=api_key)
    instructions = (
        "You create tabletop RPG magic items. "
        "Return strict JSON with keys: name (string), description (string), "
        "mechanics (string), suggested_tags (array of strings)."
    )
    user_prompt = (
        f"Item type: {payload['item_type']}\n"
        f"Rarity: {payload['rarity']}\n"
        f"Theme: {payload['theme']}\n"
        f"Constraints: {payload['constraints'] or 'None'}\n"
        f"More detail: {payload['more_detail'] or 'None'}"
    )

    model_response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_prompt},
        ],
    )
    output_text = model_response.output_text
    generated = _extract_json(output_text)

    generated.setdefault("name", "Unnamed Magic Item")
    generated.setdefault("description", "")
    generated.setdefault("mechanics", "")
    tags = generated.get("suggested_tags") or []
    generated["suggested_tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
    return generated


def _build_magic_item_from_payload(generated, user):
    """Persist generated output as a custom compendium item owned by its creator."""
    description = generated.get("description", "")
    mechanics = generated.get("mechanics", "")
    return GameObject.objects.create(
        system="dnd5e",
        object_type=GameObject.ObjectType.ITEM,
        name=generated.get("name", "Unnamed Magic Item"),
        source=GameObject.SourceType.CUSTOM,
        created_by=user,
        description=description,
        data={
            "mechanics": mechanics,
            "generated": True,
            "suggested_tags": generated.get("suggested_tags", []),
        },
    )


def _attach_tags(game_object, tag_names, user):
    """Create missing tags and attach all generated tags to the object."""
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
    """Render generator UI and optionally run one generation request.

    Successful generations redirect back to the GET view (POST-redirect-GET)
    so a browser refresh doesn't silently re-issue a paid OpenAI call.
    """
    form = MagicItemGeneratorForm(request.POST or None)
    save_global_form = MagicItemSaveGlobalForm()
    save_game_form = MagicItemSaveGameForm(user=request.user)
    effective_api_key = _resolve_openai_api_key(request.user)
    openai_ready = bool(effective_api_key and settings.OPENAI_DEFAULT_MODEL)
    if request.method == "POST":
        if form.is_valid():
            if not openai_ready:
                messages.error(
                    request,
                    "OpenAI is not configured for your account. Save a key in Settings or set OPENAI_API_KEY and OPENAI_DEFAULT_MODEL.",
                )
            else:
                try:
                    generated = _generate_magic_item(
                        form.cleaned_data,
                        form.cleaned_data["model"],
                        effective_api_key,
                    )
                    request.session[GENERATED_ITEM_SESSION_KEY] = generated
                    return redirect("utilities:magic_item")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Magic item generation failed")
                    messages.error(request, f"Generation failed: {exc}")

    generated = request.session.get(GENERATED_ITEM_SESSION_KEY) if request.method == "GET" else None
    generated_json = json.dumps(generated) if generated else ""

    return render_page(
        request,
        "utilities/magic_item_generator.html",
        {
            "form": form,
            "generated": generated,
            "save_global_form": save_global_form,
            "save_game_form": save_game_form,
            "openai_ready": openai_ready,
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
    game_object = _build_magic_item_from_payload(generated, request.user)
    _attach_tags(game_object, generated.get("suggested_tags", []), request.user)
    messages.success(request, "Magic item saved to global compendium.")
    return redirect("compendium:object_detail", pk=game_object.pk)


@login_required
@require_POST
def save_magic_item_to_game(request):
    form = MagicItemSaveGameForm(request.POST, user=request.user)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid save request.")

    generated = json.loads(form.cleaned_data["generated_payload"])
    game = form.cleaned_data["game"]

    base_object = _build_magic_item_from_payload(generated, request.user)
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
def dice_modal(request):
    in_modal = bool(request.headers.get("HX-Request"))
    context = {
        "form": DiceToolForm(),
        "allowed_dice_sides": ALLOWED_DICE_SIDES,
        "in_modal": in_modal,
    }
    if in_modal:
        return render(request, "utilities/dice_modal_content.html", context)
    return render_page(request, "utilities/dice_modal_content.html", context)


@login_required
def random_item_modal(request):
    in_modal = bool(request.headers.get("HX-Request"))
    context = {
        "in_modal": in_modal,
        "object_type_choices": GameObject.ObjectType.choices,
        "selected_object_type": GameObject.ObjectType.ITEM,
    }
    if in_modal:
        return render(request, "utilities/random_item_modal_content.html", context)
    return render_page(request, "utilities/random_item_modal_content.html", context)


@login_required
@require_POST
def random_item_pick(request):
    """Pick one random object with optional type filter and short pick history."""
    selected_object_type = request.POST.get("object_type", GameObject.ObjectType.ITEM).strip()
    allowed_object_types = {value for value, _label in GameObject.ObjectType.choices}
    if selected_object_type and selected_object_type not in allowed_object_types:
        return HttpResponseBadRequest("Invalid object type.")

    items = GameObject.objects.all()
    if selected_object_type:
        items = items.filter(object_type=selected_object_type)
    items = items.only("id", "name", "object_type", "system", "source").order_by("id")
    item_count = items.count()
    if item_count == 0:
        recent_items = _resolve_random_item_history(_load_random_item_history_ids(request))
        return render(
            request,
            "utilities/partials/random_item_result.html",
            {
                "random_item": None,
                "selected_object_type": selected_object_type,
                "recent_items": recent_items,
            },
        )

    random_index = random.randint(0, item_count - 1)
    random_item = items[random_index]
    history_ids = _load_random_item_history_ids(request)
    recent_items = _resolve_random_item_history(history_ids[:RANDOM_ITEM_HISTORY_LIMIT])
    history_ids.insert(0, random_item.pk)
    history_ids = history_ids[:RANDOM_ITEM_HISTORY_LIMIT]
    request.session[RANDOM_ITEM_HISTORY_SESSION_KEY] = history_ids

    return render(
        request,
        "utilities/partials/random_item_result.html",
        {
            "random_item": random_item,
            "selected_object_type": selected_object_type,
            "recent_items": recent_items,
        },
    )


@login_required
@require_POST
def dice_roll_tool(request):
    """Roll grouped dice plans and return aggregated per-die-type totals."""
    form = DiceToolForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid dice input. Build a roll list with allowed dice types and quantities.")

    roll_plan = form.cleaned_data["roll_plan"]
    rolls_by_sides = {}
    for entry in roll_plan:
        quantity = entry["quantity"]
        sides = entry["sides"]
        rolls = [random.randint(1, sides) for _ in range(quantity)]
        if sides not in rolls_by_sides:
            rolls_by_sides[sides] = []
        rolls_by_sides[sides].extend(rolls)

    grouped_results = []
    total = 0
    total_dice = 0
    for sides in ALLOWED_DICE_SIDES:
        grouped_rolls = rolls_by_sides.get(sides, [])
        if not grouped_rolls:
            continue
        subtotal = sum(grouped_rolls)
        grouped_results.append(
            {
                "sides": sides,
                "rolls": grouped_rolls,
                "count": len(grouped_rolls),
                "subtotal": subtotal,
            }
        )
        total += subtotal
        total_dice += len(grouped_rolls)

    context = {
        "grouped_results": grouped_results,
        "total": total,
        "total_dice": total_dice,
    }

    if request.headers.get("HX-Request"):
        return render(request, "utilities/partials/dice_tool_result.html", context)
    return redirect("core:home")
