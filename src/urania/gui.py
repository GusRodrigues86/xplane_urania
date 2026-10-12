"""
gui.py - The Urania window (Tkinter, drag and drop with tkinterdnd2).

GuiModel holds the state and the rules (no Tk: the tests use it directly).
UraniaApp draws the window and passes user actions to the model.

Layout:
    header      starfield, Uranus with its (nearly vertical) ring, "Urania"
    left        the input cards: X-Plane folder, original shader, original star file, catalog, map
    right       system check, options (screen height, airglow, advanced gains), output zip, Build, log
"""
import os
import queue
import sys
import threading
import webbrowser
from dataclasses import dataclass, field

from urania import __version__, inputs, pipeline, syscheck, theme, xplane
from urania.engine import shaders
from urania.errors import UraniaError

SLOT_KEYS = ("xplane", "xsa", "dat", "stars", "milkyway")
GAIN_KEYS = ("STAR_GAIN", "MW_GAIN", "NEBULA_GAIN", "GALAXY_GAIN")
GAIN_LABELS = {"STAR_GAIN": "Stars", "MW_GAIN": "Milky Way", "NEBULA_GAIN": "Nebulae", "GALAXY_GAIN": "Galaxies"}


# =====================================================================================
# 1. MODEL (no Tk)
# =====================================================================================

@dataclass
class Slot:
    key: str
    path: str = ""
    status: str = "empty"         # empty / ok / warn / fail
    message: str = ""
    auto: bool = False            # filled from the X-Plane folder


@dataclass
class GuiModel:
    slots: dict = field(default_factory=lambda: {k: Slot(k) for k in SLOT_KEYS})
    installs: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    screen_height: int = 1080
    airglow: bool = False
    moon: bool = True             # moonlit sky glow and moon phase (shader stages 0, 1, 2)
    gains: dict = field(default_factory=lambda: {k: shaders.DEFAULT_SETTINGS[k].value for k in GAIN_KEYS})
    out_zip: str = ""
    building: bool = False

    def __post_init__(self):
        if not self.out_zip:
            self.out_zip = os.path.join(default_out_dir(), pipeline.DEFAULT_ZIP_NAME)

    # --- inputs ---
    def set_path(self, key, path, auto=False):
        """Set and check one input. For the X-Plane folder, also find the original files."""
        slot = self.slots[key]
        slot.path, slot.auto = path or "", auto
        if not path:
            slot.status, slot.message = "empty", ""
            return slot
        if key in ("stars", "milkyway", "xsa", "dat") and os.path.isdir(path):
            slot.status, slot.message = "fail", "This is a folder. Drop the file."
            return slot
        check = inputs.SPEC_BY_KEY[key].validate(path)
        slot.status = ("warn" if check.warning else "ok") if check.ok else "fail"
        slot.message = check.message + (f"  {check.warning}" if check.warning else "")
        if key == "xplane" and check.ok:
            for k, (found, note) in inputs.autodetect(path).items():
                if found:
                    self.set_path(k, found, auto=True)
                    self.slots[k].message += f" ({note})"
                elif not self.slots[k].path or self.slots[k].auto:
                    self.slots[k] = Slot(k, "", "fail", note, auto=True)
        return slot

    def drop(self, paths):
        """Put dropped files into the right cards (by name or extension). Return the keys that changed."""
        changed = []
        for p in paths:
            key = guess_slot(p)
            if key:
                self.set_path(key, p)
                changed.append(key)
        return changed

    def find_installs(self):
        self.installs = xplane.find_installs()
        if self.installs and not self.slots["xplane"].path:
            self.set_path("xplane", self.installs[0])
        return self.installs

    # --- system ---
    def run_checks(self):
        self.checks = syscheck.run_all(os.path.dirname(self.out_zip) or None)
        return self.checks

    # --- build ---
    def problems(self):
        """Return the reasons why Build is not possible (empty list = ready)."""
        out = []
        for key in SLOT_KEYS:
            slot, spec = self.slots[key], inputs.SPEC_BY_KEY[key]
            if key == "xplane" and not slot.path and self.slots["xsa"].status == "ok" \
                    and self.slots["dat"].status == "ok":
                continue                               # the 2 originals were dropped by hand
            if slot.status in ("empty", "fail"):
                out.append(f"{spec.title}: {slot.message or 'missing'}")
        out += [f"{c.name}: {c.detail}" for c in syscheck.blocking(self.checks)]
        if not self.out_zip.lower().endswith(".zip"):
            out.append("Output: the file name must end with .zip")
        if not 240 <= int(self.screen_height) <= 8640:
            out.append("Screen height: 240 to 8640 px")
        return out

    def can_build(self):
        return not self.building and not self.problems()

    def request(self):
        overrides = {"VIEWPORT_H": int(self.screen_height), "MOON": 1.0 if self.moon else 0.0}
        overrides.update({k: float(v) for k, v in self.gains.items()})
        s = self.slots
        return pipeline.BuildRequest(
            stars=s["stars"].path, milkyway=s["milkyway"].path, out_zip=self.out_zip,
            xplane_root=s["xplane"].path or None, xsa=s["xsa"].path or None, dat=s["dat"].path or None,
            overrides=overrides, airglow=self.airglow,
            allow_any_version=s["xplane"].status == "warn")

    def reset_gains(self):
        self.gains = {k: shaders.DEFAULT_SETTINGS[k].value for k in GAIN_KEYS}


