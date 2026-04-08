# Spider Subtitler

Real-time speech-to-subtitle tool powered by [whisper.cpp](https://github.com/ggerganov/whisper.cpp). Captures microphone audio in short chunks, transcribes and translates it (Japanese → English by default), and displays live subtitles — either overlaid on a video feed (Linux/GStreamer) or in an Electron GUI window (macOS/Linux).

## How it works

- `id_subtitle_deamon.py` — core Python daemon; records audio chunks, runs whisper.cpp for translation, and emits subtitles
- `electron-subtitle-app/` — optional Electron GUI that wraps the daemon with a config panel and floating subtitle window

---

## Prerequisites

### All platforms

1. **whisper.cpp** — build from source and note the path to the binary and a model file.

   ```sh
   git clone https://github.com/ggerganov/whisper.cpp
   cd whisper.cpp
   cmake -B build && cmake --build build --config Release
   bash models/download-ggml-model.sh small   # or base, medium, large
   ```

2. **Python 3.9+**

---

## Installation

### macOS

```sh
# Audio capture and (optional) GStreamer overlay
brew install ffmpeg pygobject3 gobject-introspection gst-plugins-base gstreamer

# Python dependencies
pip3 install SpeechRecognition PyAudio PyGObject
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
pip3 install SpeechRecognition PyAudio
```

### Electron GUI (optional, all platforms)

Requires [Node.js](https://nodejs.org) 18+.

```sh
cd electron-subtitle-app
npm install
```

---

## Running

### Command-line daemon

```sh
python3 id_subtitle_deamon.py \
  --whisper-bin /path/to/whisper.cpp/build/bin/whisper-cli \
  --model /path/to/whisper.cpp/models/ggml-small.bin \
  --source-language ja        # source language (ja = Japanese, auto = auto-detect)
  --no-overlay                # omit to use GStreamer video overlay (Linux)
```

Key environment variables (override defaults):

| Variable | Default (Linux) | Default (macOS) |
|---|---|---|
| `AUDIO_DEVICE` | `plughw:1,0` | `:0` |
| `VIDEO_DEVICE` | `/dev/usb001` | — |
| `WHISPER_BIN` | `/home/pi/whisper.cpp/main` | — |
| `MODEL_PATH` | `/home/pi/whisper.cpp/models/ggml-small.bin` | — |
| `MIN_AUDIO_RMS` | `250` | `250` |

### Electron GUI

```sh
cd electron-subtitle-app
npm start
```

Configure the whisper binary path, model path, audio device, and language from the settings panel in the app.

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
