from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.rendering import render_page

from .models import SCRATCHPAD_MAX_LENGTH, SharedNote

SCRATCHPAD_TITLE = "Scratchpad"


def _get_or_create_scratchpad(user):
    scratchpad = (
        SharedNote.objects.filter(
            created_by=user,
            title=SCRATCHPAD_TITLE,
            visibility=SharedNote.Visibility.PRIVATE,
        )
        .order_by("-updated_at")
        .first()
    )
    if scratchpad is not None:
        return scratchpad

    return SharedNote.objects.create(
        title=SCRATCHPAD_TITLE,
        content="",
        created_by=user,
        visibility=SharedNote.Visibility.PRIVATE,
    )


def _scratchpad_context(user, in_modal=False):
    scratchpad = _get_or_create_scratchpad(user)
    return {
        "scratchpad": scratchpad,
        "scratchpad_max_length": SCRATCHPAD_MAX_LENGTH,
        "scratchpad_remaining": max(SCRATCHPAD_MAX_LENGTH - len(scratchpad.content or ""), 0),
        "in_modal": in_modal,
    }


@login_required
def modal(request):
    template = "notes/modal_content.html"
    in_modal = bool(request.headers.get("HX-Request"))
    context = _scratchpad_context(request.user, in_modal=in_modal)

    if in_modal:
        return render(request, template, context)
    return render_page(request, template, context)


@login_required
@require_POST
def save_scratchpad(request):
    scratchpad = _get_or_create_scratchpad(request.user)
    scratchpad.content = (request.POST.get("content") or "")[:SCRATCHPAD_MAX_LENGTH]
    scratchpad.visibility = SharedNote.Visibility.PRIVATE
    scratchpad.title = SCRATCHPAD_TITLE
    scratchpad.save(update_fields=["content", "visibility", "title", "updated_at"])

    if request.headers.get("HX-Request"):
        return render(request, "notes/modal_content.html", _scratchpad_context(request.user, in_modal=True))
    return redirect("core:home")


@login_required
@require_POST
def clear_scratchpad(request):
    scratchpad = _get_or_create_scratchpad(request.user)
    scratchpad.content = ""
    scratchpad.visibility = SharedNote.Visibility.PRIVATE
    scratchpad.title = SCRATCHPAD_TITLE
    scratchpad.save(update_fields=["content", "visibility", "title", "updated_at"])

    if request.headers.get("HX-Request"):
        return render(request, "notes/modal_content.html", _scratchpad_context(request.user, in_modal=True))
    return redirect("core:home")
