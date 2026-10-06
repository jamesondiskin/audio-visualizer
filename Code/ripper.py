""" EXPERIMENTAL RIPPER MODE
Objective: Detect a record starting and convert audio to a .wav or .flac file, automatically stopping when audio is silent for a set duration.
This uses a raw stereo input (not the same one as the audio visualizer mode, that's a mono downmix bc it doesn't pass the audio through to anything).
Note, some extra depedencies are required. Make sure Libsndfile and soundfile are installed.
"""

import os
import time
import datetime # For naming the file
import numpy as np
import soundfile as sf

noiseFloor = 0.02 # Anything above this value means that recording starts and we no longer have silence
stopTimer = 15.0 # After 15 seconds of silence, the recording will stop. 
sampleRate = 44100 # 44.1KHz, uses the existing audio stream so a new one doesn't have to be opened
channels = 2 # Stereo
outputPath = os.path.expanduser("~/audio-vis/rips")
stateStandby = "STANDBY"
stateRec = "REC"

class Ripper:
    def __init__(self, output_format="FLAC"):
        self.state = stateStandby
        self.output_format = output_format # FLAC or WAV
        self._file = None
        self.silence_started_at = None
        os.makedirs(outputPath, exist_ok=True)

    def set_format(self, fmt):
        if self.state == stateRec:
            return
        self.output_format = fmt

    def _start_recording(self):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d___%H%M%S")
        ext = "flac" if self.output_format == "FLAC" else "wav"
        path = os.path.join(outputPath, f"rip_{timestamp}.{ext}")
        self._file = sf.SoundFile(
            path, mode="w", samplerate=sampleRate,
            channels=channels, format=self.output_format, subtype="PCM_24"

        )
        self.state = stateRec
        self.silence_started_at = None
        print(f"[ripper] Recording started with file output at: {path}")

    def _stop_recording(self):
        if self._file:
            self._file.close()
            self._file = None
        print("[ripper] Recording stopped")
        self.state = stateStandby

    def manualStart(self):
        if self.state == stateStandby:
            self._start_recording()

    def process_block(self, audio_block_stereo):
        peak = float(np.max(np.abs(audio_block_stereo)))

        if self.state == stateStandby:
            if peak >= noiseFloor:
                self._start_recording()
                self._file.write(audio_block_stereo)
        elif self.state == stateRec:
            self._file.write(audio_block_stereo)
            if peak < noiseFloor:
                if self.stopTimer is None:
                    self._stopTimer = time.time()
                elif time.time() - self._stopTimer >= stopTimer:
                    self._stop_recording()
            else:
                self._stopTimer = None

    def status(self):
        return self.state
