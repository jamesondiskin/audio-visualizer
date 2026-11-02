# TO STARTSTOP THIS SERVICE, run sudo systemctl [stop/start] audiovis.service after initially running python3 audvis.py

import os
import time
import struct
import signal
import subprocess
import sys
import select
import termios
import tty
import math
from rgbmatrix import RGBMatrix, RGBMatrixOptions
import numpy as np
import sounddevice as sd
from gradients import parseGradients, sampleGradients
from ripper import Ripper
from display_text import loadFont, drawUI

# Working on developing a breakout board implementation for physical button control over I2C, for now this flag is used for simulating the controls via keyboard and mouse
simControls = True
# Add if statement for moving controls over based on hardware
# Once the hardware info is filled in and the code is complete, remember to import Controls function from the hardware code

# Matrix Info
WIDTH = 64
HEIGHT = 32
BANDS = 64
FPS = 60
COLUMNS_PER_BAND = WIDTH // BANDS
GPIO_SLOWDOWN = 7

# Audio Config
AUDIO_DEVICE = "default"
CAVA_MAX = 65535.0
LOW_FREQ = 40.0
HIGH_FREQ = 16000.0

# Visualizer settings
GAIN = 1.65
NOISE_FLOOR = 0.018 # Need to add configurability via encoder
NOISE_FLOOR_MIN = 0.0
NOISE_FLOOR_MAX = 0.06
NOISE_FLOOR_STEP = 0.002
MAX_BAR_HEIGHT = 29
ATTACK_SMOOTHING = 0.04
RELEASE_SMOOTHING = 0.07 # Need to play with these timings a bit more to nail them in

# Color and Brightness settings
TOP_COLOR = (95, 190, 255) # Old, but default
BOTTOM_COLOR = (0, 18, 105)
DIAGNOSTIC_COLOR = (150, 225, 255)
BRIGHTNESS = 70
MIN_BRIGHT = 10
MAX_BRIGHT = 100
STEP_BRIGHT = 5
gradientsFile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gradients.txt")

# Ripper audio capture
RIPPER_NAME = "AudioBox"
RIPPER_SR = 44100 # Sample Rate
RIPPER_BS = 1024 # Block Size

# RGB Matrix Options
options = RGBMatrixOptions()
options.rows = HEIGHT
options.cols = WIDTH
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = "adafruit-hat"
options.gpio_slowdown = GPIO_SLOWDOWN
options.brightness = BRIGHTNESS
options.drop_privileges = False

CAVA_CONFIG_PATH = "/tmp/cava_led_matrix.conf"
CAVA_OUTPUT_PATH = "/tmp/cava_led_matrix.raw"

# Device state, running (normal) or diagnostic/frequency testing
running = True
diagnostic_mode = False
ripper_mode = False
deltaBright = 0 # Brightness
deltaGrad = 0 # Gradient
gradient_pressed = False
deltaSens = 0 # Sensitivity

def signal_handler(signum, frame): # Stop running when terminate signal received
    global running
    running = False

signal.signal(
    signal.SIGINT, # Signal interrupt (for the exit state, receives that signal, program exits) to avoid KeyboardInterrupt
    signal_handler
)

signal.signal(
    signal.SIGTERM, # Signal terminate for anything other than ^C to terminate
    signal_handler
)

# Initialize the matrix
matrix = RGBMatrix(
    options=options
)
canvas = matrix.CreateFrameCanvas()

# Once matrix is initialized, load gradient state and then allow for ripper mode
# Gradient state loader
gradients = parseGradients(gradientsFile)
currentGradientIndex = 0
currentBrightness = BRIGHTNESS

# Ripper state loader, creates once then loads the audio stream when the mode is entered
ripper = Ripper(output_format="FLAC")
ripper_font = loadFont()
ripper_stream = None
cava = None
cava_stream = None

realControl = None
#if not simControls:
#    realControl = Controls() PLACEHOLDER, to be implemented once software is feature complete and more fleshed out hardware dev begins

