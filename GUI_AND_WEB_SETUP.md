# Spider Subtitler - GUI & Web Setup Guide

This guide covers using the new GUI controls in the Electron app and setting up the web backend.

## Quick Start

### Option 1: Electron App (Desktop)
The easiest way to get started with GUI controls:

```bash
cd electron-subtitle-app
npm start
```

Then use the GUI sliders to adjust settings in real-time.

### Option 2: Web App (Browser-based)
For a browser interface with local backend:

```bash
cd web-backend
npm install
npm start
```

Then open `http://localhost:3000` in your browser.

---

## Electron App - New Features

### Audio Tuning Sliders

The Electron app now includes interactive sliders for audio settings:

#### Min Audio RMS
- **Slider range:** 50 - 500
- **Lower values:** Capture quieter dialogue (but more noise)
- **Higher values:** Only process loud audio (fewer false positives)
- **Tip for anime:** Start at 150-200 for quieter female voices

#### Speech Filter Toggle
- **On (default):** `highpass=80Hz, lowpass=8000Hz, volume=1.25, alimiter=0.95`
  - Reduces music misclassification
  - Preserves female voice clarity
  - Good for mixed speech content
- **Off:** No frequency filtering
  - Captures full audio spectrum
  - Slower but potentially more accurate
  - Try if speech filter is cutting off important frequencies

#### Chunk Duration
- Range: 1-10 seconds
- Lower (2-3s): More responsive, more frequent transcription
- Higher (4-6s): Faster, less computational overhead

### Settings Persistence

All settings are saved to browser localStorage and restored when you restart.

**To reset settings:**
1. Open browser DevTools (F12)
2. Go to Console
3. Run: `localStorage.removeItem('laserdisc-subtitles-config-v2')`
4. Refresh the page

### YouTube Subtitle Integration

In the Electron app, you can now:

1. Enter a YouTube video ID
2. Select subtitle language
3. Settings are sent to the daemon via environment variables

**Requirements:** `pip install yt-dlp`

---

## Web Backend

### Architecture

```
┌─────────────┐
│  Web Browser │
│  (HTML/CSS/JS)
└──────┬──────┘
       │ WebSocket
       │ HTTP
       │
┌──────▼──────────────┐
│ Node.js Express     │
│ - HTTP API          │
│ - WebSocket Server  │
│ - Process Manager   │
└──────┬──────────────┘
       │ spawn()
       │
┌──────▼──────────────┐
│ Python Daemon       │
│ id_subtitle_deamon  │
└─────────────────────┘
```

### Setup

#### 1. Install Node Dependencies

```bash
cd web-backend
npm install
```

#### 2. Set Environment Variables (Optional)

```bash
# macOS
export WHISPER_BIN="/opt/homebrew/bin/whisper"
export MODEL_PATH="$HOME/models/ggml-medium.bin"
export PYTHON_BIN="python3"
export PORT=3000
```

#### 3. Start the Server

```bash
npm start
```

Expected output:
```
╔════════════════════════════════════════╗
║  Spider Subtitler - Web Backend v0.2.0 ║
╚════════════════════════════════════════╝

✓ Server running at http://localhost:3000
✓ WebSocket at ws://localhost:3000
✓ Daemon script: /Users/darkstar/Spider_Subtitler/id_subtitle_deamon.py
✓ Python binary: python3

Press Ctrl+C to stop
```

#### 4. Open in Browser

Visit `http://localhost:3000` in your web browser.

### Web UI Features

- **Real-time sliders** for audio settings
- **Start/Stop buttons** for daemon control
- **Audio level meter** showing RMS values
- **Subtitle history** showing last 50 subtitles
- **Live logs** for debugging
- **YouTube subtitle support** with dropdown menu
- **Settings auto-save** to server

### Using YouTube Subtitles

1. Find the YouTube video ID (from URL: `youtube.com/watch?v=VIDEO_ID`)
2. In the web UI, paste the ID into "YouTube Video ID"
3. Select subtitle language
4. Click "Apply Settings"
5. Click "▶️ Start"

The daemon will:
1. Fetch subtitles from YouTube (requires `yt-dlp`)
2. Parse and stream them in real-time
3. Display in the subtitle area

**Install yt-dlp:**
```bash
pip install yt-dlp
```

### Using OpenSubtitles

1. Enter a movie or episode title in the OpenSubtitles Title / Query field
2. Paste your OpenSubtitles API key, or set `OPENSUBTITLES_API_KEY`
3. Click "Start"

If OpenSubtitles cannot return a subtitle file, the app will fall back to YouTube and then live transcription.

---

## Configuration Reference

All settings can be controlled from both UI versions:

### sourceLanguage
- **ja** (Japanese) - for anime
- **en** (English)
- **es** (Spanish)
- **fr** (French)
- **de** (German)
- **auto** - auto-detect

