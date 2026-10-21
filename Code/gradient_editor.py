# Requirements: run pip install pillow paramiko

import os
import json
import math
import bisect
import colorsys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageDraw, ImageEnhance, ImageTk
import paramiko

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pi_config.json")
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gradients.txt")

numColors = 3        # default number of colors pulled from an album cover (adjustable in the UI)
preWidth = 560       # gradient bar width in pixels
preHeight = 36       # gradient bar height in pixels
minStops = 2
maxStops = 12
minGap = 0.02        # closest two stops can get (fraction of the bar)
exportSamples = 32   # uneven gradients are baked into this many colors (matrix rows)
wheelSize = 220

# Photoshop-like dark theme
uiBg = "#383838"
uiField = "#262626"
uiButton = "#4d4d4d"
uiButtonActive = "#636363"
uiText = "#e6e6e6"
uiDim = "#9a9a9a"
uiBorder = "#1a1a1a"
uiAccent = "#4da3ff"

barPad = 14          # horizontal padding so end markers aren't clipped
barTop = 8
stripHeight = 30     # marker strip under the bar
markerHalf = 7


def rgb2hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)

def parseHex(text):
    text = text.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None

def loadConfig():
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

def saveConfig(config):
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

def getColors(image_path, numColors=numColors):
    # Use quantization to reduce the color distribution into groups
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((500, 500))
    quantized = img.quantize(colors=numColors, method=Image.MEDIANCUT)
    palette = quantized.getpalette()[: numColors * 3]
    colors = [tuple(palette[i:i + 3]) for i in range(0, len(palette), 3)]

    # Sort by luminance (green has more perceived luminance so balance according to the weights)
    def luminance(c):
        r, g, b = c
        return 0.299 * r + 0.587 * g + 0.114 * b
    colors.sort(key=luminance)
    return colors

def evenPositions(n):
    return [i / (n - 1) for i in range(n)]

def isEven(positions):
    even = evenPositions(len(positions))
    return all(abs(p - e) < 0.002 for p, e in zip(positions, even))

def sampleStops(colors, positions, t):
    # Calculate gradient color at a normalized position such taht each stop has a color and position. Between two neighborting stops, indepdendently interpolate each RGB channel.
    # If outside the first and last stop, use nearest endpoint.
    """Color at position t (0-1). Flat before the first stop and after the last."""
    if t <= positions[0]:
        return tuple(colors[0])
    if t >= positions[-1]:
        return tuple(colors[-1])
    for i in range(len(positions) - 1):
        p0, p1 = positions[i], positions[i + 1]
        if p0 <= t <= p1:
            # Convert abs position to 0-to-1 frac
            local = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            c0, c1 = colors[i], colors[i + 1]
            return tuple(int(round(c0[k] + (c1[k] - c0[k]) * local)) for k in range(3)) # Interpolate rgb seperately
    return tuple(colors[-1])

def exportColors(colors, positions, samples=exportSamples):
    """Evenly spaced stops are written as-is. Uneven spacing is baked into
    `samples` evenly spaced colors so the Pi's evenly-spaced parser reproduces it."""
    if isEven(positions):
        return [tuple(c) for c in colors]
    return [sampleStops(colors, positions, k / (samples - 1)) for k in range(samples)]

def cleanName(name):
    return " ".join(name.replace("|", "-").split()).lstrip("# ")

# UI Nonsense
def styledButton(parent, text, command, **kw):
    opts = dict(bg=uiButton, fg=uiText, activebackground=uiButtonActive, activeforeground=uiText,
                disabledforeground=uiDim, relief="flat", bd=0, padx=12, pady=5,
                highlightthickness=0, cursor="hand2")
    opts.update(kw)
    return tk.Button(parent, text=text, command=command, **opts)

def styledEntry(parent, **kw):
    opts = dict(bg=uiField, fg=uiText, insertbackground=uiText, relief="flat",
                highlightthickness=1, highlightbackground=uiBorder, highlightcolor=uiAccent)
    opts.update(kw)
    return tk.Entry(parent, **opts)

def styledSpinbox(parent, **kw):
    opts = dict(bg=uiField, fg=uiText, insertbackground=uiText, buttonbackground=uiButton,
                relief="flat", highlightthickness=1, highlightbackground=uiBorder,
                highlightcolor=uiAccent)
    opts.update(kw)
    return tk.Spinbox(parent, **opts)

