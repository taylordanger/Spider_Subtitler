# Spider Subtitler

Real-time speech-to-subtitle tool powered by [whisper.cpp](https://github.com/ggerganov/whisper.cpp). Captures microphone audio in short chunks, transcribes and translates it (Japanese → English by default), and displays live subtitles — either overlaid on a video feed (Linux/GStreamer) or in an Electron GUI window (macOS/Linux).

## How it works

- `id_subtitle_deamon.py` — core Python daemon; records audio chunks, runs whisper.cpp for translation, and emits subtitles
- `electron-subtitle-app/` — optional Electron GUI that wraps the daemon with a config panel and floating subtitle window

---

## Prerequisites

### 1) whisper.cpp

- Build whisper.cpp from source and download a model (small/base/medium/large).

```sh
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
cmake -B build && cmake --build build --config Release
bash models/download-ggml-model.sh small   # or base, medium, large
```

### 2) Python

- Python 3.9+ is required for the daemon. Install runtime dependencies with:

```sh
pip3 install -r requirements.txt
```

The daemon respects these environment variables (alternatively pass flags):

- `WHISPER_BIN` — path to the whisper.cpp binary (or use `--whisper-bin` flag)
- `MODEL_PATH` — path to the ggml model (or use `--model` flag)
- `AUDIO_DEVICE` — platform-dependent audio capture device
- `MIN_AUDIO_RMS` — minimum RMS to treat audio as speech

Tip: when running the Electron GUI, set the Python executable path in the app settings (defaults to `python3`). Packaged apps may not inherit your shell PATH, so use an absolute Python path (e.g. `/usr/bin/python3`) if you see spawn ENOENT errors.

---

## Installation

### macOS

```sh
# Audio capture and (optional) GStreamer overlay
brew install ffmpeg pygobject3 gobject-introspection gst-plugins-base gstreamer

# Python dependencies (or use the repo requirements file)
pip3 install -r requirements.txt
```

### Linux (Debian / Ubuntu / Raspberry Pi)

```sh
# Audio capture (arecord) and GStreamer overlay
sudo apt-get install -y \
  alsa-utils \
  python3-gi \
  gir1.2-gstreamer-1.0 \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good

# Python dependencies
pip3 install -r requirements.txt
```

### Electron GUI (optional, all platforms)

Requires Node.js 18+.

```sh
cd electron-subtitle-app
npm install
```

---

## Running

### Command-line daemon

Run the daemon directly (no GUI):

```sh
python3 id_subtitle_deamon.py \
  --whisper-bin /path/to/whisper.cpp/build/bin/whisper-cli \
  --model /path/to/whisper.cpp/models/ggml-small.bin \
  --source-language ja \
  --no-overlay \
  --emit-json
```

Key runtime environment variables (the daemon reads these if present):

- `WHISPER_BIN`, `MODEL_PATH`, `AUDIO_DEVICE`, `MIN_AUDIO_RMS`, `FFMPEG_BIN`

### Electron GUI

Start the Electron GUI in development mode:

```sh
cd electron-subtitle-app
npm start
```

In the GUI's settings panel set:

- Whisper binary (`whisperBin`) and model path (`modelPath`)
- Audio device and source language
- Python executable path (`pythonPath`) — defaults to `python3`. If the app shows `spawn python ENOENT`, set this to the absolute Python path (for example `/usr/bin/python3`) because packaged apps may not inherit your shell PATH.

### Using internal/system audio instead of microphone

Yes, this is supported.

- On macOS, audio capture uses ffmpeg AVFoundation selectors (`AUDIO_DEVICE` in format `:<index>`).
- In the Electron app, click `List Audio Inputs` to print available input devices in Logs.
- Set `Audio Device` to one of the listed indices (example: `:1`).

For TV/system audio routing on macOS, use a virtual loopback device:

1. Install BlackHole (or similar virtual audio driver).
2. Open Audio MIDI Setup and create a Multi-Output Device (your speakers + BlackHole).
3. Set your media output to that Multi-Output Device.
4. In Spider Subtitler, choose the BlackHole input index via `List Audio Inputs`.

This lets subtitles follow internal audio directly without relying on room loudness.

The GUI launches the Python daemon with `--emit-json` so it can parse structured events.

### Packaging (macOS / Linux)

Build a distributable from `electron-subtitle-app`:

```sh
cd electron-subtitle-app
npm install
npm run dist
```

Note: packaging requires `electron-builder` and a configured environment. Packaged apps may need absolute paths for external binaries (Python, ffmpeg, whisper) in the app settings or environment because the runtime PATH can differ.

### One-shot translation (testing)

```sh
python3 id_subtitle_deamon.py \
  --test-translate /path/to/audio.wav \
  --whisper-bin /path/to/whisper-cli \
  --model /path/to/ggml-small.bin
```

---

## Notes

- On macOS, PyGObject/GStreamer is optional; the daemon falls back to `--no-overlay` mode automatically if not installed.
- Adjust `--chunk-seconds` (default: `2`) to tune latency vs. accuracy.
- Set `MIN_AUDIO_RMS` lower to pick up quieter audio, or higher to reduce false triggers.
- A `.gitignore` has been added to ignore `node_modules/` and `dist/` directories when committing.
