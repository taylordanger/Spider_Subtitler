/*This file is part of Electron Subtitle App, licensed under MIT License (MIT). */ 

const subtitleText = document.getElementById('subtitleText');
const logBox = document.getElementById('logBox');
const statusBadge = document.getElementById('statusBadge');
const micLevelFill = document.getElementById('micLevelFill');
const micLevelText = document.getElementById('micLevelText');

const whisperBinInput = document.getElementById('whisperBin');
const modelPathInput = document.getElementById('modelPath');
const audioDeviceInput = document.getElementById('audioDevice');
const sourceLanguageInput = document.getElementById('sourceLanguage');
const chunkSecondsInput = document.getElementById('chunkSeconds');
const minAudioRmsInput = document.getElementById('minAudioRms');
const pythonPathInput = document.getElementById('pythonPath');

const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const theaterBtn = document.getElementById('theaterBtn');

const LS_KEY = 'laserdisc-subtitles-config-v1';
const LS_THEATER_KEY = 'laserdisc-subtitles-theater-mode-v1';
/* state function  */
function setStatus(stage) {
  const safe = (stage || 'idle').toLowerCase();
  const labels = {
    idle: 'idle',
    starting: 'starting',
    recording: 'recording',
    transcribing: 'transcribing',
    ready: 'ready',
    stopped: 'stopped'
  };

  statusBadge.textContent = labels[safe] || safe;
  statusBadge.className = `status-badge status-${safe}`;
}
/*display audio level */
function setAudioLevel(rms, threshold) {
  const safeThreshold = Math.max(1, Number(threshold) || 1);
  const percent = Math.max(0, Math.min(100, Math.round((Number(rms) / safeThreshold) * 100)));
  micLevelFill.style.width = `${percent}%`;
  micLevelText.textContent = `Mic RMS: ${Math.round(Number(rms) || 0)} / ${safeThreshold}`;
}
/* sets full screen mode "theater mode" */
function setTheaterMode(enabled) {
  document.body.classList.toggle('theater-mode', enabled);
  theaterBtn.textContent = enabled ? 'Exit Theater' : 'Theater Mode';
  localStorage.setItem(LS_THEATER_KEY, enabled ? '1' : '0');
}
/* appends a line to the log box aka console */

function appendLog(line) {
  const maxLines = 120;
  const current = logBox.textContent ? logBox.textContent.split('\n') : [];
  current.push(line);
  if (current.length > maxLines) {
    current.splice(0, current.length - maxLines);
  }
  logBox.textContent = current.join('\n');
  logBox.scrollTop = logBox.scrollHeight;
}
/* setter for the configuration */
function loadConfig() {
  const raw = localStorage.getItem(LS_KEY);
  if (!raw) {
    return;
  }
  try {
    const cfg = JSON.parse(raw);
    whisperBinInput.value = cfg.whisperBin || '';
    modelPathInput.value = cfg.modelPath || '';
    audioDeviceInput.value = cfg.audioDevice || ':0';
    sourceLanguageInput.value = cfg.sourceLanguage || 'ja';
    chunkSecondsInput.value = cfg.chunkSeconds || 4;
    minAudioRmsInput.value = cfg.minAudioRms || 250;
    pythonPathInput.value = cfg.pythonPath || 'python3';
  } catch (err) {
    appendLog(`Failed to load saved config: ${err}`);
  }
}
/* getter for the configuration */
function getConfig() {
  return {
    whisperBin: whisperBinInput.value.trim(),
    modelPath: modelPathInput.value.trim(),
    audioDevice: audioDeviceInput.value.trim() || ':0',
    sourceLanguage: sourceLanguageInput.value.trim() || 'ja',
    chunkSeconds: Number(chunkSecondsInput.value || '4'),
    minAudioRms: Number(minAudioRmsInput.value || '250'),
    pythonPath: pythonPathInput.value.trim() || 'python3'
  };
}
/* saves the configuration */
function saveConfig(cfg) {
  localStorage.setItem(LS_KEY, JSON.stringify(cfg));
}

startBtn.addEventListener('click', async () => {
  const cfg = getConfig();
  if (!cfg.whisperBin || !cfg.modelPath) {
    appendLog('Set Whisper Binary and Model Path first.');
    return;
  }
  saveConfig(cfg);
  setStatus('starting');
  appendLog('Starting subtitle engine...');
  await window.subtitleApp.start(cfg);
});

stopBtn.addEventListener('click', async () => {
  setStatus('stopped');
  appendLog('Stopping subtitle engine...');
  await window.subtitleApp.stop();
});

theaterBtn.addEventListener('click', () => {
  const enabled = !document.body.classList.contains('theater-mode');
  setTheaterMode(enabled);
});

window.subtitleApp.onSubtitle((text) => {
  subtitleText.textContent = text;
});

window.subtitleApp.onLog((line) => {
  appendLog(line);
});

window.subtitleApp.onStatus((stage) => {
  setStatus(stage);
});

window.subtitleApp.onAudioLevel((payload) => {
  setAudioLevel(payload.rms, payload.threshold);
});

loadConfig();
setTheaterMode(localStorage.getItem(LS_THEATER_KEY) === '1');
setStatus('idle');
setAudioLevel(0, Number(minAudioRmsInput.value || '250'));
appendLog('Ready. Configure paths and click Start.');
