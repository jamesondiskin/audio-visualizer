import os
import sys
import time
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

script_dir = os.path.dirname(os.path.abspath(__file__))
font_path = os.path.abspath(os.path.join(script_dir, "../rpi-rgb-led-matrix/fonts/5x7.bdf"))
standby_color = (60, 60, 60)
record_color = (255, 0, 0)
selected_color = (0, 224, 108)
unselected_color = (189, 183, 177)
title_color = (0, 143, 245)

def loadFont():
    font = graphics.Font()
    print("DEBUG cwd:", os.getcwd())
    print("DEBUG __file__:", __file__)
    print("DEBUG font_path:", font_path)
    print("DEBUG exists:", os.path.exists(font_path))
    if not os.path.exists(font_path):
        print(f"No font path found")
        sys.exit(1)
    font.LoadFont(font_path)
    return font

def drawUI(canvas, font, status, selected_format):
    """
    status: "STANDBY" or "REC"
    selected_format: "WAV" or "FLAC"
    """
    canvas.Clear()

    graphics.DrawText(canvas, font, 4, 8, graphics.Color(*title_color), "RIP MODE")
    status_color = record_color if status == "REC" else standby_color
    graphics.DrawText(canvas, font, 4, 17, graphics.Color(*status_color), status)
    wav_color = selected_color if selected_format == "WAV" else unselected_color
    flac_color = selected_color if selected_format == "FLAC" else unselected_color
    graphics.DrawText(canvas, font, 4, 27, graphics.Color(*wav_color), "WAV")
    graphics.DrawText(canvas, font, 34, 27, graphics.Color(*flac_color), "FLAC")

def main():
    options = RGBMatrixOptions()
    options.rows = 32
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.hardware_mapping = 'adafruit-hat'
    options.gpio_slowdown = 2
    options.drop_privileges = False

    matrix = RGBMatrix(options=options)
    offscreen_canvas = matrix.CreateFrameCanvas()
    font = loadFont()

    status = "STANDBY"
    selected_format = "WAV"
    print("Press Ctrl + C to stop")
    try:
        while True:
            drawUI(offscreen_canvas, font, status, selected_format)
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
            time.sleep(0.05)
    except KeyboardInterrupt:
        matrix.Clear()
        print("\nDisplay cleared")

if __name__ == "__main__":
    main()