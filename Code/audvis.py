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

# Matrix Info
WIDTH = 64
HEIGHT = 32
BANDS = 64
FPS = 60
COLUMNS_PER_BAND = WIDTH // BANDS
GPIO_SLOWDOWN = 5

# Audio Config
AUDIO_DEVICE = "default"
CAVA_MAX = 65535.0
LOW_FREQ = 40.0
HIGH_FREQ = 16000.0

# Visualizer settings
GAIN = 1.65
NOISE_FLOOR = 0.018
MAX_BAR_HEIGHT = 29
ATTACK_SMOOTHING = 0.04
RELEASE_SMOOTHING = 0.07

# Color and Brightness settings
TOP_COLOR = (95, 190, 255)
BOTTOM_COLOR = (0, 18, 105)
DIAGNOSTIC_COLOR = (150, 225, 255)
BRIGHTNESS = 70

# RGB Matrix Options
options = RGBMatrixOptions()
options.rows = HEIGHT
options.cols = WIDTH
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = "adafruit-hat"
options.gpio_slowdown = GPIO_SLOWDOWN
options.brightness = BRIGHTNESS

CAVA_CONFIG_PATH = "/tmp/cava_led_matrix.conf"
CAVA_OUTPUT_PATH = "/tmp/cava_led_matrix.raw"

# Device state, running (normal) or diagnostic/frequency testing
running = True
diagnostic_mode = False


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

# Precompute blue gradient/32 blue shades
BLUE_PALETTE = [get_blue_shade(y) for y in range(HEIGHT)]

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


def check_keyboard():
    global diagnostic_mode
    global running
    if not sys.stdin.isatty():
        return

    readable, _, _ = (select.select([sys.stdin], [], [], 0))
    if not readable:
        return

    key = (sys.stdin.read(1).lower())
    if key == "d":

        diagnostic_mode = (not diagnostic_mode)
        print(
            "DIAGNOSTIC MODE:",
            (
                "ON"
                if diagnostic_mode
                else
                "OFF"
            )
        )

    elif key == "q":
        running = False

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
                r, g, b = (BLUE_PALETTE[y])
            for x in range(x_start, x_end):
                canvas.SetPixel(x, y, r, g, b)

    # Push the frame to the display
    canvas = (matrix.SwapOnVSync(canvas))
    return (strongest_band, smoothed[strongest_band])


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
    global running
    cava = None
    cava_stream = None
    last_diag_print = 0.0

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
            check_keyboard()
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