#!/usr/bin/env node
/**
 * Spider Subtitler - Web Backend Server
 * 
 * This Node.js/Express server provides:
 * 1. HTTP API to manage daemon settings
 * 2. WebSocket connection for real-time subtitle streaming
 * 3. Web UI serving (static files)
 * 4. Python daemon process management
 */

const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const ws = require('ws');
const http = require('http');
const os = require('os');

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const DAEMON_SCRIPT = path.join(__dirname, '..', 'id_subtitle_deamon.py');
const WHISPER_BIN = process.env.WHISPER_BIN || '/home/pi/whisper.cpp/main';
const MODEL_PATH = process.env.MODEL_PATH || '/home/pi/whisper.cpp/models/ggml-small.bin';

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(express.static(path.join(__dirname, 'public')));

// State
let daemonProcess = null;
let wsClients = new Set();
let currentConfig = {
  sourceLanguage: 'ja',
  chunkSeconds: 2,
  minAudioRms: 250,
  enableSpeechFilter: true,
  openSubtitlesQuery: '',
  openSubtitlesApiKey: '',
  youtubeId: '',
  subtitleLang: 'en'
};

function normalizeYoutubeVideoId(value) {
  const rawValue = String(value || '').trim();
  if (!rawValue) {
    return '';
  }

  const directMatch = rawValue.match(/(?:v=|youtu\.be\/|shorts\/)([A-Za-z0-9_-]{6,})/);
  if (directMatch) {
    return directMatch[1];
  }

  if (rawValue.startsWith('http://') || rawValue.startsWith('https://')) {
    try {
      const url = new URL(rawValue);
      const queryId = (url.searchParams.get('v') || '').trim();
      if (queryId) {
        return queryId;
      }
      const parts = url.pathname.split('/').filter(Boolean);
      if (parts.length) {
        return parts[parts.length - 1].split('?')[0].split('&')[0].trim();
      }
    } catch (_) {
      // fall through to raw value
    }
  }

  return rawValue;
}

// ============= Daemon Process Management =============

/**
 * Build command-line arguments for the Python daemon
 */
function buildDaemonArgs() {
  const args = [
    DAEMON_SCRIPT,
    '--whisper-bin', WHISPER_BIN,
    '--model', MODEL_PATH,
    '--no-overlay',
    '--emit-json',
    '--source-language', currentConfig.sourceLanguage,
    '--chunk-seconds', String(currentConfig.chunkSeconds)
  ];

  if (currentConfig.openSubtitlesQuery && currentConfig.openSubtitlesQuery.trim()) {
    args.push('--opensubtitles-query', currentConfig.openSubtitlesQuery.trim());
    args.push('--subtitle-lang', currentConfig.subtitleLang);
  }
  
  // Add speech filter flag
  if (!currentConfig.enableSpeechFilter) {
    args.push('--no-speech-filter');
  }
  
  // Add YouTube ID if provided
  if (currentConfig.youtubeId && currentConfig.youtubeId.trim()) {
    const youtubeId = normalizeYoutubeVideoId(currentConfig.youtubeId);
    args.push('--youtube-id', youtubeId);
    args.push('--subtitle-lang', currentConfig.subtitleLang);
  }
  
  return args;
}

/**
 * Start the Python daemon process
 */
function startDaemon() {
  if (daemonProcess) {
    console.log('Daemon already running');
    return;
  }
  
  const args = buildDaemonArgs();
  console.log(`Starting daemon: ${PYTHON_BIN} ${args.join(' ')}`);
  
  daemonProcess = spawn(PYTHON_BIN, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    env: {
      ...process.env,
      OPENSUBTITLES_API_KEY: String(currentConfig.openSubtitlesApiKey || process.env.OPENSUBTITLES_API_KEY || '')
    }
  });
  
  // Handle stdout (JSON lines from daemon)
  daemonProcess.stdout.on('data', (data) => {
    const lines = data.toString().split('\n').filter(l => l.trim());
    lines.forEach(line => {
      try {
        const msg = JSON.parse(line);
        broadcastToClients(msg);
      } catch (e) {
        console.log('[daemon stdout]', line);
      }
    });
  });
  
  // Handle stderr
  daemonProcess.stderr.on('data', (data) => {
    console.error('[daemon stderr]', data.toString());
    broadcastToClients({
      type: 'error',
      message: data.toString().trim()
    });
  });
  
  daemonProcess.on('close', (code) => {
    console.log(`Daemon exited with code ${code}`);
    daemonProcess = null;
    broadcastToClients({
      type: 'status',
      stage: 'stopped'
    });
  });
  
  daemonProcess.on('error', (err) => {
    console.error('Daemon error:', err);
    daemonProcess = null;
  });
}

