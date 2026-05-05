#!/usr/bin/env python3
import os
import subprocess
import threading
import tempfile
import time
import argparse
import platform
import shutil
import io
import json
import wave
import struct
import math
import re
import difflib
import urllib.request
import urllib.parse
import zipfile
from functools import lru_cache
from typing import Any, Optional, cast, List, Dict

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
SUBTITLE_LANG = os.environ.get("SUBTITLE_LANG", "en")  # Language for fetched subtitles
OPENSUBTITLES_API_KEY = os.environ.get("OPENSUBTITLES_API_KEY", "").strip()


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


def list_mac_audio_inputs(ffmpeg_bin: str):
    probe = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    stderr = (probe.stderr or "")
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    audio_inputs = []
    in_audio_section = False

    for line in lines:
        if "AVFoundation audio devices" in line:
            in_audio_section = True
            continue
        if "AVFoundation video devices" in line:
            in_audio_section = False
            continue
        if not in_audio_section:
            continue

        match = re.match(r".*\[(\d+)\]\s+(.+)$", line)
        if match:
            audio_inputs.append({"index": match.group(1), "name": match.group(2)})

    return audio_inputs


def choose_mac_audio_input(audio_inputs):
    if not audio_inputs:
        return None

    preferred_patterns = [
        re.compile(r"built[- ]?in", re.IGNORECASE),
        re.compile(r"internal microphone", re.IGNORECASE),
        re.compile(r"macbook.*microphone", re.IGNORECASE),
    ]
    excluded_patterns = [
        re.compile(r"blackhole", re.IGNORECASE),
        re.compile(r"loopback", re.IGNORECASE),
        re.compile(r"capture screen", re.IGNORECASE),
    ]

    def is_excluded(name: str) -> bool:
        return any(pattern.search(name) for pattern in excluded_patterns)

    for device in audio_inputs:
        name = device.get("name", "")
        if name and not is_excluded(name) and any(pattern.search(name) for pattern in preferred_patterns):
            return device

    for device in audio_inputs:
        name = device.get("name", "")
        if name and not is_excluded(name):
            return device

    return audio_inputs[0]


@lru_cache(maxsize=1)
def get_effective_audio_device() -> str:
    requested = (AUDIO_DEVICE or "").strip()
    if not IS_MACOS:
        return requested or AUDIO_DEVICE

    ffmpeg_bin = resolve_ffmpeg_binary()
    audio_inputs = list_mac_audio_inputs(ffmpeg_bin)

    if requested and requested.lower() not in {"auto", "default", ":0"}:
        # Respect explicit selectors when they still exist in current device list.
        if re.match(r"^:\d+$", requested):
            requested_index = requested[1:]
            if any(str(device.get("index", "")) == requested_index for device in audio_inputs):
                return requested
            # Saved index is stale (devices reordered/removed), fall back to best pick.
        else:
            return requested

    chosen = choose_mac_audio_input(audio_inputs)
    if chosen and chosen.get("index") is not None:
        return f":{chosen['index']}"

    return requested or ":0"

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


def record_chunk_to_wav(wav_path: str, duration_sec: int = 2, audio_device: Optional[str] = None):
    if IS_MACOS:
        ffmpeg_bin = resolve_ffmpeg_binary()
        device_selector = audio_device or get_effective_audio_device()

        # avfoundation audio-only input format is :<index>.
        ffmpeg_cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
            "-i",
            device_selector,
            "-t",
            str(duration_sec),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            # Balanced speech filter: preserve female voices while reducing music.
            # highpass=80: preserve female voice fundamentals and male voice clarity
            # lowpass=8000: keep full speech spectrum including sibilants
            # volume/alimiter: raise quiet speech gently without clipping
            "highpass=f=80,lowpass=f=8000,volume=1.25,alimiter=limit=0.95" if ENABLE_SPEECH_FILTER else "anull",
            "-y",
            wav_path,
        ]
        try:
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            err_text = (e.stderr or "").strip()
            raise RuntimeError(f"ffmpeg capture failed for AUDIO_DEVICE={device_selector}: {err_text}") from e
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


