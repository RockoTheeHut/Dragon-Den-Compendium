from copy import deepcopy

from django.core.cache import cache

from games.models import Game

from .models import Favorite
from .rules import (
    apply_inline_reference_links,
    build_reference_lookup,
    build_related_reference_groups,
    build_rules_sections,
    compile_reference_pattern,
)
from .text_utils import build_preview_context


DETAIL_CACHE_TIMEOUT_SECONDS = 60 * 60


def _cache_stamp(game_object):
    return f"{game_object.pk}:{game_object.updated_at.isoformat()}"


def get_preview_context(game_object):
    cache_key = f"compendium:preview:{_cache_stamp(game_object)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return deepcopy(cached)

    preview_context = build_preview_context(game_object)
    cache.set(cache_key, preview_context, DETAIL_CACHE_TIMEOUT_SECONDS)
    return deepcopy(preview_context)


def get_detail_payload(game_object):
    cache_key = f"compendium:detail:{_cache_stamp(game_object)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return deepcopy(cached)

    preview_context = get_preview_context(game_object)
    related_reference_groups = build_related_reference_groups(game_object, preview_context)
    reference_lookup = build_reference_lookup(related_reference_groups)
    reference_pattern = compile_reference_pattern(reference_lookup)
    apply_inline_reference_links(preview_context, reference_lookup, reference_pattern)
    rules_sections = build_rules_sections(preview_context, reference_lookup, reference_pattern)

    payload = {
        **preview_context,
        "related_reference_groups": related_reference_groups,
        "rules_sections": rules_sections,
    }
    cache.set(cache_key, payload, DETAIL_CACHE_TIMEOUT_SECONDS)
    return deepcopy(payload)


def build_object_detail_context(game_object, form, user, can_edit=False):
    payload = get_detail_payload(game_object)
    return {
        "game_object": game_object,
        "form": form,
        "games": Game.objects.filter(created_by=user).only("id", "title").order_by("title"),
        "is_favorite": Favorite.objects.filter(user=user, game_object=game_object).exists(),
        "can_edit": can_edit,
        **payload,
    }
