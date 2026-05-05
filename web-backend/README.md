# Spider Subtitler - Web Backend

A Node.js/Express server that manages the Python subtitle daemon and provides a web UI for controlling it.

## Features

- 🌐 Web-based UI (accessible via browser)
- ⚙️ Real-time settings adjustment (no restart needed)
- 📊 Audio level visualization  
- 💬 Subtitle history tracking
- 📝 Live logs
- 🎵 YouTube subtitle integration
- 🔊 Audio filter control
- 🔗 WebSocket for real-time updates

## Quick Start

### 1. Install Dependencies

```bash
cd web-backend
npm install
```

### 2. Start the Server

```bash
npm start
```

The server will start on `http://localhost:3000`

### 3. Open in Browser

Visit `http://localhost:3000` in your web browser.

## Environment Variables

```bash
# Port to run on (default: 3000)
export PORT=3000

# Python binary (default: python3)
export PYTHON_BIN=python3
```

## API Endpoints

### GET `/api/status`
Get daemon status and current configuration.

```bash
curl http://localhost:3000/api/status
```

Response:
```json
{
  "daemon_running": false,
  "config": {
    "sourceLanguage": "ja",
    "chunkSeconds": 2,
    "minAudioRms": 250,
    "enableSpeechFilter": true,
    "youtubeId": "",
    "subtitleLang": "en"
  },
  "platform": "darwin",
  "python_version": "3.9.0"
}
```

### POST `/api/config`
Update configuration.

```bash
curl -X POST http://localhost:3000/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "sourceLanguage": "ja",
    "chunkSeconds": 2,
    "minAudioRms": 150,
    "enableSpeechFilter": true
  }'
```

### POST `/api/daemon/start`
Start the daemon.

```bash
curl -X POST http://localhost:3000/api/daemon/start
```

### POST `/api/daemon/stop`
Stop the daemon.

```bash
curl -X POST http://localhost:3000/api/daemon/stop
```

## WebSocket Messages

### Client → Server

**Start daemon:**
```json
{"type": "start"}
```

**Stop daemon:**
```json
{"type": "stop"}
```

**Update configuration:**
```json
{
  "type": "config",
  "data": {
    "sourceLanguage": "ja",
    "chunkSeconds": 2,
    "minAudioRms": 250,
    "enableSpeechFilter": true,
    "youtubeId": "VIDEO_ID",
    "subtitleLang": "en"
  }
}
```

### Server → Client

**Subtitle:**
```json
{"type": "subtitle", "text": "Translated text here"}
```

**Status update:**
```json
{"type": "status", "stage": "recording"}
```

**Audio level:**
```json
{"type": "audio-level", "rms": 215.5, "threshold": 250}
```

**Configuration:**
```json
{"type": "config", "data": {...}}
```

**Error:**
```json
{"type": "error", "message": "Error description"}
```

## Configuration

The daemon accepts the following settings:

### `sourceLanguage`
Source language for speech recognition.
- Values: `"ja"`, `"en"`, `"es"`, `"fr"`, `"de"`, `"auto"`
- Default: `"ja"`

### `chunkSeconds`
Audio chunk duration in seconds.
- Values: `1` to `10`
- Default: `2`

### `minAudioRms`
Minimum audio level (RMS) threshold. Higher = only very loud audio.
- Values: `50` to `500`
- Default: `250`

### `enableSpeechFilter`
Enable audio filtering to reduce music and background noise.
- Values: `true` or `false`
- Default: `true`
- Filter: `highpass=80Hz, lowpass=8000Hz, volume=1.25, alimiter=0.95`

### `youtubeId`
YouTube video ID to fetch subtitles from (requires `yt-dlp`).
- Values: Video ID string (e.g., `"jNQXAC9IVRw"`)
- Default: `""`

### `subtitleLang`
Language for fetched YouTube subtitles.
- Values: `"en"`, `"ja"`, `"es"`, `"fr"`, `"de"`, `"zh"`
- Default: `"en"`

## Troubleshooting

### WebSocket Connection Failed
- Check that the server is running on the correct port
- Verify firewall allows WebSocket connections
- Try accessing `http://localhost:3000` directly in browser

### Daemon Won't Start
- Check that Python is installed: `python3 --version`
- Verify `id_subtitle_deamon.py` path is correct
- Check logs in the web UI for error details

### No Audio Input
- Ensure microphone is enabled and working
- On macOS, check System Settings > Privacy & Security > Microphone
- Try running the daemon directly to see specific device errors

### Poor Subtitle Quality
- Try adjusting `minAudioRms` lower for quiet speech
- Toggle `enableSpeechFilter` on/off
- Try different `sourceLanguage` setting
- Use `youtubeId` for YouTube videos (much more accurate)

## Development

For development with auto-reload:

```bash
npm run dev
```

This uses `nodemon` to automatically restart on file changes.

## Deployment

For production deployment:

### Docker (Recommended)

Create a `Dockerfile` in the web-backend directory:

```dockerfile
FROM node:18-alpine

WORKDIR /app

# Install Python and required tools
RUN apk add --no-cache python3 ffmpeg

COPY package*.json ./
RUN npm ci --only=production

COPY . .
COPY ../id_subtitle_deamon.py ../

EXPOSE 3000

CMD ["npm", "start"]
```

Build and run:

```bash
docker build -t spider-subtitler-web .
docker run -p 3000:3000 --device /dev/snd spider-subtitler-web
```

### Heroku

```bash
heroku create spider-subtitler
git push heroku main
heroku open
```

### AWS / DigitalOcean

Deploy the Node.js app to your hosting platform. Ensure:
- Python 3.9+ is installed
- FFmpeg is available
- Audio device is accessible (for live transcription)

## Security Considerations

⚠️ **Important:** This server currently has NO authentication. 

Before exposing to the internet:
- Add authentication (OAuth, JWT, etc.)
- Use HTTPS/WSS
- Implement rate limiting
- Restrict API endpoints
- Use environment variables for sensitive config

## Contributing

To contribute improvements:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or suggestions:
- Check [IMPROVEMENTS.md](../IMPROVEMENTS.md) for configuration guides
- Review logs in the web UI
- Check console output on the server

## Related

- [Main README](../README.md)
- [Improvements Guide](../IMPROVEMENTS.md)
- [Python Daemon](../id_subtitle_deamon.py)
