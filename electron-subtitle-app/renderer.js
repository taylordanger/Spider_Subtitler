/*This file is part of Electron Subtitle App, licensed under MIT License (MIT). */ 

const subtitleText = document.getElementById('subtitleText');
const subtitleHistory = document.getElementById('subtitleHistory');
const logBox = document.getElementById('logBox');
const statusBadge = document.getElementById('statusBadge');
const micLevelFill = document.getElementById('micLevelFill');
const micLevelText = document.getElementById('micLevelText');

const whisperBinInput = document.getElementById('whisperBin');
const modelPathInput = document.getElementById('modelPath');
const audioDeviceInput = document.getElementById('audioDevice');
const audioPresetInput = document.getElementById('audioPreset');
const listAudioBtn = document.getElementById('listAudioBtn');
const sourceLanguageInput = document.getElementById('sourceLanguage');
const chunkSecondsInput = document.getElementById('chunkSeconds');
const minAudioRmsInput = document.getElementById('minAudioRms');
const minAudioRmsValue = document.getElementById('minAudioRmsValue');
const enableSpeechFilterInput = document.getElementById('enableSpeechFilter');
const pythonPathInput = document.getElementById('pythonPath');
const resemblyThreshInput = document.getElementById('resemblyThresh');
const whisperTimeoutInput = document.getElementById('whisperTimeout');
const loadSrtBtn = document.getElementById('loadSrtBtn');
const forceLiveBtn = document.getElementById('forceLiveBtn');
const srtFileInput = document.getElementById('srtFileInput');
const srtThreshInput = document.getElementById('srtThresh');
const srtSyncStatus = document.getElementById('srtSyncStatus');
const openSubtitlesQueryInput = document.getElementById('openSubtitlesQuery');
const openSubtitlesApiKeyInput = document.getElementById('openSubtitlesApiKey');
const youtubeIdInput = document.getElementById('youtubeId');
const subtitleLangInput = document.getElementById('subtitleLang');

const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const theaterBtn = document.getElementById('theaterBtn');
const resetHistoryBtn = document.getElementById('resetHistoryBtn');
const saveSessionBtn = document.getElementById('saveSessionBtn');

const LS_KEY = 'laserdisc-subtitles-config-v2';
const LS_THEATER_KEY = 'laserdisc-subtitles-theater-mode-v1';

/* Slider sync for minAudioRms */
if (minAudioRmsInput) {
  minAudioRmsInput.addEventListener('input', (e) => {
    minAudioRmsValue.value = e.target.value;
  });
}
if (minAudioRmsValue) {
  minAudioRmsValue.addEventListener('change', (e) => {
    minAudioRmsInput.value = e.target.value;
  });
}
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
    const savedAudioDevice = String(cfg.audioDevice || '').trim();
    const normalizedAudioDevice = savedAudioDevice === ':0' ? 'auto' : (savedAudioDevice || 'auto');
    whisperBinInput.value = cfg.whisperBin || '';
    modelPathInput.value = cfg.modelPath || '';
    audioDeviceInput.value = normalizedAudioDevice;
    if (audioPresetInput) {
      audioPresetInput.value = normalizedAudioDevice;
      if (!Array.from(audioPresetInput.options).some((opt) => opt.value === audioPresetInput.value)) {
        audioPresetInput.value = 'custom';
      }
    }
    sourceLanguageInput.value = cfg.sourceLanguage || 'ja';
    chunkSecondsInput.value = cfg.chunkSeconds || 4;
    minAudioRmsInput.value = cfg.minAudioRms || 250;
    minAudioRmsValue.value = cfg.minAudioRms || 250;
    enableSpeechFilterInput.checked = cfg.enableSpeechFilter !== false;
    pythonPathInput.value = cfg.pythonPath || 'python3';
    resemblyThreshInput.value = cfg.resemblyThresh || 0.72;
    whisperTimeoutInput.value = cfg.whisperTimeout || 30;
    openSubtitlesQueryInput.value = cfg.openSubtitlesQuery || '';
    openSubtitlesApiKeyInput.value = cfg.openSubtitlesApiKey || '';
    youtubeIdInput.value = cfg.youtubeId || '';
    subtitleLangInput.value = cfg.subtitleLang || 'en';
  } catch (err) {
    appendLog(`Failed to load saved config: ${err}`);
  }
}
/* getter for the configuration */
function getConfig() {
  return {
    whisperBin: whisperBinInput.value.trim(),
    modelPath: modelPathInput.value.trim(),
    audioDevice: audioDeviceInput.value.trim() || 'auto',
    sourceLanguage: sourceLanguageInput.value.trim() || 'ja',
    chunkSeconds: Number(chunkSecondsInput.value || '4'),
    minAudioRms: Number(minAudioRmsInput.value || '250'),
    enableSpeechFilter: enableSpeechFilterInput.checked,
    pythonPath: pythonPathInput.value.trim() || 'python3',
    resemblyThresh: Number(resemblyThreshInput.value || '0.72'),
    whisperTimeout: Number(whisperTimeoutInput.value || '30'),
    openSubtitlesQuery: openSubtitlesQueryInput.value.trim(),
    openSubtitlesApiKey: openSubtitlesApiKeyInput.value.trim(),
    youtubeId: youtubeIdInput.value.trim(),
    subtitleLang: subtitleLangInput.value.trim() || 'en'
  };
}
/* saves the configuration */
function saveConfig(cfg) {
  localStorage.setItem(LS_KEY, JSON.stringify(cfg));
}