def panel(parent, title):
    return tk.LabelFrame(parent, text=title, bg=uiBg, fg=uiText, bd=1, relief="groove",
                         padx=10, pady=8)
# Color wheel stuff
_wheelCache = {}
def buildWheel():
    # Hue is angle around the center, saturation is distance from center, center is unsatured where edge is full
    # Calculate at half res then cache wheel image/mask
    """Hue/saturation wheel at full brightness plus an antialiased circular mask.
    Built once, then cached. Colors are computed at half size and upscaled."""
    if "wheel" in _wheelCache:
        return _wheelCache["wheel"], _wheelCache["mask"]
    small = wheelSize // 2
    c = small / 2
    rad = c - 1
    pixels = []
    for y in range(small):
        for x in range(small): # Pixel coords to wheel center offset
            dx, dy = x + 0.5 - c, y + 0.5 - c
            dist = math.hypot(dx, dy)
            hue = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0 # Get angle of pixel around corner
            r, g, b = colorsys.hsv_to_rgb(hue, min(dist / rad, 1.0), 1.0) # Normalize distance to 0-to-1 saturation
            pixels.append((int(r * 255), int(g * 255), int(b * 255)))
    img = Image.new("RGB", (small, small))
    img.putdata(pixels)
    wheel = img.resize((wheelSize, wheelSize), Image.BICUBIC)

    # Create grayscale mask that is downscaled to act as filter. White areas show wheel, black hide the rough corners.
    # Supersampling to smooth out the boundary.
    big = Image.new("L", (wheelSize * 4, wheelSize * 4), 0)
    ImageDraw.Draw(big).ellipse([8, 8, (wheelSize - 2) * 4, (wheelSize - 2) * 4], fill=255)
    mask = big.resize((wheelSize, wheelSize), Image.LANCZOS)

    _wheelCache["wheel"] = wheel
    _wheelCache["mask"] = mask
    return wheel, mask