### chunkSeconds
How long to listen before processing:
- **2s** (default) - responsive, frequent transcription
- **3-4s** - balanced
- **5-6s** - better for longer sentences

### minAudioRms
Audio threshold for filtering silence:
- **50-150** - very sensitive (lots of noise but catches quiet voices)
- **150-250** - balanced (default 250)
- **250-500** - strict (only loud audio, fewer false positives)

### enableSpeechFilter
Audio preprocessing:
- **true** (default) - reduces music, improves dialogue clarity
- **false** - preserves full audio spectrum

### youtubeId
YouTube video ID for subtitle fetching:
- Leave empty for live microphone input
- Requires `yt-dlp` installed

### subtitleLang
Language for fetched subtitles:
- **en, ja, es, fr, de, zh**
- Ignored if youtubeId is empty

---

## Recommended Settings for Anime

### For Quiet Dialogue

```
sourceLanguage: ja
chunkSeconds: 3
minAudioRms: 100
enableSpeechFilter: true
```

### For Mixed Male/Female Voices

```
sourceLanguage: ja
chunkSeconds: 2
minAudioRms: 150
enableSpeechFilter: true
```

### For YouTube Videos

```
youtubeId: [paste video ID]
subtitleLang: en
```

Then click "Apply Settings" and "Start".

---

## Troubleshooting

### Web Backend Won't Start

```bash
# Check Python is accessible
python3 --version

# Check daemon script exists
ls ../id_subtitle_deamon.py

# Try verbose mode
DEBUG=* npm start
```

### WebSocket Connection Failed

- Ensure server is running: `curl http://localhost:3000`
- Check firewall blocks port 3000
- Try different port: `PORT=3001 npm start`

### Settings Not Saving (Electron)

Clear localStorage:
```javascript
// In DevTools Console (F12)
localStorage.clear()
```

### Daemon Won't Start

Check logs in web UI or Electron console:
- Missing Whisper binary path
- Missing model file
- Audio device not found (macOS: might need `:2` instead of `:0`)

### No Subtitles Appearing

1. Check status indicator (should be green when recording)
2. Verify audio is being captured (check mic level meter)
3. Look at logs for errors
4. Try lowering `minAudioRms` value
5. Try disabling speech filter

---

## Comparing Electron vs Web

| Feature | Electron | Web Backend |
|---------|----------|------------|
| Desktop App | ✓ | - |
| Browser UI | - | ✓ |
| GUI Sliders | ✓ | ✓ |
| Video Overlay | ✓ | - |
| Real-time Settings | ✓ | ✓ |
| YouTube Subtitles | ✓ | ✓ |
| Local Processing | ✓ | ✓ |
| Theater Mode | ✓ | - |
| Installable | ✓ | - |
| Dev Server | - | ✓ |
| Auto-Reload | - | ✓ (with nodemon) |

---

## Rebuilding Distributions

### Electron
```bash
cd electron-subtitle-app
npm run dist
# Output: dist/Laserdisc\ Live\ Subtitles-*.dmg (macOS installer)
```

### Web Backend
For production deployment:

**Docker:**
```bash
cd web-backend
docker build -t spider-subtitler-web .
docker run -p 3000:3000 spider-subtitler-web
```

**Manual deployment:**
```bash
# Copy to server
scp -r web-backend/ user@server:/app/

# On server
cd /app/web-backend
npm ci --only=production
NODE_ENV=production npm start
```

---

## Next Steps

1. **Test the Electron GUI:** `npm start` in electron-subtitle-app
2. **Try the web version:** Follow the web-backend setup above
3. **Adjust settings** using sliders until you get good results
4. **Report issues** or improvements to the GitHub repo

For more details:
- See [IMPROVEMENTS.md](../IMPROVEMENTS.md) for comprehensive tuning guide
- See [web-backend/README.md](../web-backend/README.md) for API documentation
- Check [id_subtitle_deamon.py](../id_subtitle_deamon.py) for daemon options

---

## Tips for Best Results

✨ **For anime subtitles:**
1. Start with YouTube ID (highest quality)
2. Use `sourceLanguage: ja`
3. Adjust `minAudioRms` based on voice volume
4. Toggle `enableSpeechFilter` if music interferes

✨ **For live transcription:**
1. Use `enableSpeechFilter: true`
2. Start with `minAudioRms: 250`
3. Lower it if missing quiet dialogue
4. Raise it if getting too much noise

✨ **Performance:**
1. Increase `chunkSeconds` for faster processing
2. Use `enableSpeechFilter: false` to skip audio processing (but less accurate)
3. Restart the daemon if it gets slow (memory leak possible)

Happy subtitling! 🎬