def guess_slot(path):
    name = os.path.basename(path.rstrip("/\\")).lower()
    if os.path.isdir(path):
        return "xplane"
    if name.endswith(".xsa"):
        return "xsa"
    if name.endswith(".dat") or name.endswith(".dat.original"):
        return "dat"
    if name.endswith((".json", ".tgz", ".tar.gz")):
        return "stars"
    if name.endswith(".exr"):
        return "milkyway"
    return None


def default_out_dir():
    home = os.path.expanduser("~")
    for d in (os.path.join(home, "Desktop"), os.path.join(home, "Documents"), home):
        if os.path.isdir(d):
            return d
    return os.getcwd()


# =====================================================================================
# 2. VIEW (Tk)
# =====================================================================================

def _tk_root():
    """A Tk root with drag and drop if tkinterdnd2 works, else a plain Tk root."""
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk(), True
    except Exception:                                  # missing package or no tkdnd for this platform
        import tkinter as tk
        return tk.Tk(), False


class UraniaApp:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.dnd = _tk_root()
        self.root.title(f"Urania {__version__} - night sky for X-Plane 12")
        self.root.geometry("1120x800")
        self.root.minsize(980, 700)
        theme.apply(self.root)
        self._set_icon()
        self.T = theme.TOKENS
        self.model = GuiModel(screen_height=self.root.winfo_screenheight() or 1080)
        self.events = queue.Queue()
        self.cards = {}
        self._build_ui()
        self.root.after(50, self._startup)
        self.root.after(100, self._poll)

    def _set_icon(self):
        """The Pleiades icon in the title bar and the task bar (scripts/make_icon.py draws it)."""
        from importlib import resources
        try:
            with resources.as_file(resources.files("urania").joinpath("assets", "urania.png")) as p:
                self._icon = self.tk.PhotoImage(file=str(p))          # keep a reference (Tk needs it)
            self.root.iconphoto(True, self._icon)
        except Exception:                                             # no icon: the window still works
            pass

    # --- layout ---------------------------------------------------------------------
    def _build_ui(self):
        tk, ttk, T = self.tk, self.ttk, self.T
        self.header = tk.Canvas(self.root, height=118, bg=T["bg"], highlightthickness=0)
        self.header.pack(fill="x")
        self.header.bind("<Configure>", lambda e: self._draw_header(e.width, e.height))

        body = ttk.Frame(self.root, padding=(18, 6, 18, 14))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=11, uniform="col")
        body.columnconfigure(1, weight=9, uniform="col")
        body.rowconfigure(0, weight=1)

        left = self._scroll_column(body)
        ttk.Label(left, text="1  Your files", style="Heading.TLabel").pack(anchor="w", pady=(0, 6))
        hint = "Drop files anywhere in this window, or use Browse." if self.dnd else "Use Browse to choose each file."
        ttk.Label(left, text=hint, style="MutedBg.TLabel").pack(anchor="w", pady=(0, 8))
        for key in SLOT_KEYS:
            self._card(left, key)

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        self._system_panel(right)
        self._options_panel(right)
        self._build_panel(right)

        if self.dnd:
            from tkinterdnd2 import DND_FILES
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

    def _scroll_column(self, body):
        """The left column: a frame that scrolls when the cards are taller than the window."""
        tk, ttk, T = self.tk, self.ttk, self.T
        holder = ttk.Frame(body)
        holder.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        canvas = tk.Canvas(holder, bg=T["bg"], highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)

        def on_inner(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            fits = inner.winfo_reqheight() <= canvas.winfo_height()
            if fits:
                bar.pack_forget()
                canvas.yview_moveto(0)
            elif not bar.winfo_ismapped():
                bar.pack(side="right", fill="y")
        inner.bind("<Configure>", on_inner)
        canvas.bind("<Configure>", lambda e: (canvas.itemconfigure(win, width=e.width), on_inner(e)))

        def on_wheel(e):
            if bar.winfo_ismapped():
                step = -1 if (getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4) else 1
                canvas.yview_scroll(step * 3, "units")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, lambda e: on_wheel(e) if str(e.widget).startswith(str(holder)) else None, add="+")
        return inner

    def _draw_header(self, w, h):
        c, T = self.header, self.T
        c.delete("all")
        for x, y, r, col in theme.starfield(w, h, max(40, w // 9)):
            c.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="")
        cx, cy, R = 70, h / 2 + 2, 34
        # Uranus' axis is tilted 98 deg: the ring stands nearly upright. Back half of the ring first.
        ring = (cx - 22, cy - 56, cx + 22, cy + 56)
        c.create_arc(*ring, start=90, extent=180, style="arc", outline=theme.mix(T["accent"], T["bg"], 0.35), width=2)
        for r, col in theme.uranus_rings(R):
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
        c.create_arc(*ring, start=270, extent=180, style="arc", outline=T["accent"], width=3)
        fam = theme.font_family()
        c.create_text(128, cy - 14, text="Urania", anchor="w", fill=T["primary_soft"], font=(fam, 28, "bold"))
        c.create_text(131, cy + 22, text="Real star colors, the Milky Way and deep-sky objects for X-Plane 12.4.4+",
                      anchor="w", fill=T["text_muted"], font=(fam, 10))
        c.create_line(0, h - 1, w, h - 1, fill=T["border"])

    def _card(self, parent, key):
        tk, ttk, T = self.tk, self.ttk, self.T
        spec = inputs.SPEC_BY_KEY[key]
        outer = tk.Frame(parent, bg=T["border"], padx=1, pady=1)
        outer.pack(fill="x", pady=4)
        card = ttk.Frame(outer, style="Card.TFrame", padding=(12, 8))
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)

        dot = ttk.Label(card, text="●", style="empty.Status.TLabel")
        dot.grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(card, text=spec.title, style="CardTitle.TLabel").grid(row=0, column=1, sticky="w")
        btns = ttk.Frame(card, style="Card.TFrame")
        btns.grid(row=0, column=2, sticky="e")
        if spec.url:
            ttk.Button(btns, text="Get it", style="Small.TButton",
                       command=lambda u=spec.url: webbrowser.open(u)).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Browse", style="Small.TButton",
                   command=lambda k=key: self._browse(k)).pack(side="left")

        if key == "xplane":
            self.xp_combo = ttk.Combobox(card, state="readonly")
            self.xp_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(6, 0))
            self.xp_combo.bind("<<ComboboxSelected>>", lambda e: self._set("xplane", self.xp_combo.get()))
            path_label = None
        else:
            path_label = ttk.Label(card, text="", style="Card.TLabel")
            path_label.grid(row=1, column=1, columnspan=2, sticky="w", pady=(4, 0))
        status = ttk.Label(card, text="", style="empty.Msg.TLabel", wraplength=520, justify="left")
        status.grid(row=2, column=1, columnspan=2, sticky="w", pady=(2, 0))
        where = ttk.Label(card, text=spec.where, style="Muted.TLabel", wraplength=560, justify="left")
        where.grid(row=3, column=1, columnspan=2, sticky="w", pady=(2, 0))
        card.bind("<Configure>", lambda e, a=(status, where): [w.configure(wraplength=max(200, e.width - 60))
                                                                 for w in a])
        self.cards[key] = {"dot": dot, "path": path_label, "status": status}

    def _system_panel(self, parent):
        ttk, tk, T = self.ttk, self.tk, self.T
        top = ttk.Frame(parent)
        top.pack(fill="x")
        ttk.Label(top, text="2  System check", style="Heading.TLabel").pack(side="left")
        ttk.Button(top, text="Check again", style="Small.TButton", command=self._run_checks).pack(side="right")
        self.sys_frame = tk.Frame(parent, bg=T["surface"], padx=12, pady=8)
        self.sys_frame.pack(fill="x", pady=(6, 12))
        ttk.Label(self.sys_frame, text="Checking...", style="Muted.TLabel").pack(anchor="w")

    def _options_panel(self, parent):
        ttk, tk, T = self.ttk, self.tk, self.T
        ttk.Label(parent, text="3  Options", style="Heading.TLabel").pack(anchor="w")
        box = tk.Frame(parent, bg=T["bg"])
        box.pack(fill="x", pady=(6, 4))
        ttk.Label(box, text="Screen height (px)").grid(row=0, column=0, sticky="w")
        self.screen_var = tk.StringVar(value=str(self.model.screen_height))
        ttk.Spinbox(box, from_=240, to=8640, increment=1, width=7, textvariable=self.screen_var,
                    command=self._sync_options).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(box, text="The height of the X-Plane window. The Milky Way size depends on it.",
                  style="MutedBg.TLabel").grid(row=1, column=0, columnspan=3, sticky="w")
        self.screen_var.trace_add("write", lambda *a: self._sync_options())
        self.airglow_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, text="Airglow: a faint natural glow over the full sky", variable=self.airglow_var,
                        command=self._sync_options).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.moon_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Moonlit sky: glow around the moon, real moon phase light",
                        variable=self.moon_var, command=self._sync_options).grid(row=3, column=0, columnspan=3,
                                                                                  sticky="w", pady=(2, 0))

        self.adv_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="Advanced: brightness gains", variable=self.adv_var, style="Lav.TCheckbutton",
                        command=self._toggle_adv).pack(anchor="w", pady=(6, 0))
        self.adv = tk.Frame(parent, bg=T["surface"], padx=12, pady=8)
        self.gain_vars = {}
        for i, key in enumerate(GAIN_KEYS):
            ttk.Label(self.adv, text=GAIN_LABELS[key], style="Card.TLabel").grid(row=i, column=0, sticky="w")
            var = tk.StringVar(value=f"{self.model.gains[key]:g}")
            var.trace_add("write", lambda *a: self._sync_options())
            ttk.Entry(self.adv, textvariable=var, width=8).grid(row=i, column=1, sticky="w", padx=8, pady=2)
            ttk.Label(self.adv, text=shaders.DEFAULT_SETTINGS[key].comment, style="Muted.TLabel").grid(
                row=i, column=2, sticky="w")
            self.gain_vars[key] = var
        ttk.Button(self.adv, text="Tested values", style="Small.TButton", command=self._reset_gains).grid(
            row=len(GAIN_KEYS), column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.adv_anchor = ttk.Frame(parent)
        self.adv_anchor.pack(fill="x")

    def _build_panel(self, parent):
        ttk, tk, T = self.ttk, self.tk, self.T
        ttk.Label(parent, text="4  Build", style="Heading.TLabel").pack(anchor="w", pady=(10, 0))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Zip file").pack(side="left")
        self.out_var = tk.StringVar(value=self.model.out_zip)
        self.out_var.trace_add("write", lambda *a: self._sync_options())
        ttk.Entry(row, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Save as", style="Small.TButton", command=self._choose_out).pack(side="left")

        row2 = ttk.Frame(parent)
        row2.pack(fill="x", pady=(10, 4))
        self.build_btn = ttk.Button(row2, text="Build Urania zip", style="Primary.TButton", command=self._start_build)
        self.build_btn.pack(side="left")
        self.open_btn = ttk.Button(row2, text="Show the zip", style="Small.TButton", command=self._open_out)
        self.why = ttk.Label(row2, text="", style="warn.StatusBg.TLabel", wraplength=300, justify="left")
        self.why.pack(side="left", padx=12)
        self.progress = ttk.Progressbar(parent, maximum=len(pipeline.STEPS), mode="determinate")
        self.progress.pack(fill="x", pady=(4, 4))
        self.step_label = ttk.Label(parent, text="", style="MutedBg.TLabel")
        self.step_label.pack(anchor="w")
        logf = tk.Frame(parent, bg=T["border"], padx=1, pady=1)
        logf.pack(fill="both", expand=True, pady=(6, 0))
        self.log = tk.Text(logf, height=8, bg=T["bg"], fg=T["text_muted"], insertbackground=T["text"],
                           relief="flat", wrap="word", font=(theme.mono_family(), 9), padx=8, pady=6)
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("ok", foreground=T["ok"])
        self.log.tag_configure("error", foreground=T["error"])
        self.log.tag_configure("note", foreground=T["warn"])
        self.log.configure(state="disabled")

    # --- actions --------------------------------------------------------------------
    def _startup(self):
        installs = self.model.find_installs()
        self.xp_combo.configure(values=installs)
        self._refresh_all()
        self._run_checks()
        self._write_log(f"Urania {__version__}. " + (f"Found X-Plane: {', '.join(installs)}" if installs
                                                     else "No X-Plane 12 install found: choose the folder."))

    def _run_checks(self):
        self._sync_options()

        def work():
            items = self.model.run_checks()
            self.events.put(("checks", items))
        threading.Thread(target=work, daemon=True).start()

    def _set(self, key, path):
        try:
            self.model.set_path(key, path)
        except Exception as e:                         # a validator must never close the window
            self.model.slots[key] = Slot(key, path, "fail", f"Cannot read this file ({e}).")
        self._refresh_all()

    def _browse(self, key):
        from tkinter import filedialog
        spec = inputs.SPEC_BY_KEY[key]
        if spec.is_folder:
            path = filedialog.askdirectory(title=spec.title, mustexist=True)
        else:
            types = [(spec.title, " ".join("*" + e for e in spec.extensions)), ("All files", "*")]
            path = filedialog.askopenfilename(title=spec.title, filetypes=types)
        if path:
            if key == "xplane" and path not in self.model.installs:
                self.model.installs.append(path)
                self.xp_combo.configure(values=self.model.installs)
            self._set(key, os.path.normpath(path))

    def _on_drop(self, event):
        paths = [os.path.normpath(p) for p in self.root.tk.splitlist(event.data)]
        unknown = [p for p in paths if not guess_slot(p)]
        for p in paths:
            key = guess_slot(p)
            if key == "xplane" and p not in self.model.installs:
                self.model.installs.append(p)
                self.xp_combo.configure(values=self.model.installs)
            if key:
                self._set(key, p)
        for p in unknown:
            self._write_log(f"Not an input file of Urania: {p}", "note")

    def _choose_out(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(title="Save the Urania zip", defaultextension=".zip",
                                            initialfile=os.path.basename(self.model.out_zip),
                                            initialdir=os.path.dirname(self.model.out_zip),
                                            filetypes=[("Zip file", "*.zip")])
        if path:
            self.out_var.set(os.path.normpath(path))

    def _open_out(self):
        folder = os.path.dirname(self.model.out_zip)
        if sys.platform.startswith("win"):
            os.startfile(folder)                       # noqa: S606 (opens Explorer)
        else:
            webbrowser.open("file://" + folder)

    def _toggle_adv(self):
        if self.adv_var.get():
            self.adv.pack(fill="x", pady=(4, 0), before=self.adv_anchor)
        else:
            self.adv.pack_forget()

    def _reset_gains(self):
        self.model.reset_gains()
        for k, var in self.gain_vars.items():
            var.set(f"{self.model.gains[k]:g}")

    def _sync_options(self):
        try:
            self.model.screen_height = int(self.screen_var.get())
        except (ValueError, AttributeError):
            self.model.screen_height = 0
        if hasattr(self, "airglow_var"):
            self.model.airglow = bool(self.airglow_var.get())
        if hasattr(self, "moon_var"):
            self.model.moon = bool(self.moon_var.get())
        for k, var in getattr(self, "gain_vars", {}).items():
            try:
                v = float(var.get())
                if v > 0:
                    self.model.gains[k] = v
            except ValueError:
                pass
        if hasattr(self, "out_var"):
            self.model.out_zip = self.out_var.get().strip()
        self._refresh_build()

    def _start_build(self):
        self._sync_options()
        if not self.model.can_build():
            return
        req = self.model.request()
        if os.path.exists(req.out_zip):
            from tkinter import messagebox
            if not messagebox.askyesno("Urania", f"{req.out_zip} exists. Replace it?"):
                return
        self.model.building = True
        self.progress.configure(value=0)
        self.open_btn.pack_forget()
        self._refresh_build()
        self._write_log("Build started.")

        def work():
            try:
                r = pipeline.run_build(req, log=lambda t: self.events.put(("log", t)),
                                       step=lambda n, total, title: self.events.put(("step", (n, title))))
                self.events.put(("done", r))
            except UraniaError as e:
                self.events.put(("error", str(e)))
            except Exception as e:                     # unexpected: show it, do not crash the window
                self.events.put(("error", f"Unexpected error: {type(e).__name__}: {e}"))
        threading.Thread(target=work, daemon=True).start()

    # --- events from worker threads --------------------------------------------------
    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "checks":
                    self._show_checks(data)
                elif kind == "log":
                    self._write_log(data, "note" if data.startswith("NOTE") else None)
                elif kind == "step":
                    n, title = data
                    self.progress.configure(value=n - 1)
                    self.step_label.configure(text=f"Step {n} of {len(pipeline.STEPS)}: {title}")
                elif kind == "done":
                    self.model.building = False
                    self.progress.configure(value=len(pipeline.STEPS))
                    self.step_label.configure(text="Done.")
                    self._write_log(f"Done: {data.zip_path}", "ok")
                    self._write_log("Install: close X-Plane, then extract the zip into your X-Plane 12 folder "
                                    "(the folder that contains \"Resources\"). Menu Plugins > Urania opens the "
                                    "settings.", "ok")
                    self.open_btn.pack(side="left", padx=(10, 0), after=self.build_btn)
                    self._refresh_build()
                elif kind == "error":
                    self.model.building = False
                    self.step_label.configure(text="Stopped.")
                    self._write_log(f"ERROR: {data}", "error")
                    self._refresh_build()
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    # --- refresh ---------------------------------------------------------------------
    def _refresh_all(self):
        for key in SLOT_KEYS:
            slot, card = self.model.slots[key], self.cards[key]
            card["dot"].configure(style=f"{slot.status}.Status.TLabel")
            card["status"].configure(text=slot.message, style=f"{slot.status}.Msg.TLabel")
            if card["path"] is not None:
                card["path"].configure(text=slot.path or "-")
            elif slot.path and self.xp_combo.get() != slot.path:
                if slot.path not in self.model.installs:
                    self.model.installs.append(slot.path)
                    self.xp_combo.configure(values=self.model.installs)
                self.xp_combo.set(slot.path)
        self._refresh_build()

    def _refresh_build(self):
        if not hasattr(self, "build_btn"):
            return
        problems = self.model.problems()
        self.build_btn.configure(state="normal" if self.model.can_build() else "disabled")
        if self.model.building:
            self.why.configure(text="Building... (about 30 seconds)")
        else:
            self.why.configure(text=problems[0] if problems else "")

    def _show_checks(self, items):
        ttk = self.ttk
        for w in self.sys_frame.winfo_children():
            w.destroy()
        # Passed checks: one short line (the details are in a tooltip-free log line). Problems: in full.
        passed = [it for it in items if it.status == syscheck.OK]
        if passed:
            row = ttk.Frame(self.sys_frame, style="Card.TFrame")
            row.pack(fill="x", anchor="w")
            ttk.Label(row, text="●", style="ok.Status.TLabel").pack(side="left", padx=(0, 6), anchor="n")
            ttk.Label(row, text=f"{len(passed)} checks OK: " + ", ".join(it.name for it in passed),
                      style="Card.TLabel", wraplength=420, justify="left").pack(side="left")
            self._write_log("System: " + "; ".join(f"{it.name} {it.detail}" for it in passed))
        for it in items:
            if it.status == syscheck.OK:
                continue
            row = ttk.Frame(self.sys_frame, style="Card.TFrame")
            row.pack(fill="x", anchor="w")
            ttk.Label(row, text="●", style=f"{it.status}.Status.TLabel").pack(side="left", padx=(0, 6))
            ttk.Label(row, text=f"{it.name}: {it.detail}", style="Card.TLabel").pack(side="left")
            if it.fix:
                ttk.Label(self.sys_frame, text=it.fix, style="Muted.TLabel", wraplength=420,
                          justify="left").pack(anchor="w", padx=(18, 0))
            if it.fix_command:
                ttk.Button(self.sys_frame, text="Install now", style="Small.TButton",
                           command=lambda i=it: self._run_fix(i)).pack(anchor="w", padx=(18, 0), pady=2)
        self._refresh_build()

    def _run_fix(self, item):
        self._write_log("Running: " + " ".join(item.fix_command))

        def work():
            ok, out = syscheck.run_fix(item)
            self.events.put(("log", out[-2000:]))
            self.events.put(("log", "Installed. Restart Urania." if ok else "The install did not work."))
            self.events.put(("checks", self.model.run_checks()))
        threading.Thread(target=work, daemon=True).start()

    def _write_log(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", (tag,) if tag else ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self):
        self.root.mainloop()


def main():
    try:
        app = UraniaApp()
    except Exception as e:                             # for example: no display on Linux
        print(f"Cannot open the Urania window ({e}). Use the command line: urania --help", file=sys.stderr)
        return 1
    app.run()
    return 0
