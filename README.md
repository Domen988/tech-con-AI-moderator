# AI Conference Moderator — Proof of Concept

A real-time AI moderator assistant for technology conferences. A human operator controls an AI assistant that listens to speech, transcribes it via Azure Speech-to-Text, and generates summaries, follow-up questions, and moderator responses on demand.

---

## ⚡ Standalone single-file build — `index.html` (no backend)

`index.html` at the repo root is a **self-contained, static rebuild** of this app that combines the operator dashboard with a **working Azure real-time video avatar** in one file — no Python, no FastAPI, no WebSocket server.

**Why this exists:** the original FastAPI build never rendered the avatar because Azure's talking avatar is a **WebRTC** stream that must be negotiated in the *browser*, while the backend only had an `/api/avatar` placeholder. The standalone build uses the proven browser WebRTC path (relay token → `RTCPeerConnection` with `recvonly` video+audio transceivers → `AvatarSynthesizer.startAvatarAsync` → shared `MediaStream` bound to `<video>` + `<audio>`). The Azure Speech JS SDK also does Speech-to-Text in the browser, so the server is no longer needed.

**What it includes**
- **Live transcript** — browser `SpeechRecognizer` (continuous recognition, partial + final).
- **Reasoner** — `Mock` (offline keyword/extractive logic) **and** an `LLM` toggle calling any OpenAI-compatible endpoint (Groq / OpenAI / OpenRouter / Azure OpenAI — base URL + model + key configurable).
- **Conference moderator personas** — 🎤 **HOST** (polished MC / facilitator — keynotes & flow), 🔬 **PROBE** (analyst — technical depth & trade-offs), 💡 **SPARK** (audience advocate — accessibility & energy). Each maps to a voice + voice-style + system prompt and is tuned to *facilitate* the speaker rather than upstage them.
- **Questions → pick one** — the **❓ Questions** action proposes three candidate questions as selectable cards; the operator clicks **🎤 Ask** on exactly one, and the avatar poses that question to the speaker.
- **Avatar stage** — character/style/voice/style-degree/rate controls, fullscreen toggle, speaking glow, and a **⧉ Pop out** button that opens the avatar in a separate window you can drag to a second screen and enlarge (audio stays on the main window).
- **Avatar background** — set a solid colour, or a **public HTTPS image URL at 1920×1080** that Azure composites behind the avatar server-side (so the image must be web-hosted, not a local file). Applied on Start Avatar.
- **Speaker briefing** — paste or load a `.pptx`, `.docx`, `.txt` or `.md` file as reasoner context. `.pptx`/`.docx` are unzipped and parsed in the browser via JSZip (no server, no upload).
- **Transcript compression** — for long talks, **🗜 Compress** rolls older utterances into a running summary (mock-extractive or LLM), shown as a banner and fed back to the reasoner as context.
- **Settings panel** — Azure key/region/language + reasoner config, saved to `localStorage` (no keys baked into the file).
- **Hisense-branded** dark broadcast-operator UI (Hisense green accents).

**Run it**
1. Open ⚙ **Settings**, paste your **Azure Speech key** (must be **Standard S0** tier — required for the avatar) and region.
2. Click **▶ Start Avatar**, then **▶ Start Listening**.
3. Generate **Summarize / Response** (review, then **🗣 Send to Avatar**), or **Questions** and click **🎤 Ask** on the one you want the avatar to pose.

> **Microphone note:** browsers only grant mic access in a *secure context*. Serve the file over `localhost` (e.g. `python -m http.server`) or `https` — opening via `file://` may block the microphone (the avatar/TTS still works either way).

> **Self-contained / shareable:** the Azure Speech SDK and JSZip are **inlined** into `index.html` (base64), so it loads with **no CDN** — it works on a first-time, empty-cache open even behind a corporate firewall, with browser tracking-prevention on, or with an ad-blocker. Just send the single file. *Runtime* features (avatar, speech-to-text) still call Azure's servers, so the machine needs internet access to Azure when those are used.

The original FastAPI backend below remains intact and unchanged.

---

## Architecture

```
┌─────────────┐      WebSocket       ┌──────────────────────────┐
│  Browser UI  │◄────────────────────►│  FastAPI Backend         │
│  (operator   │                      │                          │
│   dashboard) │◄── REST /api/* ─────►│  ┌────────────────────┐  │
└─────────────┘                      │  │ TranscriptionService│  │
                                     │  │ (Azure Speech SDK)  │  │
                                     │  └────────┬───────────┘  │
                                     │           │              │
                                     │  ┌────────▼───────────┐  │
                                     │  │  SessionManager     │  │
                                     │  │  (in-memory state)  │  │
                                     │  └────────┬───────────┘  │
                                     │           │              │
                                     │  ┌────────▼───────────┐  │
                                     │  │  Reasoner           │  │
                                     │  │  (Mock or LLM)      │  │
                                     │  └────────────────────┘  │
                                     └──────────────────────────┘
```

**Data flow:**
1. Microphone → Azure Speech SDK (runs on the server machine)
2. Azure SDK fires `recognizing` (partial) and `recognized` (final) callbacks
3. Callbacks push events into an asyncio queue
4. WebSocket handler drains the queue and broadcasts to all connected browsers
5. Operator clicks a button → REST call → Reasoner processes recent transcript → response displayed

