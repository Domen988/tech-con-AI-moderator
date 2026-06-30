// ── State ───────────────────────────────────────────────────
let ws = null;
let listening = false;
let utterances = [];
let avatarPeerConnection = null;
let avatarSynthesizer = null;

// ── DOM refs ────────────────────────────────────────────────
const transcriptPanel = document.getElementById('transcriptPanel');
const transcriptEmpty = document.getElementById('transcriptEmpty');
const utteranceCount  = document.getElementById('utteranceCount');
const aiOutput        = document.getElementById('aiOutput');
const aiBadge         = document.getElementById('aiBadge');
const activityPanel   = document.getElementById('activityPanel');
const activityEmpty   = document.getElementById('activityEmpty');
const logCount        = document.getElementById('logCount');
const statusDot       = document.getElementById('statusDot');
const statusText      = document.getElementById('statusText');
const speechUsage     = document.getElementById('speechUsage');
const avatarVideo     = document.getElementById('avatarVideo');
const avatarAudio     = document.getElementById('avatarAudio');
const avatarScreen    = document.getElementById('avatarScreen');
const avatarPlaceholder = document.getElementById('avatarPlaceholder');
const avatarStatus    = document.getElementById('avatarStatus');
const btnStart        = document.getElementById('btnStart');
const btnStop         = document.getElementById('btnStop');
const personaAvatar   = document.getElementById('personaAvatar');
const personaName     = document.getElementById('personaName');
const personaSub      = document.getElementById('personaSub');

// ── WebSocket ───────────────────────────────────────────────
function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
        setStatus('connected', 'Connected');
        // keep-alive ping every 25s
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({cmd: 'ping'}));
            }
        }, 25000);
    };

    ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        handleMessage(msg);
    };

    ws.onclose = () => {
        setStatus('disconnected', 'Disconnected — reconnecting…');
        setTimeout(connect, 2000);
    };

    ws.onerror = () => {
        setStatus('disconnected', 'Connection error');
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'partial':
            showPartial(msg.text);
            break;
        case 'usage':
            updateSpeechUsage(msg.usage);
            break;
        case 'final':
            addUtterance(msg.text);
            break;
        case 'status':
            addLog('system', msg.text);
            break;
        case 'error':
            addLog('error', msg.text);
            break;
    }
}

// ── Transcript ──────────────────────────────────────────────
let partialEl = null;

function showPartial(text) {
    if (!partialEl) {
        partialEl = document.createElement('div');
        partialEl.className = 'transcript-line transcript-partial';
        transcriptPanel.appendChild(partialEl);
    }
    partialEl.textContent = '… ' + text;
    transcriptPanel.scrollTop = transcriptPanel.scrollHeight;
}

function addUtterance(text) {
    // Remove partial
    if (partialEl) {
        partialEl.remove();
        partialEl = null;
    }
    // Hide empty placeholder
    transcriptEmpty.style.display = 'none';

    utterances.push(text);

    const el = document.createElement('div');
    el.className = 'transcript-line';
    el.textContent = text;
    transcriptPanel.appendChild(el);
    transcriptPanel.scrollTop = transcriptPanel.scrollHeight;

    utteranceCount.textContent = `${utterances.length} utterance${utterances.length !== 1 ? 's' : ''}`;
}

// ── Activity Log ────────────────────────────────────────────
let logEntries = 0;

function addLog(kind, content) {
    activityEmpty.style.display = 'none';
    logEntries++;

    const el = document.createElement('div');
    el.className = 'activity-entry';
    const time = new Date().toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    el.innerHTML = `<span class="tag">${kind}</span> <span style="color:var(--text-dim)">${time}</span> ${escapeHtml(content.slice(0, 120))}`;
    activityPanel.prepend(el); // newest first
    logCount.textContent = `${logEntries} entries`;
}

function setAvatarSpeaking(isSpeaking) {
    if (!avatarScreen) return;
    if (isSpeaking) {
        avatarScreen.classList.add('speaking');
    } else {
        avatarScreen.classList.remove('speaking');
    }
}

