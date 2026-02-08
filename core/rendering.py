from django.shortcuts import render


def render_page(request, template_name, context=None):
    context = context or {}
    if request.headers.get("HX-Request"):
        return render(request, template_name, context)

    full_context = {"page_template": template_name}
    full_context.update(context)
    return render(request, "core/page.html", full_context)