audioPresetInput?.addEventListener('change', () => {
  const preset = audioPresetInput.value;
  if (!preset || preset === 'custom') {
    return;
  }
  audioDeviceInput.value = preset;
  appendLog(`Audio preset applied: ${preset}`);
});

listAudioBtn?.addEventListener('click', async () => {
  appendLog('Scanning audio capture devices...');
  try {
    const result = await window.subtitleApp.listAudioDevices();
    if (!result || !result.ok) {
      appendLog(`Audio device scan failed: ${result && result.error ? result.error : 'unknown error'}`);
      return;
    }

    appendLog(`Platform: ${result.platform}`);
    if (result.hint) {
      appendLog(result.hint);
    }

    if (Array.isArray(result.audioInputs) && result.audioInputs.length) {
      appendLog('Available audio inputs:');
      result.audioInputs.forEach((input) => {
        appendLog(`  :${input.index}  ${input.name}`);
      });
      if (result.recommendedAudioDevice) {
        appendLog(`Recommended selector: ${result.recommendedAudioDevice}`);
      }
      appendLog('Set Audio Device to one of the :<index> values above.');
      return;
    }

    if (Array.isArray(result.raw) && result.raw.length) {
      appendLog('Raw device listing:');
      result.raw.forEach((line) => appendLog(`  ${line}`));
      return;
    }

    appendLog('No audio inputs found.');
  } catch (err) {
    appendLog(`Audio device scan error: ${err}`);
  }
});