function cleanupAvatarAudioUrl() {
    if (avatarAudio && avatarAudio._currentObjectUrl) {
        URL.revokeObjectURL(avatarAudio._currentObjectUrl);
        avatarAudio._currentObjectUrl = null;
    }
}

async function initAvatarConnection() {
    if (!window.SpeechSDK) {
        addLog('error', 'Azure Speech SDK not loaded in the browser.');
        setAvatarStatus('Avatar SDK not loaded', false);
        return;
    }

    setAvatarStatus('Requesting avatar relay token…');
    try {
        const resp = await fetch('/api/avatar-token');
        if (!resp.ok) {
            const body = await resp.text();
            throw new Error(body || resp.statusText);
        }

        const tokenData = await resp.json();
        // Helpful debug output: show the token payload (does not print secrets in server logs)
        console.log('Avatar token payload (client):', tokenData);
        const hasToken = Boolean(tokenData.authorizationToken || tokenData.iceServers?.length);
        if (!hasToken || !tokenData.region) {
            console.error('Avatar token payload', tokenData);
            throw new Error('Missing avatar relay token/ICE credentials or region');
        }

        setAvatarStatus('Avatar service ready', true);
        addLog('system', 'Avatar relay token acquired; browser can now initialize Azure avatar session.');

        // Store token information for later use if needed.
        window.avatarTokenData = tokenData;

        // Try initializing an avatar session if we have an auth token
        try {
                await initAvatarSession(tokenData);
        } catch (e) {
            addLog('error', 'Avatar session initialization error: ' + e.message);
            setAvatarStatus('Avatar init failed', false);
        }
    } catch (err) {
        addLog('error', 'Avatar initialization failed: ' + err.message);
        setAvatarStatus('Avatar unavailable', false);
    }
}

