const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');

let mainWindow = null;
let pyProc = null;
let currentSubtitle = '';

function listAudioDevices() {
  const platform = process.platform;

  if (platform === 'darwin') {
    const ffmpegCandidates = [
      process.env.FFMPEG_BIN,
      '/opt/homebrew/bin/ffmpeg',
      '/usr/local/bin/ffmpeg',
      'ffmpeg'
    ].filter(Boolean);

    let ffmpegBin = ffmpegCandidates[ffmpegCandidates.length - 1];
    for (const candidate of ffmpegCandidates) {
      try {
        const probe = spawnSync(candidate, ['-version'], { stdio: 'ignore' });
        if (!probe.error) {
          ffmpegBin = candidate;
          break;
        }
      } catch (_) {
        // Keep trying candidates.
      }
    }

    const probe = spawnSync(
      ffmpegBin,
      ['-hide_banner', '-f', 'avfoundation', '-list_devices', 'true', '-i', ''],
      { encoding: 'utf8' }
    );

    const stderr = String(probe.stderr || '');
    const lines = stderr.split('\n').map((line) => line.trim()).filter(Boolean);
    const audioInputs = [];

    let inAudioSection = false;
    for (const line of lines) {
      if (line.includes('AVFoundation audio devices')) {
        inAudioSection = true;
        continue;
      }
      if (line.includes('AVFoundation video devices')) {
        inAudioSection = false;
        continue;
      }

      if (!inAudioSection) {
        continue;
      }

      const match = line.match(/\[(\d+)\]\s+(.+)$/);
      if (match) {
        audioInputs.push({ index: match[1], name: match[2] });
      }
    }

    return {
      ok: true,
      platform,
      ffmpegBin,
      audioInputs,
      hint: 'Use AVFoundation audio selector format :<index> (example: :0, :1).'
    };
  }

  if (platform === 'linux') {
    const arecord = spawnSync('arecord', ['-l'], { encoding: 'utf8' });
    const output = String(arecord.stdout || arecord.stderr || '');
    const lines = output.split('\n').map((line) => line.trim()).filter(Boolean);
    return {
      ok: true,
      platform,
      raw: lines,
      hint: 'Use ALSA format like plughw:<card>,<device>.'
    };
  }

  return {
    ok: false,
    platform,
    error: `Audio device listing is not implemented for ${platform}`
  };
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 760,
    minWidth: 980,
    minHeight: 620,
    title: 'Laserdisc Live Subtitles',
    backgroundColor: '#070c1a',
    alwaysOnTop: true,
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'build', 'icons', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.loadFile('index.html');

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function stopPython() {
  if (pyProc) {
    pyProc.kill('SIGTERM');
    pyProc = null;
  }
}

function parseOutputLine(line) {
  const trimmed = line.trim();
  if (!trimmed) {
    return;
  }

  try {
    const evt = JSON.parse(trimmed);
    if (evt.type === 'subtitle' && typeof evt.text === 'string') {
      currentSubtitle = evt.text;
      mainWindow?.webContents.send('subtitle:update', currentSubtitle);
      return;
    }
    if (evt.type === 'status' && typeof evt.stage === 'string') {
      mainWindow?.webContents.send('subtitle:status', evt.stage);
      return;
    }
    if (evt.type === 'audio-level' && typeof evt.rms === 'number') {
      mainWindow?.webContents.send('subtitle:audioLevel', evt);
      return;
    }
  } catch (_) {
    // Non-JSON lines are treated as diagnostics.
  }

  mainWindow?.webContents.send('subtitle:log', trimmed);
}

function startPython(config) {
  stopPython();
  mainWindow?.webContents.send('subtitle:status', 'starting');

  const projectRoot = app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');
  const scriptPath = app.isPackaged
    ? path.join(process.resourcesPath, 'id_subtitle_deamon.py')
    : path.join(projectRoot, 'id_subtitle_deamon.py');

  if (!require('fs').existsSync(scriptPath)) {
    mainWindow?.webContents.send('subtitle:log', `Missing Python script at: ${scriptPath}`);
    return;
  }

  const args = [
    scriptPath,
    '--source-language', config.sourceLanguage,
    '--chunk-seconds', String(config.chunkSeconds),
    '--no-overlay',
    '--emit-json'
  ];

  // Determine a working python executable. Try configured path, env var, then common names.
  const candidates = Array.from(new Set([
    config.pythonPath,
    process.env.PYTHON,
    'python3',
    'python',
    'py'
  ].filter(Boolean)));

  let chosenPython = null;
  for (const cand of candidates) {
    try {
      const res = spawnSync(cand, ['--version'], { env: process.env, stdio: 'ignore' });
      if (!res.error) {
        chosenPython = cand;
        break;
      }
    } catch (_) {
      // ignore and try next
    }
  }

  if (!chosenPython) {
    mainWindow?.webContents.send('subtitle:log', `Python executable not found. Tried: ${candidates.join(', ')}`);
    mainWindow?.webContents.send('subtitle:status', 'stopped');
    return;
  }

  if (chosenPython !== (config.pythonPath || 'python3')) {
    mainWindow?.webContents.send('subtitle:log', `Using Python executable: ${chosenPython}`);
  }

  pyProc = spawn(chosenPython, args, {
    cwd: projectRoot,
    env: {
      ...process.env,
      WHISPER_BIN: config.whisperBin,
      MODEL_PATH: config.modelPath,
      AUDIO_DEVICE: config.audioDevice,
      MIN_AUDIO_RMS: String(config.minAudioRms || 250),
      RESEMBLY_SIM_THRESH: String(typeof config.resemblyThresh !== 'undefined' ? config.resemblyThresh : '0.72'),
      WHISPER_TIMEOUT: String(typeof config.whisperTimeout !== 'undefined' ? config.whisperTimeout : '30')
    },
    stdio: ['ignore', 'pipe', 'pipe']
  });

  pyProc.on('error', (err) => {
    mainWindow?.webContents.send('subtitle:log', `Failed to start Python (${err && err.code}): ${err && err.message}`);
    if (err && err.code === 'ENOENT') {
      mainWindow?.webContents.send('subtitle:log', 'Python executable missing; check the Python path in settings.');
    }
  });

  pyProc.stdout.setEncoding('utf8');
  pyProc.stderr.setEncoding('utf8');

  let stdoutBuffer = '';
  pyProc.stdout.on('data', (chunk) => {
    stdoutBuffer += chunk;
    const lines = stdoutBuffer.split('\n');
    stdoutBuffer = lines.pop() || '';
    lines.forEach(parseOutputLine);
  });

  pyProc.stderr.on('data', (chunk) => {
    const lines = chunk.split('\n').map((x) => x.trim()).filter(Boolean);
    lines.forEach((line) => mainWindow?.webContents.send('subtitle:log', line));
  });

  pyProc.on('close', (code) => {
    mainWindow?.webContents.send('subtitle:status', 'stopped');
    mainWindow?.webContents.send('subtitle:log', `Python process exited with code ${code}`);
    pyProc = null;
  });
}

ipcMain.handle('subtitle:start', async (_, config) => {
  startPython(config);
  return { ok: true };
});

ipcMain.handle('subtitle:stop', async () => {
  stopPython();
  return { ok: true };
});

ipcMain.handle('subtitle:save', async (_, text) => {
  if (!mainWindow) return { ok: false, error: 'no-window' };
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    title: 'Save subtitles',
    defaultPath: 'subtitles.txt',
    filters: [{ name: 'Text', extensions: ['txt'] }]
  });
  if (canceled || !filePath) return { ok: false, canceled: true };
  try {
    fs.writeFileSync(filePath, String(text || ''), 'utf8');
    return { ok: true, path: filePath };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
});

ipcMain.handle('subtitle:listAudioDevices', async () => {
  try {
    return listAudioDevices();
  } catch (err) {
    return { ok: false, error: String(err), platform: process.platform };
  }
});

app.whenReady().then(() => {
  createWindow();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', function () {
  stopPython();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
