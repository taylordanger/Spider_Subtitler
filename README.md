# Spider Subtitler

Real-time Japanese-to-English subtitle generation for the rest of us — specifically, the rest of us who own Japanese laserdiscs.

The workflow is straightforward: open the app on your laptop, start your Japanese laserdisc (or any Japanese audio source, the software is not precious about it), and set your laptop near the TV so the microphone can pick up the audio. That's the entire setup. The app listens, transcribes, and displays English subtitles on your screen in real time. No cables, no capture cards, no dedicated hardware — just a laptop and a microphone pointed at whatever is making noise.

Because it's just a laptop, it goes wherever you go. Living room, bedroom, a friend's place, a screening room, a suspiciously large walk-in closet — if there's a screen playing Japanese audio, Spider Subtitler will follow. It works with any TV or any space. It is, by design, portable.

The subtitles appear in an Electron GUI window. For those watching from the couch — or from further away than is probably advisable — **Theater Mode** displays the subtitles in a large, high-contrast format readable from across the room. Sit back. Read from afar. Pretend you understood all along.

Under the hood: [whisper.cpp](https://github.com/ggerganov/whisper.cpp) handles transcription and translation, a Python daemon handles audio capture and silence detection, and the Electron GUI handles users who find environment variables distressing. The software also filters out whisper's well-documented habit of spontaneously generating compliments and sign-offs when given silence — a quirk that is charming exactly once.

The laserdisc format was discontinued in 2001. The market for this software is small. If you are in it, you are among friends.

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
