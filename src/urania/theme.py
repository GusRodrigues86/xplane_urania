"""
theme.py - The Urania look: a pastel dark space theme in the colors of Uranus.

Uranus in visible light is a pale cyan / blue-green: methane in its atmosphere absorbs red light.
The palette uses those colors on a deep-space navy. All colors are here (TOKENS); gui.py uses
only these names. tests/test_theme.py checks the WCAG contrast of each text color.
"""
import math
import random
import sys

TOKENS = {
    "bg":           "#0E1220",   # window: deep-space navy
    "surface":      "#171D30",   # panels, input cards
    "surface_hi":   "#212943",   # hover, focus, drop-zone highlight
    "border":       "#2C3654",   # thin lines between parts
    "text":         "#E6F4F5",   # main text: pale icy white
    "text_muted":   "#8FA3B5",   # help text, paths
    "primary":      "#9FD8DF",   # Uranus cyan: Build button, progress, links
    "primary_soft": "#C6E9EC",   # pale Uranus haze: headings, selected state
    "primary_deep": "#5FA8B3",   # Uranus limb (darker cyan): pressed button, disc edge
    "accent":       "#7FC4C9",   # teal: card borders, ring
    "lavender":     "#B9B6E3",   # second accent: options, Advanced
    "ok":           "#A8E6CF",   # pastel green
    "warn":         "#F3D9A4",   # pastel amber
    "error":        "#F2A7B1",   # pastel rose
}

# Text colors and the backgrounds they appear on (checked for contrast in the tests).
TEXT_PAIRS = [(fg, bg) for fg in ("text", "text_muted", "primary", "primary_soft", "accent", "lavender",
                                  "ok", "warn", "error")
              for bg in ("bg", "surface", "surface_hi")] + [("bg", "primary"), ("bg", "primary_deep")]

STATUS_COLOR = {"ok": "ok", "warn": "warn", "fail": "error", "empty": "text_muted", "busy": "lavender"}


def font_family():
    if sys.platform.startswith("win"):
        return "Segoe UI"
    return "DejaVu Sans"


def mono_family():
    if sys.platform.startswith("win"):
        return "Consolas"
    return "DejaVu Sans Mono"


# --- Color math ------------------------------------------------------------------------

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def mix(a, b, t):
    """Mix 2 hex colors: t = 0 gives a, t = 1 gives b."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def relative_luminance(h):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in hex_to_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio of 2 colors (1 .. 21)."""
    la, lb = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# --- Starfield and Uranus (header picture) ------------------------------------------------

def star_colors(n=6):
    """Soft star colors from the engine's black-body table (blue-white to warm), mixed toward the text color."""
    from urania.engine.shaders import star_rgb_values
    table = star_rgb_values()
    picks = [table[k] for k in (2, 15, 30, 45, 60, 75)][:n]
    out = []
    for r, g, b in picks:
        m = max(r, g, b)
        out.append(mix(rgb_to_hex((255 * r / m, 255 * g / m, 255 * b / m)), TOKENS["text"], 0.55))
    return out


def starfield(width, height, count, seed=7):
    """Return [(x, y, radius, color)] for a calm random starfield (same seed: same stars)."""
    rnd = random.Random(seed)
    colors = star_colors()
    stars = []
    for _ in range(count):
        size = rnd.random() ** 3                      # most stars are faint and small
        color = mix(TOKENS["bg"], rnd.choice(colors), 0.35 + 0.65 * size)
        stars.append((rnd.uniform(0, width), rnd.uniform(0, height), 0.6 + 1.4 * size, color))
    return stars


def uranus_rings(radius, steps=18):
    """Return [(r, color)] from outside in: a soft cyan disc, darker at the limb (limb darkening)."""
    out = []
    for i in range(steps):
        t = i / (steps - 1)                           # 0 = limb, 1 = center
        r = radius * (1 - t * 0.92)
        color = mix(TOKENS["primary_deep"], TOKENS["primary_soft"], math.sqrt(t))
        out.append((r, color))
    return out


