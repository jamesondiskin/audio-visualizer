import sys, time, signal, select, termios, tty
from rgbmatrix import RGBMatrix, RGBMatrixOptions

# matrix settings
width = 64
height = 32
test_duration = 0.5 # measured in seconds

# convert settings to config
options = RGBMatrixOptions()
options.cols = width
options.rows = height
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = "adafruit-hat"
options.gpio_slowdown = 5
options.brightness = 40
matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()
old_terminal_settings = None

running = True
skip_requested = False

def setup_keyboard():
    global old_terminal_settings
    if not sys.stdin.isatty():
        return
    old_terminal_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

def restore_keyboard():
    if old_terminal_settings is not None and sys.stdin.isatty():
        termios.tcsetattr(sys.stdin,termios.TCSADRAIN, old_terminal_settings)

def check_keyboard():
    global running, skip_requested
    if not sys.stdin.isatty():
        return
    readable, _, _ = select.select([sys.stdin], [], [], 0)
    if not readable:
        return
    key = sys.stdin.read(1).lower()
    if key == "q":
        running = False
    if key == "w":
        skip_requested = True

def test(seconds):
    global skip_requested
    start = time.monotonic()
    while running and not skip_requested:
        check_keyboard()
        if time.monotonic() - start >= seconds:
            return
        time.sleep(0.02)
    skip_requested = False

def push(cv):
    global canvas
    canvas = matrix.SwapOnVSync(cv)
    return canvas

def clear():
    global canvas
    canvas.Clear()
    canvas = push(canvas)

def solidColor():
    print("solid color test, rgbw")
    colors = [
        ("RED", (255, 0, 0)),
        ("GREEN", (0, 255, 0)),
        ("BLUE", (0, 0, 255)),
        ("WHITE", (254, 254, 254)),
    ]
    for name, (r, g, b) in colors:
        print(f"testing {name}")
        canvas.Clear()
        for y in range(height):
            for x in range(width):
                canvas.SetPixel(x, y, r, g, b)
        push(canvas)
        test(test_duration)
        if not running or skip_requested:
            return

def corner():
    canvas.Clear()
    markers = {
        "top-L": (0, 0, (255, 0, 0)),
        "bot-L": (0, height - 1, (0, 255, 0)),
        "top-R": (width - 1, 0, (0, 0, 255)),
        "bot-R": (width - 1, height - 1, (255, 255, 0)),
    }
    for label, (x, y, color) in markers.items():
        for dx in range(3):
            for dy in range(3):
                px = x - dx if x != 0 else x + dx
                py = y - dy if y != 0 else y + dy
                if 0 <= px < width and 0 <= py < height:
                    canvas.SetPixel(px, py, *color)
    # make center
    cx = width // 2
    cy = height // 2
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            canvas.SetPixel(cx + dx, cy + dy, 255, 255, 255)
    push(canvas)
    test(test_duration)

def checker():
    canvas.Clear()
    for y in range(height):
        for x in range(width):
            if (x + y) % 2 == 0:
                canvas.SetPixel(x, y, 255, 255, 255)
    push(canvas)
    test(test_duration)

def hori():
    for x in range(width):
        if not running or skip_requested:
            break
        check_keyboard()
        canvas.Clear()
        for y in range(height):
            canvas.SetPixel(x, y, 255, 0, 0)
        push(canvas)
        time.sleep(0.06)

def vert():
    for y in range(height):
        if not running or skip_requested:
            break
        check_keyboard()
        canvas.Clear()
        for x in range(width):
            canvas.SetPixel(x, y, 0, 255, 0)
        push(canvas)
        time.sleep(0.06)

def brightCheck():
    canvas.Clear()
    for x in range(width):
        level = int(255 * (x / (width - 1)))
        for y in range(height):
            canvas.SetPixel(x, y, level, level, level)
    push(canvas)
    test(test_duration)

def gradient():
    canvas.Clear()
    for y in range(height):
        for x in range(width):
            r = int(255*(x/(width-1)))
            g = int(255*(y/(height-1)))
            b = 255 - r
            canvas.SetPixel(x, y, r, g, b)
    push(canvas)
    test(test_duration)

tests = [solidColor, corner, checker, hori, vert, brightCheck, gradient]

def main():
    global running, skip_requested
    print("Running Matrix Test")
    print(f"Matrix: {width}x{height}")

    try:
        setup_keyboard()
        for test_fn in tests:
            if not running:
                break
            skip_requested = False
            test_fn()
            if not running:
                break
            if running:
                print("Done")
    except Exception as error:
        print("Error:")
        print(error)
    finally:
        running = False
        restore_keyboard()
        try:
            canvas.Clear()
            push(canvas)
        except Exception:
            pass

if __name__ == "__main__":
    main()