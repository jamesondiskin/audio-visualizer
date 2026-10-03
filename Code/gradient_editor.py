""" Make the gradients on the Pi directly, seperate from the cover-to-gradient converter that runs on a seperate PC and gets sent over.
In order to use this properly on the matrix, run `sudo systemctl stop audiovis.service`. When done, you can re-enable it with `sudo systemctl start audiovis.service`
Otherwise, it can be viewed from the terminal at any time, although the colors may not match the matrix with complete accuracy """

import os
import time
from gradients import hex2rgb, parseGradients, saveGradients, sampleGradients
gradientFile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gradients.txt") 

def fileCheck():
    if not os.path.exists(gradientFile):
        with open(gradientFile, "w") as f:
            f.write("# One gradient per line\n")
            f.write("# Must be formatted as Name|#rrggbb1, #rrggbb2, #rrggbbn (going from bottom to top)\n") # Make the file if it doesn't exist

def terminalPreview(colors, width=40):
    # Show gradient with 24-bit terminal color codes
    line = ""
    for i in range(width):
        t = i / (width - 1)
        r, g, b = sampleGradients(colors, t)
        line += f"\033[48;2;{r};{g};{b}m \033[0m"
    print(line)

def matrixPreview(colors, seconds=5):
    # Display bottom-to-top, fully cover the matrix
    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
    except ImportError:
        print("Could not import RGBMatrix files")
        return

    # Matrix properties
    numRows = 32
    numCols = 64
    options = RGBMatrixOptions()
    options.rows = numRows
    options.cols = numCols
    options.hardware_mapping = "adafruit_hat"
    options.chain_length = 1
    options.parallel = 1
    options.brightness = 100 #audvis.py has this set to 70, maybe change later
    options.gpio_slowdown = 5 #audvis.py has this set to 7, maybe change later
    options.drop_privileges = False

    try:
        matrix = RGBMatrix(options=options) # Initialization + error handling because I am stupid
    except Exception as e:
        print("Matrix opening failed, make sure to kill audvis process")
        return

    # Matrix initialization
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()
    for y in range (numRows):
        botRow = numRows = 1 - y
        t = botRow / numRows
        r, g, b = sampleGradients(colors, t)
        for x in range(numCols):
            canvas.SetPixel(x, y, r, g, b)
    canvas = matrix.SwapOnVSync(canvas)

    print(f"Displaying for {seconds} seconds")
    time.sleep(seconds)
    matrix.Clear()

def newGradient():
    name = input("Gradient name: ").strip()
    if not name:
        print("Name field cannot be empty")
        return None
    print("Input the first hexadecimal color (e.g. #ffffff), start with the BOTTOM color and type 'done' when finished (minimum of two colors).")
    colors_hex = []
    while True:
        entry = input(f"Color #{len(colors_hex) + 1} (or 'done'): ").strip()
        if entry.lower() == "done":
            if len(colors_hex) < 2:
                print("Gradients must be two colors")
                continue
            break
        try:
            hex2rgb(entry)
        except ValueError as e:
            print(f"Invalid color {e}")
            continue
        colors_hex.append(entry)

    rgb_colors = [hex2rgb(c) for c in colors_hex]
    return {"name": name, "colors": rgb_colors}

def listGradient(gradients):
    if not gradients:
        print("There are no gradients")
        return
    for i, g in enumerate(gradients):
        print(f"[{i}] {g['name']}  ({len(g['colors'])} colors)")

def main():
    # File check and linking to the rest of the function
    fileCheck()
    gradients = parseGradients(gradientFile)

    while True:
        listGradient(gradients)
        print("\n Controls")
        print("n - New Gradient")
        print("p - Preview via Terminal")
        print("m - Preview via Matrix")
        print("d - Delete")
        print("q - Save and quit")
        choice = input("> ").strip().lower()
        
        # NEW GRADIENT
        if choice == "n":
            new_gradient = newGradient()
            if new_gradient:
                gradients.append(new_gradient)
                saveGradients(gradientFile, gradients)
                print(f"Saved '{new_gradient['name']}'.")

        # PREVIEW VIA TERMINAl
        if choice == "p":
            if not gradients:
                print("No gradients yet.")
                continue
            idx = input("Index to preview: ").strip()
            if idx.isdigit() and int(idx) < len(gradients):
                terminalPreview(gradients[int(idx)]["colors"])
            else:
                print("Invalid index")
        # PREVIEW VIA MATRIX
        if choice == "m":
            if not gradients:
                print("No gradients yet.")
                continue
        idx = input("Index to preview on matrix: ").strip()
        if idx.isdigit() and int(idx) < len(gradients):
            matrixPreview(gradients[int(idx)]["colors"])
        else:
            print("Invalid index")
    
        # DELETE
        if choice == "d":
            if not gradients:
                print("No gradients yet.")
                continue
            idx = input("Index to delete: ").strip()
            if idx.isdigit() and int(idx) < len(gradients):
                removed = gradients.pop(int(idx))
                saveGradients(gradientFile, gradients)
                print(f"Deleted '{removed['name']}'.")
            else:
                print("Invalid index")

        # SAVE AND QUIT
        if choice == "q":
            saveGradients(gradientFile, gradients)
            break

        else:
            print("Unknown input, please try again.")

if __name__ == "__main__":
    main()