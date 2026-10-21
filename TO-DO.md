Further plans for the project as well as stuff that needs to be added to the repository

# Short Term / Bug Fixes
- Fix noise floor sensitivity alternating between 0 and 0.6, so that you can change the volume of the channels on the audio interface (for ripper mode) without drastically messing up the visualizer mode
- Fix noise floor text printing endlessly once initially modified.
- Fix the ripper mode not entering standby mode upon silence
- Fix SSH Host Key verification in the standalone gradient generator
- Replace `paramiko.AutoAddPolicy()` with system host key validation
- Implement `client.load_system_host_keys()` and switch the missing host key policy to `paramiko.RejectPolicy()`.
- Add exception handling for `paramiko.SSHException` to catch unknown hosts.
- Use a git rebase to remove insecure version of `gradient_generator_v2.py`
- Force push the sanitized history to GitHub to prevent accidental downloads.

# Repository
- Auto-run/system service setup instructions
- Add Gradient Maker v2
- Video demo

# Long Term Project / Stretch Goals
- Add rotary encoder that can be used to change colors from gradient presents to match currently playing album.
- Add rotary encoder for brightness and noise floor sensitivity (POTENTIALLY changing the number of bands displayed instead of sensitivity, not sure yet)
- Create 3D printable enclosure so there aren't (too many) loose wires in my entertainment center
- Test on lower end Pi models so I can downscale from a 256GB microSD and an 8GB Pi 5 and reuse those.