/**
 * Stop the Python daemon process
 */
function stopDaemon() {
  if (!daemonProcess) {
    console.log('No daemon running');
    return;
  }
  
  console.log('Stopping daemon...');
  daemonProcess.kill('SIGTERM');
  
  // Force kill after 3 seconds
  setTimeout(() => {
    if (daemonProcess) {
      daemonProcess.kill('SIGKILL');
      daemonProcess = null;
    }
  }, 3000);
}

// ============= WebSocket Server =============

function broadcastToClients(message) {
  const data = JSON.stringify(message);
  wsClients.forEach(client => {
    if (client.readyState === ws.OPEN) {
      client.send(data);
    }
  });
}

const server = http.createServer(app);
const wss = new ws.Server({ server });

wss.on('connection', (client) => {
  console.log('WebSocket client connected');
  wsClients.add(client);
  
  // Send current config to new client
  client.send(JSON.stringify({
    type: 'config',
    data: currentConfig
  }));
  
  client.on('message', (raw) => {
    try {
      const msg = JSON.parse(raw);
      console.log('[ws message]', msg.type);
      
      // Handle different message types
      if (msg.type === 'start') {
        startDaemon();
      } else if (msg.type === 'stop') {
        stopDaemon();
      } else if (msg.type === 'config') {
        // Update config and restart daemon if needed
        const oldYtId = currentConfig.youtubeId;
        Object.assign(currentConfig, msg.data);
        
        if (daemonProcess) {
          stopDaemon();
          // Restart with new config
          setTimeout(startDaemon, 500);
        }
        
        // Broadcast updated config to all clients
        broadcastToClients({
          type: 'config',
          data: currentConfig
        });
      }
    } catch (e) {
      console.error('[ws error]', e.message);
    }
  });
  
  client.on('close', () => {
    console.log('WebSocket client disconnected');
    wsClients.delete(client);
  });
  
  client.on('error', (err) => {
    console.error('[ws client error]', err);
  });
});

// ============= HTTP Routes =============

/**
 * GET /api/status - Get daemon status and config
 */
app.get('/api/status', (req, res) => {
  res.json({
    daemon_running: daemonProcess !== null,
    config: currentConfig,
    platform: os.platform(),
    python_version: process.env.PYTHON_VERSION || 'unknown'
  });
});

/**
 * POST /api/config - Update configuration
 */
app.post('/api/config', (req, res) => {
  try {
    Object.assign(currentConfig, req.body);
    
    // Restart daemon if running
    if (daemonProcess) {
      stopDaemon();
      setTimeout(startDaemon, 500);
    }
    
    // Broadcast to WebSocket clients
    broadcastToClients({
      type: 'config',
      data: currentConfig
    });
    
    res.json({ success: true, config: currentConfig });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/**
 * POST /api/daemon/start - Start the daemon
 */
app.post('/api/daemon/start', (req, res) => {
  try {
    startDaemon();
    res.json({ success: true, message: 'Daemon started' });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/**
 * POST /api/daemon/stop - Stop the daemon
 */
app.post('/api/daemon/stop', (req, res) => {
  try {
    stopDaemon();
    res.json({ success: true, message: 'Daemon stopped' });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/**
 * GET / - Serve web UI
 */
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ============= Error Handling =============

process.on('SIGINT', () => {
  console.log('\nShutting down...');
  stopDaemon();
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\nShutting down...');
  stopDaemon();
  process.exit(0);
});

// ============= Start Server =============

server.listen(PORT, () => {
  console.log(`
╔════════════════════════════════════════╗
║  Spider Subtitler - Web Backend v0.2.0 ║
╚════════════════════════════════════════╝

✓ Server running at http://localhost:${PORT}
✓ WebSocket at ws://localhost:${PORT}
✓ Daemon script: ${DAEMON_SCRIPT}
✓ Python binary: ${PYTHON_BIN}

Press Ctrl+C to stop
  `.trim());
});