# Just ensure that the values stay within range. If too low, pulled to min or too high, pulled to max. Otherwise just keep the value.
def clamp(
    value, minimum,maximum
):
    return max(minimum, min(maximum,value))

# Frequency band information
def get_band_frequency_range(
    band
):
    ratio = (HIGH_FREQ / LOW_FREQ)
    low = (LOW_FREQ * (ratio**(band/BANDS)))
    high = (LOW_FREQ * (ratio**((band+1)/BANDS)))
    return(low, high)
def get_band_center_frequency(band):
    low, high = (get_band_frequency_range(band))
    return math.sqrt(low*high)

# Print band table
def print_frequency_table():
    print("APPROXIMATE BAND FREQUENCIES\n")
    for band in range(BANDS):
        low, high = (get_band_frequency_range(band)) # Bass and treble
        center = (get_band_center_frequency(band)) # Mids

        x1 = (band * COLUMNS_PER_BAND)
        x2 = (x1 + COLUMNS_PER_BAND - 1)

        print(
            f"Band {band:02d} "
            f"| LEDs {x1:02d}-{x2:02d} "
            f"| {low:7.0f}-{high:7.0f} Hz "
            f"| center ~{center:7.0f} Hz]"
        )

# Create CAVA config
def create_cava_config():

    config = f"""
[general]
bars = {BANDS}
framerate = {FPS}

autosens = 0
sensitivity = 3200

lower_cutoff_freq = {int(LOW_FREQ)}
higher_cutoff_freq = {int(HIGH_FREQ)}

[input]
method = alsa
source = {AUDIO_DEVICE}

[output]
method = raw
raw_target = {CAVA_OUTPUT_PATH}
data_format = binary
bit_format = 16bit
channels = mono
mono_option = average
"""
    with open(CAVA_CONFIG_PATH, "w") as file: file.write(config)
    os.chmod(CAVA_CONFIG_PATH, 0o644)