async function initAvatarSession(tokenData) {
    // tokenData: may contain authorizationToken OR iceServers
    const sdk = window.SpeechSDK;
    if (!sdk) {
        addLog('error', 'Speech SDK not loaded; cannot initialize avatar session');
        setAvatarStatus('SDK not loaded', false);
        return;
    }

    // If we only have ICE servers, we cannot complete signaling without an authorization token
    const hasAuth = Boolean(tokenData.authorizationToken);
    const hasIce = Boolean(tokenData.iceServers && tokenData.iceServers.length);

    if (!hasAuth) {
        if (hasIce) {
            setAvatarStatus('Only TURN provided — awaiting auth token', false);
            addLog('system', 'Received ICE servers but no authorization token — waiting for STS token');
        } else {
            setAvatarStatus('No avatar credentials', false);
            addLog('error', 'Avatar token payload missing credentials');
        }
        return;
    }

    setAvatarStatus('Initializing avatar session…');
    const token = tokenData.authorizationToken;
    const region = tokenData.region;

    try {
        const speechConfig = sdk.SpeechConfig.fromAuthorizationToken(token, region);

        // Build AvatarConfig using server-provided defaults or fallbacks
        const character = tokenData.avatar_character || tokenData.character || 'lisa';
        const style = tokenData.avatar_style || tokenData.style || 'casual-sitting';
        const avatarConfig = new sdk.AvatarConfig(character, style);

        // Create RTCPeerConnection with ICE servers provided by the backend
        const pcConfig = {};
        if (tokenData.iceServers && tokenData.iceServers.length) {
            pcConfig.iceServers = tokenData.iceServers;
        }
        const pc = new RTCPeerConnection(pcConfig);
        avatarPeerConnection = pc;

        pc.onconnectionstatechange = () => {
            addLog('debug', 'Avatar peer connection state: ' + pc.connectionState);
        };
        pc.oniceconnectionstatechange = () => {
            addLog('debug', 'Avatar ICE connection state: ' + pc.iceConnectionState);
        };
        pc.onicegatheringstatechange = () => {
            addLog('debug', 'Avatar ICE gathering state: ' + pc.iceGatheringState);
        };
        pc.onicecandidate = (evt) => {
            if (evt && evt.candidate) {
                addLog('debug', 'Avatar ICE candidate gathered: ' + evt.candidate.candidate.slice(0, 100));
            }
        };

        // Attach remote tracks to the video element
        pc.ontrack = (evt) => {
            try {
                const stream = (evt.streams && evt.streams[0]) || (evt.track && new MediaStream([evt.track]));
                if (!stream) throw new Error('No remote media stream available');
                avatarVideo.srcObject = stream;
                avatarVideo.muted = true;
                avatarVideo.play().catch(() => {});
                avatarVideo.classList.add('active');
                avatarPlaceholder.style.display = 'none';
                setAvatarStatus('Avatar connected', true);
                addLog('system', 'Avatar video stream attached (ontrack)');
            } catch (ex) {
                addLog('error', 'Failed to attach avatar track: ' + ex.message);
            }
        };

        // Create the AvatarSynthesizer with both speech and avatar configs
        const avatarSynth = new sdk.AvatarSynthesizer(speechConfig, avatarConfig);
        avatarSynthesizer = avatarSynth;

        setAvatarStatus('Starting avatar session…');

        const result = await avatarSynth.startAvatarAsync(pc);
        addLog('debug', 'Avatar session start result: ' + JSON.stringify(result && (result.errorDetails ? { errorDetails: result.errorDetails } : { reason: result.reason } )));

        if (result && result.errorDetails && typeof result.errorDetails === 'string') {
            const err = result.errorDetails;
            if (err.includes('Standard S0') || err.includes('S0 resource') || err.toLowerCase().includes('only available')) {
                const msg = 'Azure Avatar requires a Speech resource in the Standard S0 tier. Use an S0 key/region or create an S0 Speech resource in the Azure Portal.';
                addLog('error', msg + ' (server: ' + err + ')');
                setAvatarStatus('Avatar unavailable: S0 resource required', false);
                return;
            }
            throw new Error(err);
        }

        avatarVideo.muted = true;
        avatarVideo.addEventListener('playing', () => {
            setTimeout(() => { avatarVideo.muted = false; }, 300);
        }, { once: true });

        setAvatarStatus('Avatar ready', true);
        addLog('system', 'Avatar session initialized; waiting for remote video track.');
    } catch (e) {
        addLog('error', 'Avatar session setup failed: ' + e.message);
        setAvatarStatus('Avatar setup error', false);
    }
}


async function startAvatarSpeech(text) {
    if (!window.avatarTokenData || !window.SpeechSDK) {
        setAvatarStatus('Avatar not ready', false);
        return;
    }

    setAvatarStatus('Playing avatar speech…');
    await renderAvatarSpeech(text);
}

async function renderAvatarSpeech(text) {
    if (!avatarVideo || !avatarScreen || !window.avatarTokenData || !window.SpeechSDK) return;
    cleanupAvatarAudioUrl();
    setAvatarSpeaking(false);

    try {
        // If session is closed or does not exist, reinitialize it
        if (!avatarSynthesizer || !avatarPeerConnection || avatarPeerConnection.signalingState === 'closed') {
            await initAvatarSession(window.avatarTokenData);
        }

        if (!avatarSynthesizer) {
            throw new Error('Avatar session is not initialized');
        }

        const speakResult = await avatarSynthesizer.speakTextAsync(text);
        addLog('debug', 'Avatar speakTextAsync result: ' + JSON.stringify(speakResult && (speakResult.errorDetails ? { errorDetails: speakResult.errorDetails } : { reason: speakResult.reason })));

        if (speakResult && speakResult.errorDetails && typeof speakResult.errorDetails === 'string') {
            const err = speakResult.errorDetails;
            if (err.includes('Standard S0') || err.includes('S0 resource') || err.toLowerCase().includes('only available')) {
                const msg = 'Azure Avatar requires a Speech resource in the Standard S0 tier. Use an S0 key/region or create an S0 Speech resource in the Azure Portal.';
                addLog('error', msg + ' (server: ' + err + ')');
                setAvatarStatus('Avatar unavailable: S0 resource required', false);
                return;
            }
            throw new Error(err);
        }

        avatarVideo.muted = true;
        avatarVideo.addEventListener('playing', () => {
            setTimeout(() => { avatarVideo.muted = false; }, 300);
        }, { once: true });
    } catch (e) {
        setAvatarSpeaking(false);
        addLog('error', 'Avatar speech error: ' + e.message);
        setAvatarStatus('Avatar speech failed', false);
        console.error('Avatar speech error', e);
    }
}

