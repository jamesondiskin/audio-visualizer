# Real-time Audio Visualizer

<video src="https://github.com/user-attachments/assets/14c61fe0-b0ee-4298-b2c4-de7c07e8da9a" width="100%" height="100%" controls></video>

This project is built on the Raspberry Pi 5, developed using an 8GB board, although suitable across all models. Running the program headless uses only ~200MB of RAM while running all the libraries.

Hardware Used:
- [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/)
- [Adafruit RGB LED Matrix](https://www.adafruit.com/product/2279) and the included cables
- [Adafruit RGB Matrix Hat](https://www.adafruit.com/product/2345)
- A USB Audio Interface (any Linux compatible USB interface should work, but I used a [PreSonus AudioBox iTwo](https://www.sweetwater.com/insync/presonus-audiobox-ione-and-audiobox-itwo/) because I found an open-box unit for very cheap.
- Power supply for the Raspberry Pi and the Matrix HAT (the official 27W Pi 5 charger was used, plus a 5V power supply to independently power the matrix)
- Requisite cables for your audio setup

# Pi 5 Setup
Note: This process requires the use of the Pi 5 and an additional PC
1) Using [Raspberry Pi Imager](https://www.raspberrypi.com/software/) begin creating your boot installation of __Raspberry Pi OS Lite (64 bit)__ on a microSD card.
2) Choose your hostname (I used audvis), username, and password.
3) Set up your Wi-Fi credentials.
4) Enable password authenticated SSH.
5) Insert the microSD card and power on the Raspberry Pi.

Note: It may be necessary to connect a monitor, keyboard, and mouse to the Pi for the next steps if your network was not configured successfully during the installation.

# Connect to the Pi
1) Run `hostname -l` on the Raspberry Pi to get the local IP
2) Verify WiFi connection with `sudo nmcli device wifi connect "YOUR SSID" password "YOUR PASSWORD"`
3) Verify SSH is turned on with `sudo systemctl enable --now ssh`
4) On a different computer, open PowerShell (Windows), Terminal (macOS), or terminal of choice (Linux) and run `ssh "USER"@"LOCAL IP FOUND IN STEP 1"`. Example: `ssh username@192.168.x.xx` on a home network.

# IDE Setup
Once connection has been established, it is time to set up the IDE. For the development, I did my programming in VS Code these are the setup steps I took. They may vary if you have a different preferred environment.
1) Install the __Remote -- SSH__ extension
2) In the command palette, choose __Remote-SSH: Connect to host__ with the same user@IP format used to test SSH.
3) In the directory, create a new folder called `audio-vis` to act as the project root.

Note: You may want to authenticate with SSH keys, but I chose to just use my password as needed.