def text_similarity(a: str, b: str) -> float:
    """Calculate similarity between two strings (0.0 to 1.0)."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def contains_repeated_chars(text: str, min_repeats: int = 3) -> bool:
    """Detect patterns like 'ああああ' or 'hahaha' that indicate hallucination."""
    # Check for repeated ASCII characters
    for char in set(text):
        if text.count(char) >= min_repeats and char.isalpha():
            # Check if they're consecutive
            pattern = char * min_repeats
            if pattern in text:
                return True
    return False


def is_likely_hallucination_pattern(text: str) -> bool:
    """Detect common hallucination patterns beyond the known list."""
    norm = normalize_line(text)
    words = norm.split()
    
    # Reject very short lines (often garbage)
    if len(norm) < 3:
        return True
    
    # Reject single character repetitions
    if contains_repeated_chars(norm):
        return True
    
    # Reject lines that are mostly numbers/special chars
    if sum(1 for c in norm if c.isalnum()) < len(norm) * 0.3:
        return True
    
    # Reject lines with excessive punctuation
    if sum(1 for c in norm if c in '.,!?;:') > len(words):
        return True
    
    # Detect music/instrumental patterns
    music_patterns = {
        "♪", "♫", "la la", "lala", "doo doo", "dododo", "tra la", 
        "nanana", "da da", "boom boom", "beep", "boop",
        "instrumental", "music", "theme", "bgm"
    }
    if any(pattern in norm for pattern in music_patterns):
        return True
    
    # Common filler words in English transcription
    filler_patterns = {
        "um", "uh", "err", "erm", "hmm", "ah", "oh", "so", "like", "you know",
        "i mean", "just", "basically", "essentially", "literally"
    }
    if norm in filler_patterns and len(words) == 1:
        return True
    
    return False


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
    
    # Check exact match in known hallucinations
    if norm in known_hallucinations:
        return True, norm
    
    # Check for common hallucination patterns
    if is_likely_hallucination_pattern(norm):
        return True, norm
    
    # Check for variations of subscription/watching messages
    if "thank you for watching" in norm:
        return True, norm
    if "subscribe" in norm and len(norm.split()) <= 8:
        return True, norm
    
    # Skip exact duplicates
    if norm == last_line_norm:
        return True, norm
    
    # Skip if too similar to last line (>85% similarity)
    if last_line_norm and text_similarity(norm, last_line_norm) > 0.85:
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


def normalize_youtube_video_id(value: str) -> str:
    raw_value = str(value or '').strip()
    if not raw_value:
        return ''

    match = re.search(r'(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{6,})', raw_value)
    if match:
        return match.group(1)

    if raw_value.startswith('http://') or raw_value.startswith('https://'):
        parsed = urllib.parse.urlparse(raw_value)
        query_id = urllib.parse.parse_qs(parsed.query).get('v', [''])[0].strip()
        if query_id:
            return query_id
        path_parts = [part for part in parsed.path.split('/') if part]
        if path_parts:
            last_part = path_parts[-1].split('?')[0].split('&')[0].strip()
            if last_part:
                return last_part

    return raw_value


def fetch_subtitles_from_youtube(video_id: str, lang: str = "en") -> Optional[str]:
    """Fetch subtitles from YouTube using yt-dlp."""
    video_id = normalize_youtube_video_id(video_id)
    print(f"[info] Fetching YouTube subtitles for video_id={video_id}, lang={lang}")
    try:
        import yt_dlp
    except ImportError:
        print("[warning] yt-dlp not installed. Install with: pip install yt-dlp")
        yt_dlp = None
    
    if yt_dlp is not None:
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': [lang],
                'outtmpl': tempfile.gettempdir() + '/%(title)s.%(ext)s',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                print(f"[info] YouTube video title: {info.get('title', 'unknown')}")
                # Look for subtitle file
                for ext in ['vtt', 'srt']:
                    subtitle_file = f"{tempfile.gettempdir()}/{info['title']}.{lang}.{ext}"
                    if os.path.exists(subtitle_file):
                        print(f"[info] Found subtitle file: {subtitle_file}")
                        return subtitle_file
                print(f"[warning] No subtitle file found for video_id={video_id} and lang={lang}")
        except Exception as e:
            err_text = str(e)
            print(f"[warning] Failed to fetch subtitles from YouTube: {e}")
            if '429' not in err_text and 'Too Many Requests' not in err_text:
                return None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("[warning] youtube-transcript-api not installed. Install with: pip install youtube-transcript-api")
        return None

    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        transcript = None
        try:
            transcript = transcript_list.find_transcript([lang]).fetch()
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript([lang]).fetch()
            except Exception:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang]).fetch()
                except Exception:
                    if transcript_list:
                        try:
                            transcript = transcript_list.find_transcript([
                                getattr(entry, 'language_code', '')
                                for entry in transcript_list
                                if getattr(entry, 'language_code', '')
                            ]).fetch()
                        except Exception:
                            transcript = None

        if not transcript:
            print(f"[warning] No transcript returned for video_id={video_id} and lang={lang}")
            return None

        safe_video_id = re.sub(r'[^A-Za-z0-9_-]+', '_', video_id)
        subtitle_file = os.path.join(tempfile.gettempdir(), f"{safe_video_id}.{lang}.srt")
        with open(subtitle_file, 'w', encoding='utf-8') as f:
            for index, entry in enumerate(transcript, start=1):
                start_seconds = float(getattr(entry, 'start', 0.0) or 0.0)
                duration_seconds = float(getattr(entry, 'duration', 0.0) or 0.0)
                end_seconds = start_seconds + duration_seconds
                start_time = time.strftime('%H:%M:%S', time.gmtime(start_seconds)) + f",{int((start_seconds % 1) * 1000):03d}"
                end_time = time.strftime('%H:%M:%S', time.gmtime(end_seconds)) + f",{int((end_seconds % 1) * 1000):03d}"
                text = str(getattr(entry, 'text', '') or '').replace('\n', ' ').strip()
                f.write(f"{index}\n{start_time} --> {end_time}\n{text}\n\n")

        print(f"[info] Fallback transcript API saved subtitle file: {subtitle_file}")
        return subtitle_file
    except Exception as e:
        print(f"[warning] youtube-transcript-api fallback failed: {e}")
    return None


def _request_json(method: str, url: str, headers: Optional[Dict[str, str]] = None, payload: Optional[Dict[str, Any]] = None):
    request_headers = headers.copy() if headers else {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        request_headers['Content-Type'] = 'application/json'

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read().decode('utf-8', errors='replace')
        return json.loads(raw), response.headers


def _download_subtitle_asset(download_url: str, subtitle_id: str, lang: str) -> Optional[str]:
    print(f"[info] Downloading OpenSubtitles asset for subtitle_id={subtitle_id}")
    try:
        request = urllib.request.Request(
            download_url,
            headers={'User-Agent': 'Spider Subtitler/0.2'}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
            content_type = (response.headers.get('Content-Type') or '').lower()
    except Exception as e:
        print(f"[warning] OpenSubtitles download failed: {e}")
        return None

    safe_id = re.sub(r'[^A-Za-z0-9_-]+', '_', subtitle_id or 'opensubtitles')
    base_name = f"{safe_id}.{lang}"
    temp_dir = tempfile.gettempdir()

    if zipfile.is_zipfile(io.BytesIO(content)) or 'zip' in content_type:
        zip_path = os.path.join(temp_dir, f"{base_name}.zip")
        with open(zip_path, 'wb') as f:
            f.write(content)

        try:
            with zipfile.ZipFile(zip_path, 'r') as archive:
                for member in archive.namelist():
                    member_lower = member.lower()
                    if member_lower.endswith('.srt') or member_lower.endswith('.vtt'):
                        extracted_path = os.path.join(temp_dir, f"{base_name}{os.path.splitext(member)[1]}")
                        with archive.open(member) as source, open(extracted_path, 'wb') as target:
                            target.write(source.read())
                        print(f"[info] OpenSubtitles subtitle extracted to: {extracted_path}")
                        return extracted_path
        except Exception as e:
            print(f"[warning] Failed to extract OpenSubtitles archive: {e}")
            return None

    subtitle_path = os.path.join(temp_dir, f"{base_name}.srt")
    with open(subtitle_path, 'wb') as f:
        f.write(content)
    print(f"[info] OpenSubtitles subtitle saved to: {subtitle_path}")
    return subtitle_path


def fetch_subtitles_from_opensubtitles(query: str, lang: str = "en", api_key: str = "") -> Optional[str]:
    query = str(query or '').strip()
    if not query:
        return None

    api_key = str(api_key or OPENSUBTITLES_API_KEY).strip()
    if not api_key:
        print("[warning] OpenSubtitles API key not set. Set OPENSUBTITLES_API_KEY or enter it in the app.")
        return None

    print(f"[info] Searching OpenSubtitles for query={query!r}, lang={lang}")
    headers = {
        'Api-Key': api_key,
        'Accept': 'application/json',
        'User-Agent': 'Spider Subtitler/0.2'
    }

    try:
        params = urllib.parse.urlencode({
            'query': query,
            'languages': lang,
            'order_by': 'download_count',
            'order_direction': 'desc'
        })
        payload, _ = _request_json('GET', f'https://api.opensubtitles.com/api/v1/subtitles?{params}', headers=headers)
        results = payload.get('data') or []
        if not results:
            print(f"[warning] No OpenSubtitles search results for query={query!r} and lang={lang}")
            return None

        for index, result in enumerate(results[:5], start=1):
            attributes = result.get('attributes') or {}
            print(
                f"[info] OpenSubtitles result {index}: "
                f"id={result.get('id')} release={attributes.get('release') or attributes.get('feature_details', {}).get('title') or 'unknown'}"
            )

        best_match = results[0]
        subtitle_id = str(best_match.get('id') or '').strip()
        if not subtitle_id:
            print("[warning] OpenSubtitles search returned a result without an id")
            return None

        # Try the download endpoint first. Some accounts/regions may require a bearer token,
        # so we also fall back to any direct link-like field in the search payload.
        download_link = None
        try:
            download_payload = {"file_id": subtitle_id}
            download_response, _ = _request_json('POST', 'https://api.opensubtitles.com/api/v1/download', headers=headers, payload=download_payload)
            download_link = (
                download_response.get('link')
                or (download_response.get('data') or {}).get('link')
                or download_response.get('url')
                or (download_response.get('data') or {}).get('url')
            )
            if download_link:
                print(f"[info] OpenSubtitles download link acquired for subtitle_id={subtitle_id}")
        except Exception as e:
            print(f"[warning] OpenSubtitles download endpoint failed: {e}")

        if not download_link:
            attributes = best_match.get('attributes') or {}
            download_link = (
                attributes.get('download_link')
                or attributes.get('url')
                or attributes.get('files', [{}])[0].get('file_id')
            )

        if not download_link:
            print("[warning] OpenSubtitles search succeeded but no downloadable link was available")
            return None

        return _download_subtitle_asset(str(download_link), subtitle_id, lang)
    except Exception as e:
        print(f"[warning] OpenSubtitles search failed: {e}")
        return None


def sync_subtitles_with_ffsubsync(video_file: str, subtitle_file: str) -> Optional[str]:
    """Sync subtitle file to video using ffsubsync."""
    try:
        import ffsubsync
    except ImportError:
        print("[warning] ffsubsync not installed. Install with: pip install ffsubsync")
        return None
    
    try:
        synced_file = subtitle_file.replace('.srt', '_synced.srt')
        subprocess.run(
            ['ffsubsync', subtitle_file, '-i', video_file, '-o', synced_file],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        return synced_file if os.path.exists(synced_file) else None
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"[warning] ffsubsync sync failed: {e}")
    return None


def parse_srt_file(srt_file: str) -> Dict[float, str]:
    """Parse SRT subtitle file into dict {timestamp: text}."""
    subtitles = {}
    try:
        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by double newlines to get subtitle blocks
        blocks = content.strip().split('\n\n')
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            # Parse timestamp line (e.g., "00:00:10,000 --> 00:00:15,000")
            time_line = lines[1]
            if '-->' not in time_line:
                continue
            
            start_time_str = time_line.split('-->')[0].strip()
            # Convert to seconds
            try:
                parts = start_time_str.replace(',', '.').split(':')
                seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                text = ' '.join(lines[2:]).strip()
                if text:
                    subtitles[seconds] = text
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"[warning] Failed to parse subtitle file: {e}")
    
    return subtitles


def get_current_subtitle(subtitles: Dict[float, str], elapsed_seconds: float) -> Optional[str]:
    """Get subtitle text for current playback time."""
    # Find the most recent subtitle before current time
    valid_subs = [t for t in subtitles.keys() if t <= elapsed_seconds]
    if not valid_subs:
        return None
    
    closest_time = max(valid_subs)
    return subtitles.get(closest_time)


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
    audio_device = get_effective_audio_device()
    while True:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            # record short chunk mono 16k (platform-aware)
            record_chunk_to_wav(wav_path, duration_sec=chunk_seconds, audio_device=audio_device)
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
    audio_device = get_effective_audio_device()
    print(
        f"Live translation (no overlay) started. Listening on AUDIO_DEVICE={audio_device}, "
        f"chunk={chunk_seconds}s, source_language={source_language}."
    )
    if IS_MACOS:
        print(
            "macOS tip: ensure this app has Microphone permission in "
            "System Settings > Privacy & Security > Microphone."
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
            record_chunk_to_wav(wav_path, duration_sec=chunk_seconds, audio_device=audio_device)
        except (subprocess.CalledProcessError, RuntimeError) as e:
            err_text = str(e)
            if err_text == last_capture_error:
                repeated_capture_error_count += 1
            else:
                last_capture_error = err_text
                repeated_capture_error_count = 1

            if repeated_capture_error_count == 1 or repeated_capture_error_count % 10 == 0:
                print("audio capture failed; check device/tooling:", err_text)
                if IS_MACOS:
                    print(
                        "macOS hint: set Audio Device to a valid :<index> (for MacBook Air mic often :2), "
                        "then confirm Microphone permission for this app."
                    )
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
    
    # Subtitle fetching and syncing options
    parser.add_argument("--subtitle-file", metavar="PATH", help="Use existing SRT/VTT subtitle file instead of live transcription")
    parser.add_argument("--opensubtitles-query", metavar="QUERY", help="Search OpenSubtitles by movie or episode title")
    parser.add_argument("--opensubtitles-api-key", metavar="KEY", default=OPENSUBTITLES_API_KEY, help="OpenSubtitles API key (optional if set via env)")
    parser.add_argument("--youtube-id", metavar="VIDEO_ID", help="Fetch subtitles from YouTube video ID")
    parser.add_argument("--subtitle-lang", default=SUBTITLE_LANG, help="Language for fetched subtitles (default: en)")
    parser.add_argument("--sync-video", metavar="VIDEO_FILE", help="Video file to sync subtitles with using ffsubsync")
    
    args = parser.parse_args()

    # Handle subtitle fetching from external sources.
    if args.opensubtitles_query:
        subtitle_file = fetch_subtitles_from_opensubtitles(args.opensubtitles_query, args.subtitle_lang, args.opensubtitles_api_key)
        if subtitle_file:
            args.subtitle_file = subtitle_file
            print(f"✓ OpenSubtitles file saved to: {subtitle_file}")
        else:
            print(f"[warning] OpenSubtitles did not produce a subtitle file for query={args.opensubtitles_query!r}; trying the next source")

    if args.youtube_id:
        args.youtube_id = normalize_youtube_video_id(args.youtube_id)
        print(f"Using YouTube video ID: {args.youtube_id}")
        subtitle_file = fetch_subtitles_from_youtube(args.youtube_id, args.subtitle_lang)
        if subtitle_file:
            args.subtitle_file = subtitle_file
            print(f"✓ Subtitles saved to: {subtitle_file}")
        else:
            print(f"[warning] YouTube subtitle fetch failed for ID: {args.youtube_id}, lang: {args.subtitle_lang}; continuing to live transcription")

    # Handle subtitle file syncing
    if args.subtitle_file and args.sync_video:
        print(f"Syncing subtitles with video using ffsubsync...")
        synced = sync_subtitles_with_ffsubsync(args.sync_video, args.subtitle_file)
        if synced:
            args.subtitle_file = synced
            print(f"✓ Synced subtitles saved to: {synced}")
        else:
            print("✗ Subtitle syncing failed, using original file")

    # If subtitle file provided, use it instead of live transcription
    if args.subtitle_file:
        if not os.path.exists(args.subtitle_file):
            raise FileNotFoundError(f"Subtitle file not found: {args.subtitle_file}")
        print(f"Using subtitle file: {args.subtitle_file}")
        subtitles = parse_srt_file(args.subtitle_file)
        if not subtitles:
            print("✗ No subtitles found in file")
            return
        print(f"✓ Loaded {len(subtitles)} subtitle entries")
        print("Subtitle display mode ready. Press Ctrl+C to exit.")
        if args.emit_json:
            emit_status("ready", True)
        try:
            elapsed = 0.0
            last_subtitle = None
            while True:
                current_sub = get_current_subtitle(subtitles, elapsed)
                if current_sub and current_sub != last_subtitle:
                    emit_subtitle(current_sub, args.emit_json)
                    last_subtitle = current_sub
                time.sleep(0.1)
                elapsed += 0.1
        except KeyboardInterrupt:
            pass
        return

    args.whisper_bin = validate_runtime_paths(args.whisper_bin, args.model)

    if args.test_translate:
        if not os.path.exists(args.test_translate):
            raise FileNotFoundError(f"Audio file not found: {args.test_translate}")
        args.whisper_bin = validate_runtime_paths(args.whisper_bin, args.model)

        translated = run_translate_once(args.test_translate, args.whisper_bin, args.model)
        print(translated)
        return

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