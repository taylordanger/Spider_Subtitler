#!/usr/bin/env python3
import os
import subprocess
import threading
import tempfile
import time
import argparse
import platform
import shutil
import json
import wave
import struct
import math
from typing import Any, cast

IS_MACOS = platform.system() == "Darwin"

GI_AVAILABLE = True
Gst: Any
GLib: Any
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GLib', '2.0')
    from gi.repository import Gst, GLib  # type: ignore
except ImportError:
    GI_AVAILABLE = False
    Gst = cast(Any, None)
    GLib = cast(Any, None)

WHISPER_BIN = os.environ.get("WHISPER_BIN", "/home/pi/whisper.cpp/main")
MODEL_PATH = os.environ.get("MODEL_PATH", "/home/pi/whisper.cpp/models/ggml-small.bin")
VIDEO_DEVICE = os.environ.get("VIDEO_DEVICE", "/dev/usb001")
# Linux: ALSA device (ex: plughw:1,0). macOS ffmpeg avfoundation audio selector (ex: :0)
AUDIO_DEVICE = os.environ.get("AUDIO_DEVICE", ":0" if IS_MACOS else "plughw:1,0")
# Skip whisper on near-silent chunks to prevent default hallucinations.
MIN_RMS = int(os.environ.get("MIN_AUDIO_RMS", "250"))
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
ENABLE_SPEECH_FILTER = os.environ.get("ENABLE_SPEECH_FILTER", "1") == "1"
VAD_MODEL_PATH = os.environ.get("VAD_MODEL_PATH", "").strip()
VAD_THRESHOLD = os.environ.get("VAD_THRESHOLD", "0.6")


def resolve_ffmpeg_binary() -> str:
    # GUI-packaged apps may not inherit shell PATH; probe common Homebrew locations.
    candidates = [
        FFMPEG_BIN,
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/local/bin/ffmpeg",
    ]
    for item in candidates:
        if os.path.isabs(item):
            if os.path.exists(item):
                return item
            continue
        resolved = shutil.which(item)
        if resolved:
            return resolved
    raise RuntimeError(
        "ffmpeg not found. Install with: brew install ffmpeg. "
        "If installed, set FFMPEG_BIN to full path (example: /opt/homebrew/bin/ffmpeg)."
    )

def get_pipe_desc() -> str:
    # GStreamer pipeline string (update font size/position as desired)
    if IS_MACOS:
        return (
            "autovideosrc ! videoconvert ! "
            "textoverlay name=subtitle font-desc=\"Sans 28\" halignment=center valignment=bottom shaded-background=true ! "
            "autovideosink sync=false"
        )

    return (
        f"v4l2src device={VIDEO_DEVICE} ! videoconvert ! "
        "textoverlay name=subtitle font-desc=\"Sans 28\" halignment=center valignment=bottom shaded-background=true ! "
        "autovideosink sync=false"
    )


