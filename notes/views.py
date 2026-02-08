from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.rendering import render_page

from .forms import SharedNoteForm
from .models import SharedNote


def _notes_context(user):
    return {
        "notes": SharedNote.objects.visible_to(user),
        "form": SharedNoteForm(),
    }


@login_required
def modal(request):
    template = "notes/modal_content.html"
    context = _notes_context(request.user)

    if request.headers.get("HX-Request"):
        return render(request, template, context)
    return render_page(request, template, context)


@login_required
@require_POST
def create_note(request):
    form = SharedNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.created_by = request.user
        note.save()

    if request.headers.get("HX-Request"):
        return render(request, "notes/modal_content.html", _notes_context(request.user))
    return redirect("core:home")


@login_required
@require_POST
def update_note(request, pk):
    note = get_object_or_404(SharedNote, pk=pk)
    if note.created_by != request.user:
        return HttpResponseForbidden("Only the note creator can edit this note.")

    form = SharedNoteForm(request.POST, instance=note)
    if form.is_valid():
        form.save()

    if request.headers.get("HX-Request"):
        return render(request, "notes/modal_content.html", _notes_context(request.user))
    return redirect("core:home")


@login_required
@require_POST
def delete_note(request, pk):
    note = get_object_or_404(SharedNote, pk=pk)
    if note.created_by != request.user:
        return HttpResponseForbidden("Only the note creator can delete this note.")
    note.delete()

    if request.headers.get("HX-Request"):
        return render(request, "notes/modal_content.html", _notes_context(request.user))
    return redirect("core:home")