// ── Controls ────────────────────────────────────────────────
function startListening() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({cmd: 'start_listening'}));
    listening = true;
    btnStart.disabled = true;
    btnStop.disabled = false;
    setStatus('live', 'Listening…');
    addLog('system', 'Listening started');
}

function stopListening() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({cmd: 'stop_listening'}));
    listening = false;
    btnStart.disabled = false;
    btnStop.disabled = true;
    setStatus('connected', 'Stopped');
    addLog('system', 'Listening stopped');
}

// ── Connection Test ─────────────────────────────────────────
function formatSeconds(seconds) {
    if (seconds == null || isNaN(seconds)) return '0s';
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
}

function updateSpeechUsage(usage) {
    if (!speechUsage) return;
    if (!usage) {
        speechUsage.textContent = 'Speech usage: 0s';
        return;
    }
    const consumed = formatSeconds(usage.consumed_seconds);
    if (usage.free_seconds && usage.remaining_seconds != null) {
        const remaining = formatSeconds(usage.remaining_seconds);
        speechUsage.textContent = `Speech usage: ${consumed} / ${remaining} left`;
    } else {
        speechUsage.textContent = `Speech usage: ${consumed}`;
    }
}

async function testConnection() {
    addLog('system', 'Testing Azure Speech connection…');
    aiOutput.className = 'ai-output empty';
    aiOutput.textContent = 'Testing connection to Azure Speech… (up to 10 seconds)';
    aiBadge.innerHTML = '';

    try {
        const resp = await fetch('/api/test-speech', {method: 'POST'});
        const data = await resp.json();

        if (data.ok) {
            aiOutput.className = 'ai-output';
            aiOutput.textContent = '✓ ' + (data.detail || 'Azure Speech connection works!');
            aiBadge.innerHTML = '<span class="badge-llm">OK</span>';
            addLog('system', 'Azure connection test PASSED');
        } else {
            aiOutput.className = 'ai-output';
            aiOutput.textContent = '✗ CONNECTION PROBLEM\n\n' + data.error;
            aiBadge.innerHTML = '<span class="badge-mock">FAIL</span>';
            addLog('error', 'Azure connection test FAILED: ' + data.error.slice(0, 80));
        }
    } catch (e) {
        aiOutput.textContent = 'Test request failed: ' + e.message;
        addLog('error', 'Connection test error: ' + e.message);
    }
}

// ── Persona Switching ───────────────────────────────────────
async function switchPersona(key) {
    try {
        const resp = await fetch(`/api/personas/${key}`, {method: 'POST'});
        if (!resp.ok) return;
        const data = await resp.json();

        // Update avatar and labels
        personaAvatar.textContent = data.emoji;
        personaName.textContent = data.name;
        personaSub.textContent = data.subtitle;

        // Update button active state
        document.querySelectorAll('.persona-btn').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById('pb-' + key);
        if (btn) btn.classList.add('active');

        addLog('persona', `Switched to ${data.name} (${data.subtitle})`);
    } catch (e) {
        addLog('error', 'Failed to switch persona: ' + e.message);
    }
}

async function doAction(action) {
    aiOutput.className = 'ai-output empty';
    aiOutput.textContent = 'Generating…';
    aiBadge.innerHTML = '';

    try {
        const resp = await fetch(`/api/${action}`, {method: 'POST'});
        if (!resp.ok) {
            const err = await resp.json();
            aiOutput.textContent = err.detail || 'Error';
            return;
        }
        const data = await resp.json();
        aiOutput.className = 'ai-output';
        aiOutput.textContent = data.content;

        const badgeClass = data.source === 'llm' ? 'badge-llm' : 'badge-mock';
        const badgeLabel = data.source === 'llm' ? 'LLM' : 'MOCK';
        aiBadge.innerHTML = `<span class="${badgeClass}">${badgeLabel}</span>`;

        addLog(action, data.content.slice(0, 80) + '…');
        startAvatarSpeech(data.content);
    } catch (e) {
        aiOutput.textContent = 'Request failed: ' + e.message;
    }
}