def record_chunk_to_wav(wav_path: str, duration_sec: int = 2):
    if IS_MACOS:
        ffmpeg_bin = resolve_ffmpeg_binary()

        # avfoundation audio-only input format is :<index>, ex: :0
        ffmpeg_cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
            "-i",
            AUDIO_DEVICE,
            "-t",
            str(duration_sec),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            # Favor speech band and attenuate low/high music-heavy regions.
            "highpass=f=120,lowpass=f=3600" if ENABLE_SPEECH_FILTER else "anull",
            "-y",
            wav_path,
        ]
        try:
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            err_text = (e.stderr or "").strip()
            raise RuntimeError(f"ffmpeg capture failed for AUDIO_DEVICE={AUDIO_DEVICE}: {err_text}") from e
        return

    arecord_cmd = [
        "arecord",
        "-D",
        AUDIO_DEVICE,
        "-f",
        "S16_LE",
        "-r",
        "16000",
        "-c",
        "1",
        "-d",
        str(duration_sec),
        wav_path,
    ]
    try:
        subprocess.run(arecord_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        err_text = (e.stderr or "").strip()
        raise RuntimeError(f"arecord capture failed for AUDIO_DEVICE={AUDIO_DEVICE}: {err_text}") from e


def build_whisper_cmd(whisper_bin: str, model_path: str, wav_path: str, source_language: str):
    cmd = [
        whisper_bin,
        "-m", model_path,
        "-f", wav_path,
        "--translate",
        # Reduce context-driven and silence-driven hallucinations.
        "-mc", "0",
        "-nth", "0.8",
        "-sns",
        "-nf",
    ]
    if source_language and source_language != "auto":
        cmd.extend(["--language", source_language])

    # Optional VAD model support: only enable when a valid model path is supplied.
    if VAD_MODEL_PATH and os.path.exists(VAD_MODEL_PATH):
        cmd.extend(["--vad", "--vad-model", VAD_MODEL_PATH, "--vad-threshold", VAD_THRESHOLD])

    return cmd


def normalize_line(text: str) -> str:
    return " ".join(text.strip().lower().split())


def should_skip_line(text: str, last_line_norm: str):
    norm = normalize_line(text)
    known_hallucinations = {
        "thank you for watching",
        "thanks for watching",
        "thank you",
        "subscribe",
        "like and subscribe",
        "see you next time",
        "Translated by Vortex",
        "Please subscribe to my channel and like this video!",
        "If you enjoyed this video, please subscribe to my channel and give it a high rating.",
        "If you like this video, please subscribe to my channel.",
        "If you enjoyed this video,",
        "I'll see you in the next video.",
        "Thank you very much for watching.",
        "Thank you very much for watching!",
        "Thank you for watching.",
        "Thank you for watching!",
        "If you enjoyed this video, please subscribe to my channel and like this video.",
        "If you enjoyed this video, please subscribe to my channel and like this video!",
        "That's all for this video. Thanks for watching.",
        "That's all for this video. See you in the next one!",
        "That's all for this video.",
        "See you next time!",
        "This is not the end of this video.",
        "THE END",
        "And that's it for today's video.",
        "END",
        "Please subscribe to my channel.",
        "Please subscribe to my channel!",
        "Please subscribe and like this video.",
        "Please subscribe and like this video!",
        "Please subscribe and like.",
        "Please subscribe.",
        "Subscribe to my channel.",
        "Subscribe and like this video.",
        "Subscribe and like.",
        "Subscribe.",
        "Don't forget to subscribe to my channel and like this video!",
        "Don't forget to subscribe and like this video!",
        "Don't forget to subscribe and like!",
        "Don't forget to subscribe!",
        "Don't forget to subscribe to my channel!",
        "Don't forget to subscribe and like this video!",
        "Don't forget to subscribe and like!",
        "Don't forget to subscribe!",
        "To be continued...",
        "To be continued",
        "Please like and subscribe to my channel.",
        "Please like and subscribe to my channel!",
        "Please like and subscribe.",
        "Please like and subscribe!",
        "Please like this video and subscribe to my channel.",
        "Please like this video and subscribe to my channel!",
        "Please like this video and subscribe.",
        "Please like this video and subscribe!",
        "Please like this video."
    }
    if norm in known_hallucinations:
        return True, norm
    if "thank you for watching" in norm:
        return True, norm
    if "subscribe" in norm and len(norm.split()) <= 8:
        return True, norm
    if norm == last_line_norm:
        return True, norm
    return False, norm


def get_audio_rms(wav_path: str):
    try:
        with wave.open(wav_path, "rb") as wf:
            sample_width = wf.getsampwidth()
            n_channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
            if not frames:
                return 0.0

            # Compute RMS without audioop for Python 3.13 compatibility.
            if sample_width == 2:
                sample_count = len(frames) // 2
                if sample_count == 0:
                    return 0.0
                values = struct.unpack("<" + "h" * sample_count, frames)
            elif sample_width == 1:
                sample_count = len(frames)
                if sample_count == 0:
                    return 0.0
                raw = struct.unpack("<" + "B" * sample_count, frames)
                values = [v - 128 for v in raw]
            else:
                return float(MIN_RMS)

            if n_channels > 1:
                mono = []
                for i in range(0, len(values), n_channels):
                    chunk = values[i:i + n_channels]
                    if not chunk:
                        continue
                    mono.append(sum(chunk) / len(chunk))
                values = mono

            if not values:
                return 0.0
            mean_square = sum(v * v for v in values) / len(values)
            return math.sqrt(mean_square)
    except Exception:
        # If RMS calculation fails, do not block transcription.
        return float(MIN_RMS)

# Simple energy-based filter to skip near-silent chunks and prevent hallucinations.
def audio_has_speech_energy(wav_path: str, min_rms: int):
    return get_audio_rms(wav_path) >= min_rms

# Emit a subtitle message. If emit_json is True, output a JSON line instead of plain text for better integration with external tools.
def emit_subtitle(text: str, emit_json: bool):
    if emit_json:
        print(json.dumps({"type": "subtitle", "text": text}), flush=True)
        return
    print(text, flush=True)
# Emit a status update. If emit_json is True, output a JSON line instead of plain text for better integration with external tools.

def emit_status(stage: str, emit_json: bool):
    if emit_json:
        print(json.dumps({"type": "status", "stage": stage}), flush=True)
        return
    print(f"[status] {stage}", flush=True)

# Emit audio level information. If emit_json is True, output a JSON line instead of plain text for better integration with external tools.
def emit_audio_level(rms: float, threshold: int, emit_json: bool):
    if emit_json:
        print(json.dumps({"type": "audio-level", "rms": round(rms, 2), "threshold": threshold}), flush=True)
        return
    print(f"[audio] rms={rms:.1f} threshold={threshold}", flush=True)


def resolve_whisper_binary(whisper_bin: str) -> str:
    # Accept absolute paths or executables discoverable via PATH.
    if os.path.isabs(whisper_bin) and os.path.exists(whisper_bin):
        return whisper_bin
    resolved = shutil.which(whisper_bin)
    if resolved:
        return resolved
    raise FileNotFoundError(
        f"whisper binary not found: {whisper_bin}. "
        "Set --whisper-bin to the full path, e.g. /Users/<you>/whisper.cpp/build/bin/whisper-cli"
    )


def validate_runtime_paths(whisper_bin: str, model_path: str):
    resolved_whisper = resolve_whisper_binary(whisper_bin)
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"whisper model not found: {model_path}")
    return resolved_whisper

