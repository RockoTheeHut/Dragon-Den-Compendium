from django import template

register = template.Library()


@register.filter
def tag_text_color(hex_color):
    """Pick black or near-white text for a user-chosen #RRGGBB background.

    Uses relative luminance so dark tag colors don't end up with unreadable
    dark text.
    """
    value = (hex_color or "").lstrip("#")
    if len(value) != 6:
        return "#111111"
    try:
        red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#111111"
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "#111111" if luminance > 140 else "#f5f5f5"