startBtn.addEventListener('click', async () => {
  const cfg = getConfig();
  if (!cfg.whisperBin || !cfg.modelPath) {
    appendLog('Set Whisper Binary and Model Path first.');
    return;
  }
  srtSessionStartMs = Date.now();
  srtSyncOffsetSec = null;
  srtSyncConfidence = 0;
  srtForceLiveFallback = false;
  saveConfig(cfg);
  setStatus('starting');
  updateSrtSyncStatus();
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

// Helper to normalize text for speaker change detection
function normalizeTextForSpeaker(s) {
  return String(s || '').replace(/[\W_]+/g, ' ').trim().toLowerCase();
}

// Session state for speaker numbering, music detection, and saving
let sessionSubtitles = [];
let recentHighRmsEmptyCount = 0;
let musicAnnounced = false;
let srtEntries = [];
let srtThreshold = Number(srtThreshInput?.value || 0.7);
let srtSessionStartMs = 0;
let srtSyncOffsetSec = null;
let srtSyncConfidence = 0;
let srtForceLiveFallback = false;
// Adaptive RMS (EMA) for dynamic thresholding
let rmsEma = 0;
const RMS_EMA_ALPHA = 0.08;        // smoothing factor (lower = smoother)
const RMS_THRESHOLD_FACTOR = 0.6;  // threshold = EMA * factor
const RMS_MIN_CLAMP = 50;          // never go below this
const RMS_MAX_CLAMP = 5000;        // never go above this

function parseSrt(content) {
  const entries = [];
  const blocks = content.split(/\r?\n\r?\n+/);
  for (const block of blocks) {
    const lines = block.split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
    if (lines.length < 2) continue;
    // first line may be index
    let idx = 0;
    let timeLine = null;
    if (/^\d+$/.test(lines[0])) {
      idx = 1;
    }
    timeLine = lines[idx];
    const m = timeLine.match(/(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})/);
    let textLines = lines.slice(idx+1);
    if (!m) {
      // maybe no times; treat whole block as text
      textLines = lines.slice(idx);
    }
    const txt = textLines.join(' ').replace(/\s+/g,' ').trim();
    if (txt) {
      entries.push({
        start: m ? parseSrtTimestamp(m[1]) : 0,
        end: m ? parseSrtTimestamp(m[2]) : 0,
        text: txt
      });
    }
  }
  return entries;
}

function parseSrtTimestamp(value) {
  const match = String(value || '').trim().match(/(\d{2}):(\d{2}):(\d{2})(?:[,.](\d{1,3}))?/);
  if (!match) return 0;
  const hours = Number(match[1] || 0);
  const minutes = Number(match[2] || 0);
  const seconds = Number(match[3] || 0);
  const milliseconds = Number(String(match[4] || '0').padEnd(3, '0'));
  return hours * 3600 + minutes * 60 + seconds + (milliseconds / 1000);
}

function subtitleForTime(entries, elapsedSeconds) {
  if (!entries.length) return null;
  const target = Number(elapsedSeconds || 0);
  let current = null;
  for (const entry of entries) {
    if (entry.start <= target) {
      current = entry;
      continue;
    }
    break;
  }
  return current;
}

function updateSrtSyncStatus() {
  if (!srtSyncStatus) return;
  const pieces = [];
  if (!srtEntries.length) {
    pieces.push('SRT sync idle');
  } else if (srtForceLiveFallback) {
    pieces.push('SRT sync paused');
  } else {
    pieces.push(`SRT confidence ${Math.round(srtSyncConfidence * 100)}%`);
  }
  if (srtSyncOffsetSec != null && !srtForceLiveFallback) {
    pieces.push(`offset ${srtSyncOffsetSec >= 0 ? '+' : ''}${srtSyncOffsetSec.toFixed(2)}s`);
  }
  srtSyncStatus.textContent = pieces.join(' · ');
  if (forceLiveBtn) {
    forceLiveBtn.textContent = srtForceLiveFallback ? 'Resume SRT Sync' : 'Force Live Fallback';
  }
}

function setSrtForceLiveFallback(enabled) {
  srtForceLiveFallback = Boolean(enabled);
  updateSrtSyncStatus();
  appendLog(srtForceLiveFallback ? 'SRT sync paused; using live fallback text' : 'SRT sync resumed');
}
/* Compute Levenshtein distance between two strings */
function levenshtein(a, b) {
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const matrix = Array.from({length: a.length+1}, () => Array(b.length+1).fill(0));
  for (let i=0;i<=a.length;i++) matrix[i][0]=i;
  for (let j=0;j<=b.length;j++) matrix[0][j]=j;
  for (let i=1;i<=a.length;i++){
    for (let j=1;j<=b.length;j++){
      const cost = a[i-1]===b[j-1]?0:1;
      matrix[i][j]=Math.min(matrix[i-1][j]+1, matrix[i][j-1]+1, matrix[i-1][j-1]+cost);
    }
  }
  return matrix[a.length][b.length];
}
/* Compute similarity between two strings  */
function similarity(a, b) {
  const A = String(a||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const B = String(b||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  if (!A && !B) return 1;
  if (!A || !B) return 0;
  const dist = levenshtein(A, B);
  const maxLen = Math.max(A.length, B.length);
  return 1 - (dist / Math.max(1, maxLen));
}

resetHistoryBtn?.addEventListener('click', () => {
  if (subtitleHistory) subtitleHistory.innerHTML = '';
  sessionSubtitles = [];
  appendLog('Subtitle history cleared');
});

saveSessionBtn?.addEventListener('click', async () => {
  if (!sessionSubtitles.length) {
    appendLog('No subtitles to save');
    return;
  }
  try {
    const res = await window.subtitleApp.saveSession(sessionSubtitles.join('\n'));
    if (res && res.ok) appendLog(`Saved subtitles to ${res.path}`);
    else if (res && res.canceled) appendLog('Save canceled');
    else appendLog(`Save failed: ${res && res.error}`);
  } catch (err) {
    appendLog(`Save error: ${err}`);
  }
});

loadSrtBtn?.addEventListener('click', () => srtFileInput?.click());
forceLiveBtn?.addEventListener('click', () => {
  if (!srtEntries.length) {
    appendLog('Load an SRT file before using live fallback control');
    return;
  }
  setSrtForceLiveFallback(!srtForceLiveFallback);
});
srtFileInput?.addEventListener('change', (ev) => {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      srtEntries = parseSrt(String(reader.result || ''));
      srtSyncOffsetSec = null;
      srtSyncConfidence = 0;
      srtSessionStartMs = 0;
      srtForceLiveFallback = false;
      updateSrtSyncStatus();
      appendLog(`Loaded SRT entries: ${srtEntries.length}`);
    } catch (e) {
      appendLog(`Failed to parse SRT: ${e}`);
    }
  };
  reader.readAsText(f);
});

srtThreshInput?.addEventListener('change', () => {
  srtThreshold = Number(srtThreshInput.value || 0.7);
  appendLog(`SRT match threshold set to ${srtThreshold}`);
  updateSrtSyncStatus();
});

window.subtitleApp.onSubtitle((text) => {
  if (!srtSessionStartMs) {
    srtSessionStartMs = Date.now();
  }
  const elapsedSeconds = Math.max(0, (Date.now() - srtSessionStartMs) / 1000);

  // Display a cleaned version in the main subtitle area (remove timestamps)
  const cleanedRaw = stripTimestamps(String(text || ''));
  const cleanedNoYT = stripYouTubeSayings(cleanedRaw);
  // Remove any existing "Speaker N:" labels anywhere to avoid double-labeling
  const cleaned = String(cleanedNoYT).replace(/\bSpeaker\s*\d+\s*:\s*/gi, '');
  // If SRT loaded, use microphone transcription to estimate where we are in the file.
  let srtMatched = null;
  let syncLocked = false;
  if (srtEntries && srtEntries.length && !srtForceLiveFallback) {
    let best = {score: 0, entry: null};
    for (const e of srtEntries) {
      const s = similarity(cleaned, e.text);
      if (s > best.score) best = {score: s, entry: e};
    }
    if (best.entry && best.score >= srtThreshold) {
      const candidateOffset = best.entry.start - elapsedSeconds;
      srtSyncOffsetSec = srtSyncOffsetSec == null
        ? candidateOffset
        : (srtSyncOffsetSec * 0.8) + (candidateOffset * 0.2);
      srtSyncConfidence = Math.min(1, srtSyncConfidence + 0.25);

      const syncedTime = elapsedSeconds + srtSyncOffsetSec;
      const active = subtitleForTime(srtEntries, syncedTime);
      if (active) {
        srtMatched = String(active.text).replace(/\bSpeaker\s*\d+\s*:\s*/gi, '');
        srtMatched = stripYouTubeSayings(srtMatched);
        syncLocked = true;
      } else {
        srtMatched = String(best.entry.text).replace(/\bSpeaker\s*\d+\s*:\s*/gi, '');
        srtMatched = stripYouTubeSayings(srtMatched);
      }
      if (srtSyncConfidence >= 0.5) {
        appendLog(`SRT sync updated (offset ${srtSyncOffsetSec.toFixed(2)}s, score ${best.score.toFixed(2)})`);
      }
    }
    if (!syncLocked && srtSyncOffsetSec != null && srtSyncConfidence >= 0.35) {
      const syncedTime = elapsedSeconds + srtSyncOffsetSec;
      const active = subtitleForTime(srtEntries, syncedTime);
      if (active) {
        srtMatched = String(active.text).replace(/\bSpeaker\s*\d+\s*:\s*/gi, '');
        srtMatched = stripYouTubeSayings(srtMatched);
      }
    }
  }
  updateSrtSyncStatus();
  const norm = normalizeTextForSpeaker(cleaned);
  if (!norm) {
    // possible music/background; if already announced, keep showing it
    if (musicAnnounced) subtitleText.textContent = 'Music playing';
    else subtitleText.textContent = '';
    return;
  }
  // Display cleaned text without speaker numbering
  const displayText = srtMatched ? srtMatched : cleaned;
  subtitleText.textContent = displayText;
  try {
    appendSubtitleHistory(displayText);
    sessionSubtitles.push(displayText);
  } catch (err) {
    console.warn('Failed to append subtitle history', err);
  }
  // Reset music detection state when speech appears
  recentHighRmsEmptyCount = 0;
  musicAnnounced = false;
});

function appendSubtitleHistory(text) {
  if (!subtitleHistory) return;
  const MAX_LINES = 400;
  const atBottom = subtitleHistory.scrollHeight - subtitleHistory.clientHeight - subtitleHistory.scrollTop < 20;
  const entry = document.createElement('div');
  entry.className = 'subtitle-entry';
  // Ensure history also has timestamps stripped
  entry.textContent = stripTimestamps(String(text || ''));
  entry.textContent = stripYouTubeSayings(entry.textContent);
  // Ensure stored history also has any "Speaker N:" labels removed
  entry.textContent = entry.textContent.replace(/\bSpeaker\s*\d+\s*:\s*/gi, '');
  subtitleHistory.appendChild(entry);
  while (subtitleHistory.children.length > MAX_LINES) {
    subtitleHistory.removeChild(subtitleHistory.firstChild);
  }
  if (atBottom) {
    subtitleHistory.scrollTop = subtitleHistory.scrollHeight;
  }
}

function stripTimestamps(s) {
  if (!s) return s;
  let out = String(s);
  // Remove SRT/interval arrows and ranges like "00:00:01,000 --> 00:00:02,000"
  out = out.replace(/\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\s*-->\s*\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?/g, '');
  // Remove standalone time patterns e.g. 00:12:34.56 or 0:12:34 or 12:34
  out = out.replace(/\[?\(?\b\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\b\)?\]?/g, '');
  // Remove leftover bracketed timestamps like [00:12]
  out = out.replace(/[\[\]()]/g, '');
  // Collapse multiple spaces into one and trim
  out = out.replace(/\s{2,}/g, ' ').trim();
  return out;
}
function stripYouTubeSayings(s) {
  if (!s) return s;
  const outOrig = String(s);
  // Use an explicit list and safe regexp to robustly remove common phrases. Keep
  // the list easy to edit and avoid word-boundary issues with punctuation.
  const phrases = [
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
    ,
  ];
  const escapeRegExp = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(phrases.map(escapeRegExp).join('|'), 'gi');
  let out = outOrig.replace(pattern, '');
  // Collapse multiple spaces into one and trim
  out = out.replace(/\s{2,}/g, ' ').trim();
  return out;

}
window.subtitleApp.onLog((line) => {
  appendLog(line);
});

window.subtitleApp.onStatus((stage) => {
  setStatus(stage);
});

window.subtitleApp.onAudioLevel((payload) => {
  // Use adaptive EMA-based threshold instead of the raw payload threshold
  const rms = Number(payload.rms || 0);
  // initialize EMA on first sample
  rmsEma = rmsEma === 0 ? rms : (RMS_EMA_ALPHA * rms + (1 - RMS_EMA_ALPHA) * rmsEma);
  let adaptiveThreshold = Math.round(rmsEma * RMS_THRESHOLD_FACTOR);
  const userMin = Number(minAudioRmsInput.value || RMS_MIN_CLAMP);
  adaptiveThreshold = Math.max(userMin, Math.min(RMS_MAX_CLAMP, adaptiveThreshold));

  // Update UI with the adaptive threshold
  setAudioLevel(rms, adaptiveThreshold);

  // Simple music detection using adaptive threshold
  if (rms >= Math.max(1, adaptiveThreshold)) {
    if (!subtitleText.textContent || subtitleText.textContent.trim() === '') {
      recentHighRmsEmptyCount += 1;
    } else {
      recentHighRmsEmptyCount = 0;
    }
    if (recentHighRmsEmptyCount >= 2 && !musicAnnounced) {
      musicAnnounced = true;
      subtitleText.textContent = 'Music playing';
      appendSubtitleHistory('Music playing');
      sessionSubtitles.push('Music playing');
    }
  } else {
    recentHighRmsEmptyCount = 0;
  }
});

loadConfig();
setTheaterMode(localStorage.getItem(LS_THEATER_KEY) === '1');
setStatus('idle');
setAudioLevel(0, Number(minAudioRmsInput.value || '250'));
appendLog('Ready. Configure paths and click Start.');