class ColorWheelDialog(tk.Toplevel):
    """Click or drag on the wheel for hue + saturation, use the slider for
    brightness, or type a hex value. Click 'Current' to revert."""

    def __init__(self, parent, initial_rgb, title="Pick a Color"):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=uiBg)
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        self.original = tuple(initial_rgb)
        self._busy = False

        # Use HSV to seperate hue/sat/brightness, wheel used for hue/sat, slider for brightness
        self.hue, self.sat, self.val = colorsys.rgb_to_hsv(*(c / 255 for c in initial_rgb))
        self.hex_var = tk.StringVar()
        self.rgb_var = tk.StringVar()

        self._wheel, self._mask = buildWheel()
        bg = tuple(v // 256 for v in self.winfo_rgb(uiBg))
        self._bg = Image.new("RGB", (wheelSize, wheelSize), bg)

        body = tk.Frame(self, bg=uiBg)
        body.pack(padx=14, pady=14)

        self.canvas = tk.Canvas(body, width=wheelSize, height=wheelSize, bg=uiBg,
                                highlightthickness=0, cursor="crosshair")
        self.canvas.grid(row=0, column=0)
        self._wheel_item = self.canvas.create_image(0, 0, anchor="nw")
        self._ring_outer = self.canvas.create_oval(0, 0, 0, 0, outline="#000000", width=2)
        self._ring_inner = self.canvas.create_oval(0, 0, 0, 0, outline="#ffffff", width=1)
        self.canvas.bind("<Button-1>", self._pick)
        self.canvas.bind("<B1-Motion>", self._pick)

        side = tk.Frame(body, bg=uiBg)
        side.grid(row=0, column=1, padx=(14, 0), sticky="n")
        tk.Label(side, text="New", bg=uiBg, fg=uiDim, anchor="w").pack(fill="x")
        self.new_swatch = tk.Frame(side, width=96, height=34, bg="#000000",
                                   highlightthickness=1, highlightbackground=uiBorder)
        self.new_swatch.pack()
        self.cur_swatch = tk.Frame(side, width=96, height=34, bg=rgb2hex(self.original),
                                   highlightthickness=1, highlightbackground=uiBorder, cursor="hand2")
        self.cur_swatch.pack()
        self.cur_swatch.bind("<Button-1>", lambda e: self._set_rgb(self.original))
        tk.Label(side, text="Current (click to revert)", bg=uiBg, fg=uiDim, anchor="w").pack(fill="x")

        tk.Label(side, text="Hex", bg=uiBg, fg=uiDim, anchor="w").pack(fill="x", pady=(14, 0))
        self.hex_entry = styledEntry(side, textvariable=self.hex_var, width=11)
        self.hex_entry.pack(fill="x")
        self.hex_entry.bind("<Return>", self._apply_hex)
        self.hex_entry.bind("<FocusOut>", self._apply_hex)
        tk.Label(side, textvariable=self.rgb_var, bg=uiBg, fg=uiDim, anchor="w").pack(fill="x", pady=(6, 0))

        tk.Label(body, text="Brightness", bg=uiBg, fg=uiDim, anchor="w").grid(
            row=1, column=0, sticky="w", pady=(10, 0))
        self.scale = tk.Scale(body, from_=0, to=100, resolution=0.1, orient="horizontal",
                              showvalue=False, length=wheelSize, bg=uiBg, fg=uiText,
                              troughcolor=uiField, highlightthickness=0, bd=0,
                              activebackground=uiButtonActive, command=self._on_value)
        self.scale.grid(row=2, column=0, sticky="w")

        buttons = tk.Frame(body, bg=uiBg)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        styledButton(buttons, "Cancel", self._cancel).pack(side=tk.RIGHT, padx=(8, 0))
        styledButton(buttons, "OK", self._ok, bg=uiAccent, fg="#ffffff",
                     activebackground="#7dbbff").pack(side=tk.RIGHT)

        self._busy = True
        self.scale.set(self.val * 100)
        self._busy = False
        self._render_wheel()
        self._update()

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 40, parent.winfo_rooty() + 40))
        self.update_idletasks()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()

    def current_rgb(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.val)
        return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

    def _render_wheel(self):
        dimmed = ImageEnhance.Brightness(self._wheel).enhance(self.val)
        composed = Image.composite(dimmed, self._bg, self._mask)
        self._photo = ImageTk.PhotoImage(composed)
        self.canvas.itemconfig(self._wheel_item, image=self._photo) # Tkinter images disappear if reference gets removed by garbage collector

    def _update(self):
        rgb = self.current_rgb()
        self.new_swatch.configure(bg=rgb2hex(rgb))
        self.hex_var.set(rgb2hex(rgb))
        self.rgb_var.set("RGB  {}, {}, {}".format(*rgb))
        c = wheelSize / 2 # Convert hue -> angle and sat -> radius
        rad = c - 2
        ang = self.hue * 2 * math.pi
        mx = c + self.sat * rad * math.cos(ang)
        my = c - self.sat * rad * math.sin(ang)
        self.canvas.coords(self._ring_outer, mx - 6, my - 6, mx + 6, my + 6)
        self.canvas.coords(self._ring_inner, mx - 5, my - 5, mx + 5, my + 5)

    def _pick(self, event):
        c = wheelSize / 2
        rad = c - 2
        dx, dy = event.x - c, event.y - c
        dist = math.hypot(dx, dy)
        self.sat = min(dist / rad, 1.0) # Clamp saturation values to 1
        if dist > 0.5:
            self.hue = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0
        self._update()

    def _on_value(self, _=None):
        if self._busy:
            return
        self.val = self.scale.get() / 100.0
        self._render_wheel()
        self._update()

    def _set_rgb(self, rgb):
        self.hue, self.sat, self.val = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        self._busy = True
        self.scale.set(self.val * 100)
        self._busy = False
        self._render_wheel()
        self._update()

    def _apply_hex(self, event=None):
        rgb = parseHex(self.hex_var.get())
        if rgb is None:
            self._update()  # invalid text: put the current color back
            return
        self._set_rgb(rgb)

    def _ok(self):
        self._apply_hex()
        self.result = self.current_rgb()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

def pickColor(parent, rgb, title="Pick a Color"):
    dlg = ColorWheelDialog(parent, rgb, title)
    parent.wait_window(dlg)
    return dlg.result

