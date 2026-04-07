import re

from django.db.models import Case, Exists, IntegerField, OuterRef, Value, When
from django.db.models.functions import Lower

from .models import Favorite, GameObject


OBJECT_TYPE_SORT_ORDER = [
    GameObject.ObjectType.CLASS,
    GameObject.ObjectType.FEAT,
    GameObject.ObjectType.ITEM,
    GameObject.ObjectType.MONSTER,
    GameObject.ObjectType.CONDITION,
    GameObject.ObjectType.SPELL,
    GameObject.ObjectType.RACE,
    GameObject.ObjectType.BACKGROUND,
    GameObject.ObjectType.CHARACTER,
    GameObject.ObjectType.NPC,
    GameObject.ObjectType.MISC,
]

SEARCH_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def normalize_search_query(query):
    query = (query or "").strip().lower()
    return re.sub(r"\s+", " ", query)


def tokenize_search_query(query):
    return SEARCH_TOKEN_PATTERN.findall(normalize_search_query(query))


def with_object_type_sort_order(queryset):
    whens = [When(object_type=object_type, then=Value(index)) for index, object_type in enumerate(OBJECT_TYPE_SORT_ORDER)]
    return queryset.annotate(
        object_type_order=Case(
            *whens,
            default=Value(len(OBJECT_TYPE_SORT_ORDER)),
            output_field=IntegerField(),
        )
    )


def apply_name_search(queryset, query):
    normalized = normalize_search_query(query)
    if not normalized:
        return queryset, normalized

    tokens = tokenize_search_query(normalized)
    queryset = queryset.annotate(name_lower=Lower("name"))
    for token in tokens:
        queryset = queryset.filter(name_lower__contains=token)

    queryset = queryset.annotate(
        search_rank=Case(
            When(name_lower=normalized, then=Value(0)),
            When(name_lower__startswith=normalized, then=Value(1)),
            When(name_lower__contains=f" {normalized}", then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    )
    return queryset, normalized


def apply_search_filters(queryset, request):
    query = request.GET.get("q", "").strip()
    object_type = request.GET.get("object_type", "").strip()
    tag_id = request.GET.get("tag", "").strip()
    favorites_only = request.GET.get("favorites") == "1"

    queryset, normalized_query = apply_name_search(queryset, query)

    if object_type:
        queryset = queryset.filter(object_type=object_type)

    if tag_id.isdigit():
        queryset = queryset.filter(tags__id=int(tag_id))

    if favorites_only:
        queryset = queryset.filter(favorited_by__user=request.user)

    queryset = with_object_type_sort_order(queryset)
    sort = request.GET.get("sort")
    if sort == "favorites":
        favorites = Favorite.objects.filter(user=request.user, game_object=OuterRef("pk"))
        queryset = queryset.annotate(is_favorite=Exists(favorites))

    order_by = []
    if normalized_query:
        order_by.append("search_rank")
    if sort == "favorites":
        order_by.append("-is_favorite")
    order_by.extend(["object_type_order", "name"])
    queryset = queryset.order_by(*order_by)

    return queryset.distinct(), {
        "q": query,
        "object_type": object_type,
        "tag": tag_id,
        "favorites": "1" if favorites_only else "0",
        "sort": sort or "",
    }


def get_search_preview_queryset(query):
    queryset = GameObject.objects.all()
    queryset, normalized_query = apply_name_search(queryset, query)
    if not normalized_query:
        return queryset.none()
    queryset = with_object_type_sort_order(queryset)
    return queryset.order_by("search_rank", "object_type_order", "name")
