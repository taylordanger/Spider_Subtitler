/**
 * Spider Subtitler Web - Client-side JavaScript
 * Handles WebSocket communication, UI updates, and settings management
 */

// Configuration
const API_BASE = window.location.origin;
const WS_URL = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + 
               '//' + window.location.host;

// DOM Elements
const elements = {
  // Controls
  startBtn: document.getElementById('startBtn'),
  stopBtn: document.getElementById('stopBtn'),
  applyConfigBtn: document.getElementById('applyConfigBtn'),
  clearHistoryBtn: document.getElementById('clearHistoryBtn'),
  
  // Settings
  sourceLanguage: document.getElementById('sourceLanguage'),
  chunkSeconds: document.getElementById('chunkSeconds'),
  chunkSecondsValue: document.getElementById('chunkSecondsValue'),
  minAudioRms: document.getElementById('minAudioRms'),
  minAudioRmsValue: document.getElementById('minAudioRmsValue'),
  enableSpeechFilter: document.getElementById('enableSpeechFilter'),
  openSubtitlesQuery: document.getElementById('openSubtitlesQuery'),
  openSubtitlesApiKey: document.getElementById('openSubtitlesApiKey'),
  youtubeId: document.getElementById('youtubeId'),
  subtitleLang: document.getElementById('subtitleLang'),
  
  // Display
  subtitleText: document.getElementById('subtitleText'),
  historyContainer: document.getElementById('historyContainer'),
  logBox: document.getElementById('logBox'),
  
  // Status
  daemonStatus: document.getElementById('daemonStatus'),
  statusText: document.getElementById('statusText'),
  meterFill: document.getElementById('meterFill'),
  meterText: document.getElementById('meterText')
};

// State
let socket = null;
let historyList = [];
let logLines = [];
const MAX_HISTORY = 50;
const MAX_LOG_LINES = 100;

// ============= WebSocket Management =============

function connectWebSocket() {
  console.log('Connecting to WebSocket...');
  socket = new WebSocket(WS_URL);
  
  socket.onopen = () => {
    console.log('WebSocket connected');
    updateStatus('connected');
    appendLog('WebSocket connected');
  };
  
  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      handleMessage(message);
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e);
    }
  };
  
  socket.onerror = (error) => {
    console.error('WebSocket error:', error);
    updateStatus('error');
    appendLog(`[ERROR] WebSocket error: ${error}`);
  };
  
  socket.onclose = () => {
    console.log('WebSocket closed, reconnecting in 3s...');
    updateStatus('disconnected');
    appendLog('WebSocket disconnected, reconnecting in 3s...');
    setTimeout(connectWebSocket, 3000);
  };
}

function sendMessage(message) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message));
  } else {
    console.warn('WebSocket not connected');
  }
}

// ============= Message Handling =============

function handleMessage(msg) {
  switch (msg.type) {
    case 'subtitle':
      displaySubtitle(msg.text);
      addToHistory(msg.text);
      break;
      
    case 'status':
      updateDaemonStatus(msg.stage);
      break;
      
    case 'audio-level':
      updateMeterDisplay(msg.rms, msg.threshold);
      break;
      
    case 'config':
      updateConfigUI(msg.data);
      break;
      
    case 'error':
      appendLog(`[ERROR] ${msg.message}`);
      break;
      
    default:
      appendLog(`[${msg.type}] ${JSON.stringify(msg)}`);
  }
}

// ============= UI Updates =============

function displaySubtitle(text) {
  elements.subtitleText.textContent = text;
  elements.subtitleText.classList.add('updated');
  setTimeout(() => {
    elements.subtitleText.classList.remove('updated');
  }, 300);
}

function addToHistory(text) {
  historyList.unshift({
    text,
    timestamp: new Date().toLocaleTimeString()
  });
  
  if (historyList.length > MAX_HISTORY) {
    historyList.pop();
  }
  
  renderHistory();
}

function renderHistory() {
  elements.historyContainer.innerHTML = historyList
    .map((item, idx) => `
      <div class="history-item" data-index="${idx}">
        <span class="history-time">${item.timestamp}</span>
        <span class="history-text">${escapeHtml(item.text)}</span>
      </div>
    `)
    .join('');
}

function updateMeterDisplay(rms, threshold) {
  const percent = Math.max(0, Math.min(100, Math.round((rms / threshold) * 100)));
  elements.meterFill.style.width = `${percent}%`;
  elements.meterText.textContent = `RMS: ${Math.round(rms)} / ${threshold}`;
}

