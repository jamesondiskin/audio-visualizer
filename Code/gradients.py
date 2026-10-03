# Tool to load and save gradients to gradients.txt
# Follows the same naming guidelines (Name|#rrggbb1, #rrggbb2, #rrggbbn (going from bottom to top))
# Store each gradient as 2 or more hex colors from bottom to top, with the gradient being a linear interpolation

import numpy as np

# Color conversion functions
def hex2rgb(hex_str):
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) != 6:
        raise ValueError("No such hex color exists, six digits expected")
     # Break 6 character string into three 2 character chunks at 0, 2, and 4
     # Convert to base 10
     # Use a tuple to wrap RGB together
    return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))

def rgb2hex(rgb):
    # Unpack rgb value into lowercase 2 character wide hex then group as string
    return "${:02x}{:02x}{:02x}".format(*rgb)

# Gradient analysis, parse from gradients.txt
def parseGradients(path):
    gradients = []
    with open(path) as f:
        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"): # Make sure its actually a color value
                continue
            if "|" not in line:
                print(f"[gradients], Ignore line due to improper syntax {line_num}: {raw_line!r}")
                continue
            name, colors_str = line.split("|", 1)
            hex_colors = [c.strip() for c in colors_str.split(",") if c.strip()]
            if len(hex_colors) < 2:
                print(f"[gradients] Ignore line due to improper gradient. Remember gradients need at least two colors!")
                continue
            try:
                rgb_colors = [hex2rgb(c) for c in hex_colors]
            except ValueError as e:
                print(f"[gradients] Skipping '{name} - {e}")
                continue
            gradients.append({"name": name.strip(), "colors":rgb_colors}) # Add gradient to text file
    return gradients

def saveGradients(path, gradients):
    with open(path, "w") as f:
        for g in gradients:
            hex_list = ",".join(rgb2hex(c) for c in g["colors"])
            f.write(f"{g['name']}|{hex_list}\n")

def sampleGradients(colors, t):
    # Linearly interpolate a gradient from position t (on a scale from 0 to 1)
    t = float(np.clip(t, 0.0, 1.0))
    n = len(colors)
    if n == 1:
        return colors[0]

    # Linear interpolation
    scaled = t * (n - 1) # Map normalized value from 0 to 1
    idx = int(scaled) # Find lower bounding integer index
    idx = min(idx, n - 2) # Change idx to a maximum of (n - 2) allows ((idx + 1) < (n - 1)) to always be true, so no boundary errors at t = 1.0
    frac = scaled - idx # Get the distance of points from idx to idx + 1
    # Upper and lower bounds
    color1 = colors[idx]
    color2 = colors[idx + 1]
    # Split the channels manually
    r = int(round(color1[0] + (color2[0] - color1[0]) * frac)) # RED CHANNEL
    g = int(round(color1[1] + (color2[1] - color1[1]) * frac)) # GREEN CHANNEL
    b = int(round(color1[2] + (color2[2] - color1[2]) * frac)) # BLUE CHANNEL
    return (r, g, b)

def rowColors (botRow, matrixRow, colors):
    # NEED TO MOVE SPECTRUM.PY color_for_row() function to call here instead
    frac = botRow / matrixRow
    return sampleGradients(colors, frac)