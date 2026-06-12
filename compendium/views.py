from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.rendering import render_page

from .detailing import build_object_detail_context, get_preview_context
from .forms import GameObjectCreateForm, GameObjectEditForm, TagForm
from .models import Favorite, GameObject, Tag
from .search import apply_search_filters, get_search_preview_queryset


@login_required
def object_list(request):
    objects = (
        GameObject.objects.only("id", "name", "object_type", "system", "source")
        .prefetch_related(Prefetch("tags", queryset=Tag.objects.only("id", "name", "color").order_by("name")))
    )
    objects, active_filters = apply_search_filters(objects, request)
    tags = Tag.objects.only("id", "name").order_by("name")
    paginator = Paginator(objects, 100)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    page_object_ids = [item.id for item in page_obj.object_list]
    favorites = set(
        Favorite.objects.filter(user=request.user, game_object_id__in=page_object_ids).values_list("game_object_id", flat=True)
    )
    context = {
        "objects": page_obj.object_list,
        "tags": tags,
        "favorites": favorites,
        "object_type_choices": GameObject.ObjectType.choices,
        "active_filters": active_filters,
        "page_obj": page_obj,
        "has_next": page_obj.has_next(),
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
        "scroll_query": urlencode(active_filters),
    }
    if request.headers.get("HX-Request") and request.GET.get("append") == "1":
        return render(request, "compendium/partials/object_rows.html", context)
    return render_page(request, "compendium/object_list.html", context)


def _can_edit_object(user, game_object):
    """Custom objects are editable by their creator (or anyone, for legacy
    unowned rows); shared imported/official content only by staff."""
    if user.is_staff:
        return True
    if game_object.source != GameObject.SourceType.CUSTOM:
        return False
    return game_object.created_by_id is None or game_object.created_by_id == user.id


@login_required
def object_create(request):
    if request.method == "POST":
        form = GameObjectCreateForm(request.POST)
        if form.is_valid():
            game_object = form.save(commit=False)
            game_object.created_by = request.user
            game_object.save()
            form.save_m2m()
            messages.success(request, "Game object created.")
            return redirect("compendium:object_detail", pk=game_object.pk)
    else:
        form = GameObjectCreateForm(initial={"system": "dnd5e"})
    return render_page(request, "compendium/object_create.html", {"form": form})


@login_required
def object_detail(request, pk):
    game_object = get_object_or_404(GameObject.objects.prefetch_related("tags"), pk=pk)
    form = GameObjectEditForm(instance=game_object)
    context = build_object_detail_context(
        game_object=game_object,
        form=form,
        user=request.user,
        can_edit=_can_edit_object(request.user, game_object),
    )
    return render_page(request, "compendium/object_detail.html", context)


@login_required
@require_GET
def object_preview_modal(request, pk):
    game_object = get_object_or_404(GameObject, pk=pk)
    context = {"game_object": game_object, **get_preview_context(game_object)}
    return render(request, "compendium/partials/object_preview_modal_content.html", context)


@login_required
@require_POST
def object_edit(request, pk):
    game_object = get_object_or_404(GameObject, pk=pk)
    if not _can_edit_object(request.user, game_object):
        return HttpResponseForbidden("Imported and official compendium objects can only be edited by admins.")
    form = GameObjectEditForm(request.POST, instance=game_object)
    if form.is_valid():
        form.save()
        messages.success(request, "Game object updated.")
        return redirect("compendium:object_detail", pk=pk)

    context = build_object_detail_context(
        game_object=game_object,
        form=form,
        user=request.user,
        can_edit=True,
    )
    return render_page(request, "compendium/object_detail.html", context)


@login_required
@require_POST
def toggle_favorite(request, pk):
    game_object = get_object_or_404(GameObject, pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, game_object=game_object)
    if not created:
        favorite.delete()

    if request.headers.get("HX-Request"):
        return render_page(
            request,
            "compendium/partials/favorite_button.html",
            {"game_object": game_object, "is_favorite": created},
        )
    return redirect("compendium:object_detail", pk=pk)


@login_required
def tag_list(request):
    if request.method == "POST":
        form = TagForm(request.POST)
        if form.is_valid():
            tag = form.save(commit=False)
            tag.created_by = request.user
            tag.save()
            messages.success(request, "Tag saved.")
            return redirect("compendium:tags")
    else:
        form = TagForm(initial={"system": "dnd5e", "color": "#4A90E2"})

    tags = Tag.objects.order_by("system", "name")
    return render_page(request, "compendium/tag_list.html", {"form": form, "tags": tags})


@login_required
@require_POST
def tag_update(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    if tag.is_system_tag or tag.created_by_id != request.user.id:
        return HttpResponseForbidden("You can only edit your own non-system tags.")
    form = TagForm(request.POST, instance=tag)
    if form.is_valid():
        updated = form.save(commit=False)
        updated.created_by = request.user
        updated.save()
        messages.success(request, "Tag updated.")
    else:
        messages.error(request, "Could not update tag.")
    return redirect("compendium:tags")


@login_required
@require_GET
def search_preview(request):
    query = request.GET.get("q", "").strip()
    objects = (
        get_search_preview_queryset(query)
        .only("id", "name", "object_type")
        .prefetch_related(Prefetch("tags", queryset=Tag.objects.only("id", "name", "color").order_by("name")))[:8]
    )
    return render_page(request, "compendium/partials/search_preview.html", {"objects": objects})


@login_required
@require_GET
def quick_search_redirect(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return redirect("compendium:list")
    return redirect(f"{reverse('compendium:list')}?{urlencode({'q': query})}")


@login_required
@require_POST
def remove_tag(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    if tag.is_system_tag:
        return HttpResponseBadRequest("System tags cannot be deleted.")
    if tag.created_by_id != request.user.id:
        return HttpResponseForbidden("You can only delete your own tags.")
    tag.delete()
    messages.success(request, "Tag deleted.")
    return redirect("compendium:tags")