def apply(root):
    """Set the ttk styles for the Urania theme on a Tk root."""
    from tkinter import font as tkfont
    from tkinter import ttk

    t = TOKENS
    family = font_family()
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=family, size=10)
        except Exception:                              # font not present: keep the Tk default
            pass
    root.configure(bg=t["bg"])
    # Only for plain Tk widgets: a global "*Font" would also override the fonts of the ttk styles.
    root.option_add("*Listbox.Font", (family, 10))

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=t["bg"], foreground=t["text"], fieldbackground=t["surface"],
                bordercolor=t["border"], lightcolor=t["surface"], darkcolor=t["surface"],
                troughcolor=t["surface"], focuscolor=t["accent"], selectbackground=t["surface_hi"],
                selectforeground=t["text"], insertcolor=t["text"], font=(family, 10))
    s.configure("TFrame", background=t["bg"])
    s.configure("Card.TFrame", background=t["surface"])
    s.configure("TLabel", background=t["bg"], foreground=t["text"])
    s.configure("Card.TLabel", background=t["surface"], foreground=t["text"])
    s.configure("CardTitle.TLabel", background=t["surface"], foreground=t["primary_soft"], font=(family, 11, "bold"))
    s.configure("Muted.TLabel", background=t["surface"], foreground=t["text_muted"])
    s.configure("MutedBg.TLabel", background=t["bg"], foreground=t["text_muted"])
    s.configure("Heading.TLabel", background=t["bg"], foreground=t["primary_soft"], font=(family, 12, "bold"))
    s.configure("Link.TLabel", background=t["surface"], foreground=t["primary"], font=(family, 10, "underline"))
    for status, token in STATUS_COLOR.items():
        s.configure(f"{status}.Status.TLabel", background=t["surface"], foreground=t[token], font=(family, 10, "bold"))
        s.configure(f"{status}.Msg.TLabel", background=t["surface"], foreground=t[token])
        s.configure(f"{status}.StatusBg.TLabel", background=t["bg"], foreground=t[token])

    s.configure("TButton", background=t["surface_hi"], foreground=t["text"], borderwidth=0, padding=(12, 6),
                relief="flat")
    s.map("TButton", background=[("disabled", t["surface"]), ("pressed", t["border"]), ("active", t["border"])],
          foreground=[("disabled", t["text_muted"])])
    s.configure("Primary.TButton", background=t["primary"], foreground=t["bg"], font=(family, 11, "bold"),
                padding=(22, 10))
    s.map("Primary.TButton", background=[("disabled", t["surface_hi"]), ("pressed", t["primary_deep"]),
                                         ("active", t["primary_soft"])],
          foreground=[("disabled", t["text_muted"])])
    s.configure("Small.TButton", padding=(8, 3))

    s.configure("TCheckbutton", background=t["bg"], foreground=t["text"], indicatorbackground=t["surface"],
                indicatorforeground=t["primary"])
    s.map("TCheckbutton", background=[("active", t["bg"])], indicatorbackground=[("selected", t["surface_hi"])])
    s.configure("Lav.TCheckbutton", background=t["bg"], foreground=t["lavender"])
    s.map("Lav.TCheckbutton", background=[("active", t["bg"])])
    s.configure("TEntry", fieldbackground=t["surface"], foreground=t["text"], insertcolor=t["text"], padding=4)
    s.configure("TSpinbox", fieldbackground=t["surface"], foreground=t["text"], arrowcolor=t["primary"],
                background=t["surface_hi"], padding=3)
    s.configure("TCombobox", fieldbackground=t["surface"], foreground=t["text"], arrowcolor=t["primary"],
                background=t["surface_hi"])
    s.map("TCombobox", fieldbackground=[("readonly", t["surface"])], foreground=[("readonly", t["text"])])
    root.option_add("*TCombobox*Listbox.background", t["surface"])
    root.option_add("*TCombobox*Listbox.foreground", t["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", t["surface_hi"])
    s.configure("Horizontal.TProgressbar", background=t["primary"], troughcolor=t["surface"],
                bordercolor=t["surface"], lightcolor=t["primary"], darkcolor=t["primary"])
    s.configure("Lav.Horizontal.TScale", background=t["lavender"], troughcolor=t["surface_hi"])
    s.configure("Vertical.TScrollbar", background=t["surface_hi"], troughcolor=t["bg"], arrowcolor=t["text_muted"],
                bordercolor=t["bg"])
    return s