class SubtitleDaemon:
    def __init__(self):
        if not GI_AVAILABLE:
            raise RuntimeError("PyGObject/GStreamer not available")
        Gst.init(None)
        self.loop = GLib.MainLoop()
        self.pipeline = Gst.parse_launch(get_pipe_desc())
        self.sub_overlay = self.pipeline.get_by_name("subtitle")
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)
        self.transcript = ""
        self.lock = threading.Lock()

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            self.loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, dbg = message.parse_error()
            print("Gst.Error:", err, dbg)
            self.loop.quit()

    def start_video(self):
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
            self.loop.run()
        finally:
            self.pipeline.set_state(Gst.State.NULL)

    def update_subtitle(self, text):
        # called from other thread via GLib.idle_add
        if self.sub_overlay:
            self.sub_overlay.set_property("text", text)

def record_and_transcribe(daemon: SubtitleDaemon, whisper_bin: str, model_path: str, source_language: str, chunk_seconds: int):
    # continuous loop: record short chunks and call whisper.cpp --translate
    last_line_norm = ""
    while True:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            # record short chunk mono 16k (platform-aware)
            record_chunk_to_wav(wav_path, duration_sec=chunk_seconds)
        except (subprocess.CalledProcessError, RuntimeError) as e:
            print("audio capture failed; check device/tooling:", e)
            time.sleep(1)
            continue

        if not audio_has_speech_energy(wav_path, MIN_RMS):
            os.unlink(wav_path)
            continue

        # Call whisper.cpp for translation (adjust flags to your built binary)
        # Capturing stdout; whisper.cpp prints transcription to stdout.
        whisper_cmd = build_whisper_cmd(whisper_bin, model_path, wav_path, source_language)
        try:
            p = subprocess.run(whisper_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            output = p.stdout.strip()
        except subprocess.CalledProcessError as e:
            print("whisper error:", e.stderr)
            output = ""
        except subprocess.TimeoutExpired:
            print("whisper timed out")
            output = ""

        os.unlink(wav_path)
        if output:
            skip, norm = should_skip_line(output, last_line_norm)
            if skip:
                continue
            last_line_norm = norm
            # Use GLib.idle_add to update subtitle in the GStreamer mainloop safely
            GLib.idle_add(daemon.update_subtitle, output)
        else:
            # clear after short time if no text
            time.sleep(0.1)


def live_translate_no_overlay(whisper_bin: str, model_path: str, source_language: str, chunk_seconds: int, emit_json: bool):
    print(
        f"Live translation (no overlay) started. Listening on AUDIO_DEVICE={AUDIO_DEVICE}, "
        f"chunk={chunk_seconds}s, source_language={source_language}."
    )
    last_line_norm = ""
    last_capture_error = ""
    repeated_capture_error_count = 0
    emit_status("ready", emit_json)
    while True:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            emit_status("recording", emit_json)
            record_chunk_to_wav(wav_path, duration_sec=chunk_seconds)
        except (subprocess.CalledProcessError, RuntimeError) as e:
            err_text = str(e)
            if err_text == last_capture_error:
                repeated_capture_error_count += 1
            else:
                last_capture_error = err_text
                repeated_capture_error_count = 1

            if repeated_capture_error_count == 1 or repeated_capture_error_count % 10 == 0:
                print("audio capture failed; check device/tooling:", err_text)
            time.sleep(1)
            emit_status("ready", emit_json)
            continue

        last_capture_error = ""
        repeated_capture_error_count = 0

        chunk_rms = get_audio_rms(wav_path)
        emit_audio_level(chunk_rms, MIN_RMS, emit_json)
        if chunk_rms < MIN_RMS:
            os.unlink(wav_path)
            emit_status("ready", emit_json)
            continue

        whisper_cmd = build_whisper_cmd(whisper_bin, model_path, wav_path, source_language)

        try:
            emit_status("transcribing", emit_json)
            p = subprocess.run(whisper_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            output = p.stdout.strip()
            if output:
                skip, norm = should_skip_line(output, last_line_norm)
                if skip:
                    emit_status("ready", emit_json)
                    continue
                last_line_norm = norm
                emit_subtitle(output, emit_json)
        except subprocess.CalledProcessError as e:
            print("whisper error:", e.stderr)
        except subprocess.TimeoutExpired:
            print("whisper timed out")
        finally:
            os.unlink(wav_path)
            emit_status("ready", emit_json)


def run_translate_once(audio_file: str, whisper_bin: str, model_path: str):
    whisper_cmd = [
        whisper_bin,
        "-m", model_path,
        "-f", audio_file,
        "--translate",
    ]
    p = subprocess.run(
        whisper_cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=90,
    )
    return p.stdout.strip()

def main():
    parser = argparse.ArgumentParser(description="Subtitle daemon and one-shot translation test")
    parser.add_argument("--test-translate", metavar="AUDIO_FILE", help="Run one translation pass on a local audio file and exit")
    parser.add_argument("--whisper-bin", default=WHISPER_BIN, help="Path to whisper.cpp binary")
    parser.add_argument("--model", default=MODEL_PATH, help="Path to whisper.cpp model file")
    parser.add_argument("--source-language", default="ja", help="Source language code for whisper (default: ja, use auto to auto-detect)")
    parser.add_argument("--chunk-seconds", type=int, default=2, help="Audio chunk duration in seconds for live mode (default: 2)")
    parser.add_argument("--no-overlay", action="store_true", help="Run live microphone translation without GStreamer subtitle overlay")
    parser.add_argument("--emit-json", action="store_true", help="Emit JSON lines for subtitle events")
    args = parser.parse_args()

    if args.test_translate:
        if not os.path.exists(args.test_translate):
            raise FileNotFoundError(f"Audio file not found: {args.test_translate}")
        args.whisper_bin = validate_runtime_paths(args.whisper_bin, args.model)

        translated = run_translate_once(args.test_translate, args.whisper_bin, args.model)
        print(translated)
        return

    args.whisper_bin = validate_runtime_paths(args.whisper_bin, args.model)

    if args.no_overlay:
        print(f"Using whisper binary: {args.whisper_bin}")
        print(f"Using model: {args.model}")
        live_translate_no_overlay(args.whisper_bin, args.model, args.source_language, args.chunk_seconds, args.emit_json)
        return

    if not GI_AVAILABLE:
        if IS_MACOS:
            print(
                "PyGObject (gi) not found; falling back to --no-overlay mode. "
                "Install overlay prerequisites with: brew install pygobject3 gobject-introspection gst-plugins-base gstreamer"
            )
            print(f"Using whisper binary: {args.whisper_bin}")
            print(f"Using model: {args.model}")
            live_translate_no_overlay(args.whisper_bin, args.model, args.source_language, args.chunk_seconds, args.emit_json)
            return
        raise ImportError("GStreamer Python bindings not found. Install with: sudo apt-get install python3-gi gir1.2-gstreamer-1.0")

    daemon = SubtitleDaemon()
    t_video = threading.Thread(target=daemon.start_video, daemon=True)
    t_audio = threading.Thread(
        target=record_and_transcribe,
        args=(daemon, args.whisper_bin, args.model, args.source_language, args.chunk_seconds),
        daemon=True,
    )
    t_video.start()
    t_audio.start()
    try:
        while t_video.is_alive():
            t_video.join(timeout=0.5)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()