function updateDaemonStatus(stage) {
  const statusMap = {
    'idle': { color: '#999', label: 'Idle' },
    'starting': { color: '#ff9d00', label: 'Starting' },
    'recording': { color: '#ff6b6b', label: 'Recording' },
    'transcribing': { color: '#4dabf7', label: 'Transcribing' },
    'ready': { color: '#51cf66', label: 'Ready' },
    'stopped': { color: '#868e96', label: 'Stopped' }
  };
  
  const status = statusMap[stage] || statusMap['idle'];
  elements.daemonStatus.style.color = status.color;
  elements.daemonStatus.textContent = '●';
  elements.statusText.textContent = status.label;
}

function updateStatus(connectionStatus) {
  if (connectionStatus === 'connected') {
    elements.statusText.textContent = 'Connected';
    elements.daemonStatus.style.color = '#51cf66';
  } else if (connectionStatus === 'disconnected') {
    elements.statusText.textContent = 'Disconnected';
    elements.daemonStatus.style.color = '#999';
  } else if (connectionStatus === 'error') {
    elements.statusText.textContent = 'Error';
    elements.daemonStatus.style.color = '#ff6b6b';
  }
}

function updateConfigUI(config) {
  elements.sourceLanguage.value = config.sourceLanguage || 'ja';
  elements.chunkSeconds.value = config.chunkSeconds || 2;
  elements.chunkSecondsValue.value = config.chunkSeconds || 2;
  elements.minAudioRms.value = config.minAudioRms || 250;
  elements.minAudioRmsValue.value = config.minAudioRms || 250;
  elements.enableSpeechFilter.checked = config.enableSpeechFilter !== false;
  elements.openSubtitlesQuery.value = config.openSubtitlesQuery || '';
  elements.openSubtitlesApiKey.value = config.openSubtitlesApiKey || '';
  elements.youtubeId.value = config.youtubeId || '';
  elements.subtitleLang.value = config.subtitleLang || 'en';
}

function appendLog(line) {
  logLines.push(`[${new Date().toLocaleTimeString()}] ${line}`);
  if (logLines.length > MAX_LOG_LINES) {
    logLines.shift();
  }
  elements.logBox.textContent = logLines.join('\n');
  elements.logBox.scrollTop = elements.logBox.scrollHeight;
}

// ============= Event Listeners =============

// Slider sync
elements.chunkSeconds.addEventListener('input', (e) => {
  elements.chunkSecondsValue.value = e.target.value;
});

elements.chunkSecondsValue.addEventListener('change', (e) => {
  elements.chunkSeconds.value = e.target.value;
});

elements.minAudioRms.addEventListener('input', (e) => {
  elements.minAudioRmsValue.value = e.target.value;
});

elements.minAudioRmsValue.addEventListener('change', (e) => {
  elements.minAudioRms.value = e.target.value;
});

// Control buttons
elements.startBtn.addEventListener('click', () => {
  sendMessage({ type: 'start' });
  appendLog('Starting daemon...');
});

elements.stopBtn.addEventListener('click', () => {
  sendMessage({ type: 'stop' });
  appendLog('Stopping daemon...');
});

elements.applyConfigBtn.addEventListener('click', () => {
  const config = {
    sourceLanguage: elements.sourceLanguage.value,
    chunkSeconds: parseInt(elements.chunkSeconds.value) || 2,
    minAudioRms: parseInt(elements.minAudioRms.value) || 250,
    enableSpeechFilter: elements.enableSpeechFilter.checked,
    openSubtitlesQuery: elements.openSubtitlesQuery.value.trim(),
    openSubtitlesApiKey: elements.openSubtitlesApiKey.value.trim(),
    youtubeId: elements.youtubeId.value.trim(),
    subtitleLang: elements.subtitleLang.value
  };
  
  appendLog('Applying configuration...');
  sendMessage({
    type: 'config',
    data: config
  });
});

elements.clearHistoryBtn.addEventListener('click', () => {
  historyList = [];
  renderHistory();
  appendLog('History cleared');
});

// ============= Utility Functions =============

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ============= Initialization =============

document.addEventListener('DOMContentLoaded', () => {
  appendLog('Spider Subtitler Web initialized');
  connectWebSocket();
  
  // Fetch initial status
  fetch(`${API_BASE}/api/status`)
    .then(r => r.json())
    .then(status => {
      appendLog(`Platform: ${status.platform}`);
      updateConfigUI(status.config);
    })
    .catch(e => appendLog(`[ERROR] Failed to fetch status: ${e.message}`));
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  if (socket) {
    socket.close();
  }
});
