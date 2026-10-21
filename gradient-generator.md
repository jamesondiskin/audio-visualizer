# Gradient Generator

This is a Python script meant to run on a separate computer (from the Raspberry Pi running the rest of this) to generate gradients based on uploaded images. These gradients can then be used by the Raspbery Pi and the LED Matrix.

Click the image below for a demonstration video

<p align="center">
  <a href="https://www.youtube.com/watch?v=GE7Re7thSW4">
    <img width="3440" height="1440" alt="Click me to see demo!" src="https://github.com/user-attachments/assets/55ab552a-ad66-4629-850a-52d1717660dc" />
  </a>
</p>

# Security Warning
The SSH implementation will just accept any SSH key it is given. There is NO IDENTITY VERIFICATION and cryptographic host key verification is completely bypassed. Use at your own risk. In a home network, the possibility of a lateral movement attack is still present in the event any other local device is compromised. I currently have no timeline for a fix as I finalize bug fixes for the audio visualizer itself. Please view `TO-DO.md` for more information. For full transparency, when this is patched, the history of `gradient_generator_v2.py` will be removed not to conceal that the vulnerability existed but to ensure that nobody accidentally downloads an insecure legacy version of the script.

Included functionality:

- Automatic gradient generation based on image upload
- Ability to edit number of gradient stops
- Ability to edit color and brightness of specific gradient stops
- Ability to rename and save gradients to a text file on the local machine
- Ability to send gradients to audio visualizer on the Pi 5 connected via SSH
- Ability to automatically reset and redistribute gradient stops (for either the gradient itself or the image-based generation)
- Built in color wheel with native support for direct hexadecimal color input

# Requirements
1) Install the latest version of Python
2) Create a new VS Code folder to house the code and run `pip install pillow paramiko`
3) Add `gradient_generator.py` to the folder.
4) Run the program (press F5)
5) Select "Pi Settings"
6) Enter the Pi hostname or IP address (note: you can easily retrieve the hostname by typing `hostname` in the terminal of your Pi SSH window)
7) Enter the SSH username (note: you can easily retrieve the username by typing `whoami` in the terminal of your Pi SSH window)
8) Save the settings