def send_gradient_line_to_pi(host, username, password, remote_path, name, hex_colors_str):
    """Appends one gradient line to the Pi's gradients.txt over SFTP.
    Never reads or rewrites the rest of the file -- purely additive."""
    client = paramiko.SSHClient()
    # This is probably a mistake but this just accepts an unknown SSH key. No  identity verification so use at your own risk. Should be fine in a home setting though.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=username, password=password, timeout=10)

    sftp = client.open_sftp()
    line = f"{name}|{hex_colors_str}\n"
    with sftp.file(remote_path, "a") as f:
        f.write(line)
    sftp.close()
    client.close()

class GradientFromArtApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gradient Editor")
        self.root.configure(bg=uiBg)
        self.root.resizable(False, False)

        self.image_path = None
        self.auto_name = "Untitled"
        self.colors = [(0, 0, 0), (255, 255, 255)]
        self.positions = evenPositions(len(self.colors))
        self.selected = 0
        self.dirty = False # True once you've edited by hand
        self.drag_index = None
        self.last_count = numColors
        self._in_count = False # guards against focus-out re-entering the count handler

        self.name_var = tk.StringVar(value="Untitled")
        self.count_var = tk.StringVar(value=str(numColors))
        self.loc_var = tk.StringVar()

        # Name
        name_row = tk.Frame(root, bg=uiBg)
        name_row.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(name_row, text="Name:", bg=uiBg, fg=uiText).pack(side=tk.LEFT)
        styledEntry(name_row, textvariable=self.name_var).pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 0))

        # Gradient bar + stop markers
        self.preview_canvas = tk.Canvas(
            root, width=preWidth + barPad * 2, height=barTop + preHeight + stripHeight,
            bg=uiBg, highlightthickness=0, bd=0,
        )
        self.preview_canvas.pack(padx=12)
        self.preview_canvas.bind("<ButtonPress-1>", self.on_press)
        self.preview_canvas.bind("<B1-Motion>", self.on_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_release)
        self.preview_canvas.bind("<Double-Button-1>", self.on_double)
        self.preview_canvas.bind("<Delete>", lambda e: self.delete_selected())
        self.preview_canvas.bind("<BackSpace>", lambda e: self.delete_selected())

        caption = tk.Frame(root, bg=uiBg)
        caption.pack(fill="x", padx=12 + barPad)
        tk.Label(caption, text="bottom of bars", bg=uiBg, fg=uiDim, font=("TkDefaultFont", 8)).pack(side=tk.LEFT)
        tk.Label(caption, text="top of bars", bg=uiBg, fg=uiDim, font=("TkDefaultFont", 8)).pack(side=tk.RIGHT)

        # Stops panel
        stops = panel(root, "Stops")
        stops.pack(fill="x", padx=12, pady=(10, 6))
        row = tk.Frame(stops, bg=uiBg)
        row.pack(fill="x")
        tk.Label(row, text="Color:", bg=uiBg, fg=uiText).pack(side=tk.LEFT)
        self.color_btn = tk.Button(row, width=7, relief="solid", bd=1, cursor="hand2",
                                   command=self.edit_selected_color, highlightthickness=0)
        self.color_btn.pack(side=tk.LEFT, padx=(6, 16))
        tk.Label(row, text="Location:", bg=uiBg, fg=uiText).pack(side=tk.LEFT)
        self.loc_spin = styledSpinbox(row, from_=0, to=100, increment=1, width=6,
                                      textvariable=self.loc_var, command=self.commit_location)
        self.loc_spin.pack(side=tk.LEFT, padx=(6, 2))
        self.loc_spin.bind("<Return>", self.commit_location)
        self.loc_spin.bind("<FocusOut>", self.commit_location)
        tk.Label(row, text="%", bg=uiBg, fg=uiText).pack(side=tk.LEFT, padx=(0, 16))
        self.delete_btn = styledButton(row, "Delete", self.delete_selected)
        self.delete_btn.pack(side=tk.LEFT)
        styledButton(row, "Distribute Evenly", self.distribute_evenly).pack(side=tk.LEFT, padx=(8, 0))
        self.stops_label = tk.Label(stops, bg=uiBg, fg=uiDim, anchor="w")
        self.stops_label.pack(fill="x", pady=(8, 0))
        tk.Label(stops, text="Click below the bar to add a stop  |  drag to move  |  double-click to change color",
                 bg=uiBg, fg=uiDim, font=("TkDefaultFont", 8), anchor="w").pack(fill="x")

        # Album art panel
        art = panel(root, "Album Art")
        art.pack(fill="x", padx=12, pady=6)
        self.thumb_canvas = tk.Canvas(art, width=100, height=100, bg=uiField,
                                      highlightthickness=1, highlightbackground=uiBorder)
        self.thumb_canvas.grid(row=0, column=0, rowspan=3, padx=(0, 12))
        styledButton(art, "Choose Album Cover...", self.choose_image).grid(row=0, column=1, sticky="w")
        count_row = tk.Frame(art, bg=uiBg)
        count_row.grid(row=1, column=1, sticky="w", pady=(10, 0))
        tk.Label(count_row, text="Colors to extract:", bg=uiBg, fg=uiText).pack(side=tk.LEFT)
        self.count_spin = styledSpinbox(count_row, from_=minStops, to=maxStops, width=4,
                                        textvariable=self.count_var, command=self.on_count_changed)
        self.count_spin.pack(side=tk.LEFT, padx=(6, 0))
        self.count_spin.bind("<Return>", self.on_count_changed)
        self.count_spin.bind("<FocusOut>", self.on_count_changed)
        self.reextract_btn = styledButton(art, "Re-extract (discard edits)", self.apply_extraction)
        self.reextract_btn.grid(row=2, column=1, sticky="w", pady=(10, 0))

        # Save, send
        button_row = tk.Frame(root, bg=uiBg)
        button_row.pack(pady=(8, 12))
        styledButton(button_row, "Save Gradient", self.save_gradient).pack(side=tk.LEFT, padx=5)
        styledButton(button_row, "Send to Pi", self.send_to_pi).pack(side=tk.LEFT, padx=5)
        styledButton(button_row, "Pi Settings...", self.edit_pi_settings).pack(side=tk.LEFT, padx=5)

        self.draw_preview()
        self.sync_stop_panel()

    # Image upload
    def choose_image(self):
        path = filedialog.askopenfilename(
            title="Choose an album cover",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp")],
        )
        if not path:
            return
        
        self.image_path = path
        base = os.path.splitext(os.path.basename(path))[0]
        if self.name_var.get().strip() in ("", "Untitled", self.auto_name):
            self.name_var.set(base)
        self.auto_name = base
        self.update_thumbnail(path)
        self.apply_extraction()

    def apply_extraction(self):
        if not self.image_path:
            return
        colors = getColors(self.image_path, self.last_count)
        if len(colors) < 2:
            messagebox.showwarning("Not enough colors", "Couldn't pull at least two colors from that image.")
            return
        self.colors = colors
        self.positions = evenPositions(len(colors))
        self.selected = 0
        self.dirty = False # Warn user before changing extrraction settings
        self.draw_preview()
        self.sync_stop_panel()

    def on_count_changed(self, event=None):
        # Pop-up to confirm discarding edits will take priority, call this again while first call is awaiting answer. If calls arrive, ignore
        if self._in_count:
            return
        self._in_count = True
        try:
            self._apply_count_change()
        finally:
            self._in_count = False

    def _apply_count_change(self):
        try:
            n = int(float(self.count_var.get()))
        except ValueError:
            n = self.last_count
        n = max(minStops, min(maxStops, n))
        self.count_var.set(str(n))
        if n == self.last_count:
            return
        if self.image_path and self.dirty:
            if not messagebox.askyesno(
                "Re-extract colors?",
                "Changing the number of colors re-extracts the gradient from the "
                "album cover and discards your edits.\n\nContinue?",
            ):
                self.count_var.set(str(self.last_count))
                return
        self.last_count = n
        self.apply_extraction()

    def update_thumbnail(self, path):
        img = Image.open(path).convert("RGB")
        img.thumbnail((98, 98))
        self.thumb_photo = ImageTk.PhotoImage(img)
        self.thumb_canvas.delete("all")
        self.thumb_canvas.create_image(51, 51, image=self.thumb_photo)

    # Drawing
    def pos_to_x(self, pos):
        return barPad + pos * (preWidth - 1)

    def x_to_pos(self, x):
        return max(0.0, min(1.0, (x - barPad) / (preWidth - 1)))

    def draw_preview(self):
        c = self.preview_canvas
        c.delete("all")

        row = [sampleStops(self.colors, self.positions, x / (preWidth - 1)) for x in range(preWidth)]
        strip = Image.new("RGB", (preWidth, 1))
        strip.putdata(row)
        self.bar_photo = ImageTk.PhotoImage(strip.resize((preWidth, preHeight), Image.NEAREST))
        c.create_image(barPad, barTop, image=self.bar_photo, anchor="nw")
        c.create_rectangle(barPad - 1, barTop - 1, barPad + preWidth, barTop + preHeight,
                           outline="#d0d0d0")

        # unselected markers first so the selected one is drawn on top
        order = [i for i in range(len(self.colors)) if i != self.selected] + [self.selected]
        for i in order:
            self.draw_marker(i)

    def draw_marker(self, i):
        c = self.preview_canvas
        x = self.pos_to_x(self.positions[i])
        y = barTop + preHeight + 3
        selected = (i == self.selected)
        outline = uiAccent if selected else "#8c8c8c"
        h = markerHalf
        c.create_polygon(x, y, x + h, y + h, x + h, y + 19, x - h, y + 19, x - h, y + h,
                         fill="#e6e6e6", outline=outline, width=2 if selected else 1)
        if selected:
            c.create_polygon(x, y + 1, x + h - 1, y + h, x - h + 1, y + h, fill="#000000", outline="")
        c.create_rectangle(x - 5, y + 10, x + 5, y + 17, fill=rgb2hex(self.colors[i]), outline="#111111")

    def sync_stop_panel(self):
        rgb = self.colors[self.selected]
        self.color_btn.configure(bg=rgb2hex(rgb), activebackground=rgb2hex(rgb))
        pct = self.positions[self.selected] * 100
        self.loc_var.set(f"{pct:.1f}".rstrip("0").rstrip("."))
        n = len(self.colors)
        self.delete_btn.configure(state=tk.NORMAL if n > minStops else tk.DISABLED)
        spacing = "evenly spaced" if isEven(self.positions) else "custom spacing"
        self.stops_label.configure(text=f"{n} stops ({spacing}), selected: #{self.selected + 1}")
        self.reextract_btn.configure(state=tk.NORMAL if self.image_path else tk.DISABLED)

    # Stop editing
    def stop_at(self, x, y):
        """Index of the marker under the pointer, or None. Markers live in the strip under the bar."""
        if y < barTop + preHeight:
            return None
        best, best_dist = None, markerHalf + 2
        for i, p in enumerate(self.positions):
            d = abs(x - self.pos_to_x(p))
            if d <= best_dist:
                best, best_dist = i, d
        return best

    def clamp_position(self, i, pos):
        n = len(self.positions)
        lo = 0.0 if i == 0 else self.positions[i - 1]
        hi = 1.0 if i == n - 1 else self.positions[i + 1]
        gap = min(minGap, (hi - lo) / 4)
        lo = lo + gap if i > 0 else 0.0
        hi = hi - gap if i < n - 1 else 1.0
        return max(lo, min(hi, pos))

    def add_stop_at(self, pos):
        if len(self.colors) >= maxStops:
            self.root.bell()
            return None
        if any(abs(pos - p) < minGap for p in self.positions):
            return None
        color = sampleStops(self.colors, self.positions, pos)
        idx = bisect.bisect(self.positions, pos)
        self.positions.insert(idx, pos)
        self.colors.insert(idx, color)
        self.dirty = True
        return idx

    def on_press(self, event):
        self.preview_canvas.focus_set()
        hit = self.stop_at(event.x, event.y)
        if hit is None:
            if event.y < barTop + preHeight:
                return  # clicked the bar itself
            hit = self.add_stop_at(self.x_to_pos(event.x))
            if hit is None:
                return
        self.selected = hit
        self.drag_index = hit
        self.draw_preview()
        self.sync_stop_panel()

    def on_drag(self, event):
        i = self.drag_index
        if i is None:
            return
        pos = self.clamp_position(i, self.x_to_pos(event.x))
        if abs(pos - self.positions[i]) > 1e-9:
            self.positions[i] = pos
            self.dirty = True
            self.draw_preview()
            self.sync_stop_panel()

    def on_release(self, event):
        self.drag_index = None

    def on_double(self, event):
        self.drag_index = None
        hit = self.stop_at(event.x, event.y)
        if hit is not None:
            self.selected = hit
            self.edit_selected_color()

    def delete_selected(self):
        if len(self.colors) <= minStops:
            self.root.bell()
            return
        del self.colors[self.selected]
        del self.positions[self.selected]
        self.selected = min(self.selected, len(self.colors) - 1)
        self.dirty = True
        self.draw_preview()
        self.sync_stop_panel()

    def distribute_evenly(self):
        self.positions = evenPositions(len(self.colors))
        self.dirty = True
        self.draw_preview()
        self.sync_stop_panel()

    def edit_selected_color(self):
        i = self.selected
        rgb = pickColor(self.root, self.colors[i], f"Stop Color ({self.positions[i] * 100:.0f}%)")
        if rgb is not None and rgb != self.colors[i]:
            self.colors[i] = rgb
            self.dirty = True
        self.draw_preview()
        self.sync_stop_panel()

    def commit_location(self, event=None):
        try:
            pct = float(self.loc_var.get().strip().rstrip("%"))
        except ValueError:
            self.sync_stop_panel()
            return
        i = self.selected
        pos = self.clamp_position(i, pct / 100.0)
        if abs(pos - self.positions[i]) > 1e-9:
            self.positions[i] = pos
            self.dirty = True
        self.draw_preview()
        self.sync_stop_panel()

    # Save
    def save_gradient(self):
        name = cleanName(self.name_var.get())
        if not name:
            messagebox.showwarning("Name needed", "Give the gradient a name first.")
            return

        export = exportColors(self.colors, self.positions)
        hex_colors = ",".join(rgb2hex(c) for c in export)
        line = f"{name}|{hex_colors}\n"

        file_exists = os.path.exists(output_path)
        with open(output_path, "a") as f:
            if not file_exists:
                f.write("# gradients.txt — one gradient per line\n")
                f.write("# format: Name|#rrggbb,#rrggbb,...  (bottom color first, top color last)\n")
            f.write(line)

        note = "" if isEven(self.positions) else f"\n\n(Custom spacing was baked into {len(export)} evenly spaced colors.)"
        messagebox.showinfo("Saved", f"Saved '{name}' to {output_path}{note}")

    def edit_pi_settings(self):
        config = loadConfig()

        host = simpledialog.askstring(
            "Pi Settings", "Pi hostname or IP:", initialvalue=config.get("host", "")
        )
        if host is None:
            return
        username = simpledialog.askstring(
            "Pi Settings", "SSH username:", initialvalue=config.get("username", "")
        )
        if username is None:
            return
        default_path = config.get("remote_path") or f"/home/{username}/audio-vis/scripts/gradients.txt"
        remote_path = simpledialog.askstring(
            "Pi Settings",
            "Full path to gradients.txt on the Pi:",
            initialvalue=default_path,
        )
        if remote_path is None:
            return

        saveConfig({"host": host, "username": username, "remote_path": remote_path})
        messagebox.showinfo("Saved", "Pi connection settings saved.\n(Password is never saved -- you'll enter it each time you send.)")

    def send_to_pi(self):
        name = cleanName(self.name_var.get())
        if not name:
            messagebox.showwarning("Name needed", "Give the gradient a name first.")
            return

        config = loadConfig()
        if not config.get("host") or not config.get("username") or not config.get("remote_path"):
            messagebox.showinfo("Setup needed", "Set up your Pi's connection details first.")
            self.edit_pi_settings()
            config = loadConfig()
            if not config.get("host"):
                return

        password = simpledialog.askstring("Pi Password", f"SSH password for {config['username']}@{config['host']}:", show="*")
        if password is None:
            return

        hex_colors_str = ",".join(rgb2hex(c) for c in exportColors(self.colors, self.positions))

        try:
            send_gradient_line_to_pi(
                config["host"], config["username"], password, config["remote_path"],
                name, hex_colors_str,
            )
            messagebox.showinfo("Sent", f"'{name}' added to gradients.txt on the Pi.\n\nIt'll show up next time the visualizer cycles or reloads gradients.")
        except Exception as e:
            messagebox.showerror("Send failed", f"Couldn't reach the Pi:\n\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = GradientFromArtApp(root)
    root.mainloop()
