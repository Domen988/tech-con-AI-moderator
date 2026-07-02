# Handover Summary — AI Conference Moderator

Concept and building-block overview for whoever picks this up next. Not a
feature list (see `README.md` for that) — this is "what is this thing made
of, and why."

## What the demo does

A human operator runs a dashboard during a live conference talk. The app
listens to the speaker, transcribes them live, and on the operator's command
generates a **summary**, a **response**, or **candidate follow-up questions**.
The operator picks one output and can have it **spoken by a talking video
avatar** on stage. Nothing goes out live without the operator clicking a
button first — the AI never speaks unsupervised.

## The two builds — pick one to develop against

There are **two parallel implementations** of the same idea. This matters
a lot for a newcomer:

1. **`index.html`** (repo root) — a single self-contained HTML file, no
   server. **This is the one that actually works end-to-end**, including the
   video avatar. Everything (UI, speech recognition, LLM calls, avatar
   rendering) runs in the browser via vendored/inlined JS. All state
   (API keys, settings) lives in `localStorage`.
2. **`app/` (FastAPI backend) + `templates/` + `static/`** — the original
   server-based design. Still present and functional for transcript +
   text-based reasoning, but its avatar endpoint (`/api/avatar`) is a
   placeholder — it never got real video working, because (see below)
   Azure's avatar requires a browser, not a server, to render.

**Recommendation for your colleague: keep developing `index.html`.** It's
the one with working avatar support and is what's been demoed. The FastAPI
version is architecturally cleaner (real separation of concerns) but is
behind in features and shouldn't be assumed to be "the real one."

## Core concepts

### 1. Speech-to-text (Azure Speech SDK)
The browser's microphone is fed into Azure's `SpeechRecognizer`. It fires
two kinds of events: `recognizing` (a live, changing partial guess — shown
greyed out) and `recognized` (a finalized sentence — appended to the
transcript permanently). This is the raw material everything else consumes.

### 2. The Reasoner (two interchangeable backends)
"Reasoner" = whatever turns transcript text into AI output. There's a
common interface with two implementations, selectable at runtime:
- **Mock**: pure string/regex heuristics (keyword frequency, pick
  first/middle/last sentence). Zero dependencies, zero API keys, always
  works — useful for offline demos and as a fallback.
- **LLM**: calls any OpenAI-compatible chat-completions endpoint (OpenAI,
  Groq, OpenRouter, Azure OpenAI — just a base URL + model + API key).
  This is "prompt an LLM with the recent transcript, get text back" — no
  fine-tuning, no special model, just chat completion requests.

Three "operations" a reasoner supports: `summarize`, `suggest_questions`,
`draft_response`. The operator triggers these on demand; nothing runs
automatically.

### 3. Personas
Three fixed characters (HOST, PROBE/analyst, SPARK/audience-advocate), each
just a **system prompt + a chosen Azure voice**. Switching persona changes
which system prompt gets prepended to the LLM call and which voice speaks
the result. A shared "style rules" block (ban corporate buzzwords, no
generic filler, stay concrete) is appended to every persona so outputs
sound human rather than like typical LLM output. This is the main lever for
making the AI outputs feel distinct — not model choice, just prompting.

### 4. The video avatar — the trickiest part
This is **Azure Speech's real-time Talking Avatar**, and it is a **WebRTC**
feature, not a simple REST call. The flow:
1. Browser asks Azure for a short-lived **relay token** (ICE server
   credentials) over HTTPS.
2. Browser opens an `RTCPeerConnection` using those ICE servers, with
   `recvonly` audio+video transceivers (we only *receive* the avatar's
   stream, we don't send media to Azure over this connection).
3. `AvatarSynthesizer.startAvatarAsync(peer)` tells Azure to start
   streaming a synthesized talking-head video over that WebRTC connection.
4. The incoming `MediaStream` is bound to `<video>`/`<audio>` tags to play.
5. To make the avatar "say" something, you call the synthesizer with text
   (+ voice + style); Azure lip-syncs it server-side and streams the result.

**Why this had to move into the browser:** WebRTC peer connections must be
negotiated by the client that will render the media — a backend server
can't do this on the browser's behalf without essentially building a WebRTC
proxy. That's why the FastAPI backend's avatar support is a dead end and
`index.html` does it all client-side instead.

Background image behind the avatar (e.g. conference stage backdrop) is set
via an Azure avatar config parameter — must be a public HTTPS 1920×1080
image URL, applied when the avatar session starts.

### 5. Briefing context (RAG-lite, no vector DB)
The operator can paste or upload a `.txt`/`.md`/`.docx`/`.pptx` speaker
briefing. `.docx`/`.pptx` are just zip files of XML, so they're unzipped
client-side with JSZip and the text is extracted — no server, no document
AI. That extracted text is simply prepended as extra context in every LLM
prompt. There's no embedding/retrieval step; it's small enough to just
stuff into the prompt directly.

### 6. Transcript compression
Long talks produce long transcripts that would blow past LLM context limits
or get expensive. "Compress" takes everything except the most recent N
utterances and asks the reasoner to fold them into a short running summary,
which then replaces that older text as context for future calls. This is a
simple manual version of what production systems would call "context
window management."

### 7. Paste-transcript mode
Lets the operator feed in a pre-existing transcript (e.g. copied from
YouTube captions) as if it were spoken live, for rehearsing personas
against real talks without needing a live speaker. It's just text cleanup
(stripping timestamps/`[Music]` cues) feeding into the same pipeline as
live speech-to-text.

## Key files (in `index.html`, since that's where to develop)

- `PERSONAS` object + `STYLE_RULES` — persona definitions (~line 494).
- Avatar setup/connect logic — relay token → WebRTC → `startAvatarAsync`
  (~line 850+).
- `compressTranscript()` / `mockCompress()` / `llmCompress()` — context
  compression (~line 683+).
- Briefing file parsing via JSZip (~line 1068+).
- Settings are read from `localStorage`; there's a Settings panel in the UI
  for Azure key/region and reasoner (LLM provider) config — no keys are
  hardcoded in the file.

## What's NOT built yet (per README's "Extension Path")
Moderator approval queue (currently outputs display immediately, operator
manually decides what to send to avatar — there's no formal pending/approve
state), a projector-facing `/stage` view separate from the operator
dashboard, an audience Q&A submission queue, and multi-speaker diarization
(currently single-speaker transcription only).