async function clearSession() {
    await fetch('/api/clear', {method: 'POST'});
    utterances = [];
    transcriptPanel.innerHTML = '';
    transcriptEmpty.style.display = '';
    transcriptPanel.appendChild(transcriptEmpty);
    utteranceCount.textContent = '0 utterances';
    aiOutput.className = 'ai-output empty';
    aiOutput.textContent = 'Press a button on the right to generate AI output.';
    aiBadge.innerHTML = '';
    activityPanel.innerHTML = '';
    activityEmpty.style.display = '';
    activityPanel.appendChild(activityEmpty);
    logEntries = 0;
    logCount.textContent = '0 entries';
    // Reset briefing UI
    document.getElementById('briefingStatus').textContent = 'No materials loaded';
    document.getElementById('briefingStatus').className = 'briefing-status';
    document.getElementById('btnSynopsis').style.display = 'none';
    document.getElementById('fileInput').value = '';
    addLog('system', 'Session cleared — ready for new talk');
}

// ── File Upload & Briefing ──────────────────────────────────
let currentSynopsis = '';

async function uploadFile(input) {
    const file = input.files[0];
    if (!file) return;

    const status = document.getElementById('briefingStatus');
    status.textContent = 'Uploading & processing…';
    status.className = 'briefing-status';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/upload', {method: 'POST', body: formData});
        if (!resp.ok) {
            const err = await resp.json();
            status.textContent = 'Error: ' + (err.detail || 'Upload failed');
            return;
        }
        const data = await resp.json();
        currentSynopsis = data.synopsis;

        status.textContent = `✓ ${data.filename} (${data.extracted_chars} chars)`;
        status.className = 'briefing-status loaded';
        document.getElementById('btnSynopsis').style.display = '';

        addLog('briefing', `Loaded ${data.filename} — synopsis ready`);
    } catch (e) {
        status.textContent = 'Upload failed: ' + e.message;
        addLog('error', 'File upload failed: ' + e.message);
    }
}

function viewSynopsis() {
    if (!currentSynopsis) return;
    aiOutput.className = 'ai-output';
    aiOutput.textContent = currentSynopsis;
    aiBadge.innerHTML = '<span class="badge-llm">BRIEFING</span>';
}

async function compressTranscript() {
    addLog('system', 'Compressing transcript…');
    try {
        const resp = await fetch('/api/compress', {method: 'POST'});
        const data = await resp.json();
        if (data.status === 'nothing_to_compress') {
            addLog('system', 'Not enough transcript to compress yet');
        } else if (data.status === 'ok') {
            addLog('compress', `Compressed up to utterance ${data.summarized_up_to}/${data.total}`);
        } else {
            addLog('error', data.detail || 'Compression failed');
        }
    } catch (e) {
        addLog('error', 'Compress failed: ' + e.message);
    }
}

// ── Helpers ──────────────────────────────────────────────────
function setStatus(state, text) {
    statusDot.className = 'status-dot' + (state === 'live' ? ' live' : '');
    statusText.textContent = text;
}

function setAvatarStatus(text, isReady = false) {
    if (!avatarStatus) return;
    avatarStatus.textContent = text;
    if (isReady) {
        avatarScreen.classList.add('active');
        avatarVideo.classList.add('active');
    } else {
        avatarScreen.classList.remove('active');
        avatarVideo.classList.remove('active');
    }
}

function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ── Boot ─────────────────────────────────────────────────────
connect();
initAvatarConnection();
updateSpeechUsage({consumed_seconds: 0, free_seconds: null, remaining_seconds: null});