# Start CAVA
def start_cava():
    clean_temp_files()
    create_cava_config()

    print(
        "64x32 CAVA LED Visualizer\n"
        f"Audio device : {AUDIO_DEVICE}\n"
        f"Bands: {BANDS}\n"
        f"Matrix: {WIDTH}x{HEIGHT}\n"
        f"FPS: {FPS}\n"
        f"Noise floor: {NOISE_FLOOR}\n"
        f"\n"
        "Controls:\n"
        "d - diagnostic mode\n"
        "q - quit\n"
    )

    print_frequency_table()
    print("Starting CAVA...")
    process = subprocess.Popen(["cava", "-p", CAVA_CONFIG_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return process

# Wait for CAVA output
def wait_for_cava(
    process,
    timeout=10
):
    start_time = (time.monotonic())

    while running:
        if os.path.exists(CAVA_OUTPUT_PATH):
            print("CAVA output ready.")
            return True

        if process.poll() is not None:
            print("ERROR: CAVA stopped unexpectedly.")
            try:
                error = (process.stderr.read().decode("utf-8", errors="replace"))
                print(error)

            except Exception:
                pass

            return False

        if ((time.monotonic() - start_time) > timeout):
            print("Error: Timed out waiting for CAVA")
            return False

        time.sleep(0.05)
    return False

# Blue shade by display height
def get_blue_shade(y):
    # y = 0 is light blue, y = 31 is dark blue
    position = (y/(HEIGHT - 1))
    r = (TOP_COLOR[0] + (BOTTOM_COLOR[0] - TOP_COLOR[0]) * position)
    g = (TOP_COLOR[1] + (BOTTOM_COLOR[1] - TOP_COLOR[1]) * position)
    b = (TOP_COLOR[2] + (BOTTOM_COLOR[2] - TOP_COLOR[2]) * position)
    return (int(r), int(g), int(b))

# Palette generator based on the same logic the blue shade above but from the gradient list file.
# y = 0 is the top of the panel so that corresponds to the last color in the gradient (inverted). Flipped for the bottom colors(y = height - 1 corresponds to first in gradient)
def makePalette(colors):
    palette = []
    for y in range(HEIGHT):
        position =  1.0 - (y / (HEIGHT - 1))
        palette.append(sampleGradients(colors, position))
    return palette
# Set that palette to be active
activePalette = makePalette(gradients[currentGradientIndex]["colors"])

# Process one audio band
def process_value(raw_value, previous_value):
    #Convert 0-65535 to 0.0-1.0
    value = (raw_value / CAVA_MAX)

    # Noise Gate
    if value <= NOISE_FLOOR:
        value = 0.0
    else:
        value = (value - NOISE_FLOOR) / (1.0 - NOISE_FLOOR)

    # Gain
    value *= (GAIN)
    value = clamp(value, 0.0, 1.0)

    # Attack and release smoothing
    if value > previous_value:
        smoothing = (ATTACK_SMOOTHING)
    else:
        smoothing = (RELEASE_SMOOTHING)

    value = (previous_value * smoothing + value * (1.0 - smoothing))
    return value

# Terminal keyboard control
def setup_keyboard():
    global old_terminal_settings
    if not sys.stdin.isatty(): return
    old_terminal_settings = (termios.tcgetattr(sys.stdin))
    tty.setcbreak(sys.stdin.fileno())


def restore_keyboard():
    # If settings found (old terminal settings has data in it), use those
    if (old_terminal_settings is not None and sys.stdin.isatty()):
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_terminal_settings)

# Needs to be overhauled when hardware buttons are added
def check_keyboard():
    global diagnostic_mode
    global running
    global ripper_mode, deltaBright, deltaGrad, gradient_pressed, deltaSens
    if not sys.stdin.isatty():
        return
    readable, _, _ = (select.select([sys.stdin], [], [], 0))
    if not readable:
        return
    raw_key = sys.stdin.read(1)

    if raw_key.lower() == "d":
        diagnostic_mode = (not diagnostic_mode)
        print("DIAGNOSTIC MODE: ",("ON" if diagnostic_mode else "OFF"))
    elif raw_key.lower() == "q":
        running = False

    elif not simControls:
        pass

    # Change brightness
    elif raw_key.lower() == "b":
        deltaBright = -1
    elif raw_key.lower() == "n":
        deltaBright = 1
    # Change gradient
    elif raw_key.lower() == "g":
        deltaGrad = -1
    elif raw_key.lower() == "h":
        deltaGrad = 1
    elif raw_key.lower() == "k":
        gradient_pressed = True
    # Sensitivity
    elif raw_key.lower() == "y":
        deltaSens = -1
    elif raw_key.lower() == "u":
        deltaSens = 1
    # Ripper mode
    elif raw_key.lower() == "r":
        ripper_mode = (not ripper_mode)
        print("RIPPER MODE: ", "ON" if ripper_mode else "OFF")

def pollControls():
    global deltaBright, deltaGrad, deltaSens, gradient_pressed, ripper_mode
    check_keyboard()

    if not simControls:
        ctrl = realControl.poll()
        deltaBright = ctrl["deltaBright"]
        deltaGrad = ctrl["deltaGrad"]
        deltaSens = ctrl["deltaSens"]
        gradient_pressed = ctrl["gradient_pressed"]
        ripper_mode = ctrl["ripper mode"]

# Draw the visualizer
def draw_visualization(values, smoothed):

    global canvas
    canvas.Clear()

    # Process all bands
    for band in range(BANDS):
        smoothed[band] = (process_value(values[band], smoothed[band]))
        smoothed[band] = (smoothed[band])

    # Find most intense band for use in diag mode
    strongest_band = max(range(BANDS), key = lambda i: smoothed[i])

    # Do the actual visualization
    for band in range(BANDS):
        value = (smoothed[band])
        # Vertical height
        bar_height = int(round(value * MAX_BAR_HEIGHT))
        bar_height = clamp(bar_height, 0, MAX_BAR_HEIGHT)
        if bar_height <= 0:
            continue

        # Horizontal position
        x_start = (band * COLUMNS_PER_BAND) # Board used for testing is 64x32 but this allows it to scale to other LED matrices
        x_end = (x_start + COLUMNS_PER_BAND)

        # Vertical position
        top_y = (HEIGHT - bar_height)

        # Add continuity
        for y in range(top_y, HEIGHT):
            if (diagnostic_mode and band == strongest_band):
                r, g, b = (DIAGNOSTIC_COLOR)
            else:
                r, g, b = (activePalette[y])
            for x in range(x_start, x_end):
                canvas.SetPixel(x, y, r, g, b)

    # Push the frame to the display
    canvas = (matrix.SwapOnVSync(canvas))
    return (strongest_band, smoothed[strongest_band])

# Ripper GUI frame
def drawRipFrame():
    global canvas
    drawUI(canvas, ripper_font, ripper.status(), ripper.output_format)
    canvas = matrix.SwapOnVSync(canvas)

# Ripper audio callback
def ripAudioCall(indata, frames, time_info, status):
    if status:
        print(status)
    ripper.process_block(indata)

# Find the device name for the ripper
def deviceID(name_hint):
    for i in range(32):
        try:
            info = sd.query_devices(i)
        except Exception:
            continue
        if info.get("max_input_channels", 0) > 0 and name_hint.lower() in info["name"].lower():
            print(f"[ripper] Using audio device #{i}: {info['name']}")
            return i
    raise RuntimeError(f"No input device found")

# Ripper mode
# The two audio streams (CAVA and the ripper are independent of each other and only one runs at a time)
# This prevents two parallel processes modifying the same USB audio device
def enterRip():
    global cava, cava_stream, ripper_stream
    # Nuke Cava
    print("Current mode: RIPPER")
    stop_cava(cava)
    # Really try to nuke Cava
    if cava_stream is not None:
        try:
            cava_stream.close()
        except Exception:
            pass
    cava = None
    cava_stream = None
    time.sleep(2)
    # Initialize ripper device
    device_index = deviceID(RIPPER_NAME)
    ripper_stream = sd.InputStream(
        device=device_index,
        channels=2,
        samplerate=RIPPER_SR,
        blocksize=RIPPER_BS,
        callback=ripAudioCall
    )
    ripper_stream.start()

def exitRip():
    global cava, cava_stream, ripper_stream
    print("Leaving Ripper Mode")
    if ripper_stream is not None:
        ripper_stream.stop()
        ripper_stream.close()
        ripper_stream = None

    cava = start_cava()
    if not wait_for_cava(cava):
        print("Error: CAVA failed to restart")
        return
    cava_stream = open(CAVA_OUTPUT_PATH, "rb", buffering=0)
    print("Current mode: VISUALIZER")

# Read one CAVA frame
def read_exact(stream, size):
    data = bytearray()
    while (running and len(data) < size):
        chunk = stream.read(size - len(data))
        if not chunk: return None
        data.extend(chunk)
    if len(data) != size: return None
    return bytes(data)

# Clear/reset the matrix
def clear_matrix():
    global canvas
    try:
        canvas.Clear()
        canvas = (matrix.SwapOnVSync(canvas))
    except Exception: pass


# Stop CAVA
def stop_cava(
    process
):

    if process is None: return

    try:
        process.terminate()
        process.wait(timeout = 2)

    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass
    except Exception:
        pass

# Clean temp files
def clean_temp_files():
    for path in (CAVA_CONFIG_PATH, CAVA_OUTPUT_PATH):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError: pass

# Main
def main():
    global running, ripper_mode
    global deltaBright, deltaGrad, deltaSens
    global gradient_pressed, currentGradientIndex, currentBrightness, activePalette
    global NOISE_FLOOR
    global cava, cava_stream
    cava = None
    cava_stream = None
    last_diag_print = 0.0
    was_ripper_mode = False

    try:
        setup_keyboard()
        # Start CAVA
        cava = (start_cava())
        if not wait_for_cava(cava):
            return
        # Open CAVA binary output
        print("Opening CAVA stream...")
        cava_stream = open(CAVA_OUTPUT_PATH, "rb", buffering=0)
        print("\nVisualizer running.")

        # 32 bands * 16 bits = 64 bytes
        frame_size = (BANDS * 2)
        unpack_format = ("<" + ("H" * BANDS))
        smoothed = [0.0] * BANDS

        # Time to do the actual loop
        while running:
            pollControls()
            # Switch logic between modes
            if ripper_mode != was_ripper_mode:
                if ripper_mode:
                    enterRip()
                else:
                    exitRip()
                was_ripper_mode = ripper_mode

            if ripper_mode:
                if gradient_pressed:
                    ripper.manualStart()
                    gradient_pressed = False
                if deltaGrad != 0:
                    ripper.set_format("WAV" if ripper.output_format == "FLAC" else "FLAC")
                    deltaGrad = 0

                drawRipFrame()
                time.sleep(1.0 / FPS)
                continue

            # Visualizer mode
            if deltaBright != 0:
                currentBrightness = int(clamp(currentBrightness + deltaBright * STEP_BRIGHT, MIN_BRIGHT, MAX_BRIGHT,))
                matrix.brightness = currentBrightness
                deltaBright = 0

            if deltaGrad != 0:
                reGradient = parseGradients(gradientsFile)
                if deltaGrad > 0:
                    currentGradientIndex = (currentGradientIndex + 1) % len(reGradient)
                else:
                    currentGradientIndex = (currentGradientIndex - 1) % len(reGradient)
                activePalette = makePalette(reGradient[currentGradientIndex]["colors"])
                print(f"Gradient: {reGradient[currentGradientIndex]['name']}")
                deltaGrad = 0

            if deltaSens != 0:
                NOISE_FLOOR = clamp(NOISE_FLOOR + deltaSens + NOISE_FLOOR_STEP, NOISE_FLOOR_MIN, NOISE_FLOOR_MAX,)
                print(f"Noise floor: {NOISE_FLOOR:.3f}")
                sensitivty_delta = 0
            
            # Quadruple check that CAVA is actually running
            if cava.poll() is not None:
                print("\nERROR: CAVA stopped.")
                try:
                    error = (cava.stderr.read().decode("utf-8", errors="replace"))
                    print(error)

                except Exception: pass
                break

            # Read a single frame
            data = read_exact(
                cava_stream,
                frame_size
            )
            if data is None:
                if running:
                    print("CAVA stream ended.")
                break
            values = struct.unpack(unpack_format, data)

            # Draw
            strongest_band, strength = (draw_visualization(values, smoothed))

            # Diagnostic information
            if diagnostic_mode:
                now = (time.monotonic())
                if (now - last_diag_print >= 0.25):
                    low, high = (get_band_frequency_range(strongest_band))
                    center = (get_band_center_frequency(strongest_band))
                    print(
                        f"\r"
                        f"Band {strongest_band:02d} | "
                        f"{low:6.0f}-{high:6.0f} Hz | "
                        f"center {center:6.0f} Hz | "
                        f"level {strength:0.3f}      ",
                        end="",
                        flush=True
                    )
                    last_diag_print = (now)

    except KeyboardInterrupt: running = False
    except Exception as error:
        print("ERROR:")
        print(error)

    finally:
        running = False
        restore_keyboard()
        print("Shutting down")
        # Close output
        if cava_stream is not None:
            try:
                cava_stream.close()
            except Exception: pass
        # Terminate CAVA
        stop_cava(cava)
        clear_matrix()
        clean_temp_files()
        print("Program successfully stopped")

# Run the script
if __name__ == "__main__":
    main()