**Reasoner modes:**
- `MockReasoner` (default): keyword extraction, extractive summaries, template questions. Works with zero additional API keys.
- `LLMReasoner` (optional): OpenAI or Azure OpenAI chat completions. Activate by setting the corresponding API key in `.env`.

## File Structure

```
ai-moderator/
├── run.py                    # Entry point
├── requirements.txt
├── .env.example
├── .env                      # Your actual config (git-ignored)
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app factory
│   ├── config.py             # Settings from env vars
│   ├── logging_setup.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── api.py            # REST endpoints (summarize, questions, etc.)
│   │   └── ws.py             # WebSocket for real-time transcript
│   └── services/
│       ├── __init__.py
│       ├── session.py         # In-memory transcript + activity log
│       ├── transcription.py   # Azure Speech SDK wrapper
│       ├── reasoner.py        # BaseReasoner + MockReasoner
│       └── llm_reasoner.py    # Optional LLM-backed reasoner
├── static/
│   ├── css/style.css
│   └── js/app.js
└── templates/
    └── index.html
```

## Setup & Run

### 1. Prerequisites
- Python 3.11+
- A working microphone on the machine running the server
- Azure Speech-to-Text key and region

### 2. Create virtual environment
```bash
cd ai-moderator
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env and set your AZURE_SPEECH_KEY and AZURE_SPEECH_REGION
```

### 5. Run
```bash
python run.py
```

### 6. Open browser
Navigate to **http://localhost:8000**

Click **Start Listening**, speak into your microphone, and watch the transcript appear. Use the buttons on the right panel to generate AI outputs.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AZURE_SPEECH_KEY` | Yes | Azure Cognitive Services Speech API key |
| `AZURE_SPEECH_REGION` | Yes | Azure region (e.g. `westeurope`) |
| `OPENAI_API_KEY` | No | Enables LLMReasoner via OpenAI or OpenRouter (OpenAI-compatible) |
| `OPENAI_API_BASE_URL` | No | Optional custom OpenAI-compatible API base URL |
| `GROQ_API_KEY` | No | Enables native Groq support |
| `GROQ_API_BASE_URL` | No | Optional Groq API base URL for `gsk_` keys or OpenAI-compatible fallback |
| `GROQ_MODEL` | No | Groq model name (default: `llama-3.3-70b-versatile`) |
| `AVATAR_API_URL` | No | Optional full video avatar generation endpoint |
| `AVATAR_API_KEY` | No | Optional avatar service API key |
| `AVATAR_MODEL` | No | Optional avatar model name for video generation |
| `AVATAR_CHARACTER` | No | Optional Azure avatar character name (e.g. `lisa`) |
| `AVATAR_STYLE` | No | Optional Azure avatar style (e.g. `casual-sitting`) |
| `AZURE_OPENAI_API_KEY` | No | Enables LLMReasoner via Azure OpenAI |
| `AZURE_OPENAI_ENDPOINT` | No | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | No | Azure OpenAI deployment name |
| `AZURE_SPEECH_FREE_MINUTES` | No | Optional free-tier speech minutes for UI remaining usage display |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |
| `HOST` | No | Bind address (default: `0.0.0.0`) |
| `PORT` | No | Port (default: `8000`) |

## Extension Path

This PoC is designed for straightforward extension:

**Text-to-Speech:** Add a `TTSService` in `app/services/tts.py` using Azure Speech SDK's `SpeechSynthesizer`. Wire it to a new `/api/speak` endpoint. The frontend can trigger playback when the operator approves an AI response.

**Full video avatar:** A full talking-head avatar requires an external avatar provider. Configure `AVATAR_API_URL`, `AVATAR_API_KEY`, and `AVATAR_MODEL`, then implement `app/services/avatar.py` to call that service. The app already includes the `/api/avatar` endpoint and a browser avatar screen placeholder for video playback.

**Avatar rendering:** Replace the emoji placeholder in the persona panel with a `<canvas>` or `<video>` element. Azure provides a Talking Avatar API, or you can use a lightweight lip-sync library driven by the TTS audio stream.

**Full-screen stage output:** Add a second route (`/stage`) that serves a stripped-down, read-only view showing only the AI persona and approved outputs. Project this on the conference screen while the operator uses the dashboard on their laptop.

**Audience Q&A:** Add a `/audience` route with a simple form. Submitted questions go into a queue. The operator dashboard shows the queue and can select questions to feed into the Reasoner for AI-assisted answers.

**Moderator approval flow:** Instead of displaying AI output immediately, queue it in a "pending" state. The operator reviews and clicks "Approve" to push it to the stage display. Add WebSocket message types for `pending` and `approved`.

**Multi-speaker diarization:** Azure Speech SDK supports speaker diarization via `ConversationTranscriber`. Swap `SpeechRecognizer` for `ConversationTranscriber` in `transcription.py` and tag each utterance with a speaker ID.

**Cloud deployment:** Containerize with a `Dockerfile`. The microphone input would need to change from local device to a streaming audio source (e.g., a stage audio feed piped via WebSocket or RTMP). Deploy on Azure Container Apps or a VM with audio input hardware.
