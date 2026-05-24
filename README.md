# Mandarin Stories

Mandarin Stories is a React + FastAPI learning app for practicing spoken Mandarin with story prompts. Learners choose a topic image, record speech, review transcription, and get two layers of feedback:

- Praat acoustic analysis for pitch, tone, formants, speech rate, and fluency
- AI language-coach feedback for fluency, grammar, vocabulary, improved wording, and next practice prompts

The current UI uses a warm Clay-inspired design system with cream surfaces, black CTAs, rounded panels, and saturated learning cards.

## Features

- Multi-page app: Home, Create Story, and My Stories
- Topic-based story prompts with vocabulary support
- Browser audio recording with WAV conversion before backend analysis
- Web Speech API transcription for a free browser-native flow
- Optional OpenAI Whisper or Gemini transcription through the backend
- Praat/Parselmouth pitch and formant analysis
- Mandarin tone detection and tone-accuracy scoring
- Interactive pitch contour chart with Chart.js
- AI language feedback for fluency, grammar, and vocabulary
- Saved story history in local storage
- Docker backend option for machines without local Python

## Architecture

```text
React + Vite frontend
  -> records speech and converts audio to WAV
  -> calls FastAPI backend

FastAPI backend
  -> /api/analyze: Praat acoustic analysis + AI language feedback
  -> /api/transcribe: OpenAI or Gemini transcription
  -> /api/reference-tone/{tone}: Mandarin tone reference data
```

## Quick Start

### Option A: Run Backend With Docker

This is the easiest path on Windows if Python is not installed locally.

```powershell
docker build -t mandarin-speaking-backend ./backend
docker rm -f mandarin-speaking-backend-api
docker run -d --name mandarin-speaking-backend-api -p 8000:8000 mandarin-speaking-backend
```

Verify:

```powershell
curl http://localhost:8000/health
```

### Option B: Run Backend With Local Python

Requires Python 3.10+.

```powershell
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Run Frontend

```powershell
npm install
npm.cmd run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

Open:

- Frontend: http://127.0.0.1:5173
- Backend health: http://localhost:8000/health
- Backend API docs: http://localhost:8000/docs

## Environment Variables

Create `backend/.env` if you want cloud transcription or AI-generated coaching:

```env
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key
OPENAI_FEEDBACK_MODEL=gpt-4o-mini
GEMINI_FEEDBACK_MODEL=gemini-2.0-flash
```

Notes:

- API keys stay on the backend and are not exposed to the browser.
- If no OpenAI or Gemini key is configured, AI coach feedback falls back to local heuristic feedback.
- Web Speech API transcription does not require an API key, but browser support varies.

## User Flow

1. Open the app and go to Create Story.
2. Pick a topic and image prompt.
3. Choose a speech source.
4. Record Mandarin speech.
5. Stop recording and wait for analysis.
6. Review Praat metrics, pitch chart, AI feedback, and transcription.
7. Visit My Stories to review saved attempts.

## Praat Metrics

| Metric | Meaning |
| --- | --- |
| Detected tone | Best matching Mandarin tone from the pitch contour |
| Tone accuracy | Similarity between the learner pitch contour and tone reference |
| Pitch contour | Frequency over time extracted by Praat/Parselmouth |
| Speech rate | Estimated syllables per second |
| Fluency score | Smoothness and continuity estimate from pitch and timing |
| Formants | F1, F2, and F3 vowel characteristics |

Tone references:

- Tone 1: high level, ma1
- Tone 2: rising, ma2
- Tone 3: falling-rising, ma3
- Tone 4: falling, ma4

## AI Language Feedback

The backend adds an `ai_feedback` object to `/api/analyze` responses:

```json
{
  "provider": "openai",
  "fluency": {
    "score": 82,
    "feedback": "Your sentence is understandable and mostly smooth."
  },
  "grammar": {
    "score": 76,
    "feedback": "The sentence needs a clearer subject-action structure.",
    "corrections": ["Add a subject before the verb."]
  },
  "vocabulary": {
    "score": 80,
    "feedback": "Use one more specific descriptive word.",
    "suggestions": ["Add a place word", "Add an emotion word"]
  },
  "improved_version": "A more natural Mandarin version",
  "practice_prompt": "Say the sentence again with one extra detail."
}
```

If API keys are missing or the AI request fails, the backend returns `"provider": "local"` with fallback coaching.

## API Endpoints

### `GET /health`

Returns backend status.

### `POST /api/analyze`

Analyzes a WAV audio upload with Praat and returns language feedback.

Form fields:

- `file`: audio file
- `transcription`: optional transcription text

### `POST /api/transcribe`

Transcribes an audio upload with OpenAI or Gemini.

Form fields:

- `file`: audio file
- `model`: `openai` or `gemini`

### `GET /api/reference-tone/{tone_number}`

Returns one tone reference pattern.

### `GET /api/all-tones`

Returns all tone reference patterns.

## Project Structure

```text
.
├── backend/
│   ├── Dockerfile
│   ├── ai_feedback.py
│   ├── chinese_tones.py
│   ├── main.py
│   ├── praat_analyzer.py
│   └── requirements.txt
├── clay/
│   └── DESIGN.md
├── src/
│   ├── components/
│   │   ├── Navigation.tsx
│   │   └── StoryRecorder.tsx
│   ├── pages/
│   │   ├── HomePage.tsx
│   │   ├── CreateStoryPage.tsx
│   │   └── MyStoriesPage.tsx
│   ├── App.tsx
│   ├── PitchChart.tsx
│   ├── TopicSelector.tsx
│   └── main.tsx
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Development Commands

```powershell
npm.cmd run dev
npm.cmd run build
npm.cmd run preview
```

Backend Docker:

```powershell
docker build -t mandarin-speaking-backend ./backend
docker run -d --name mandarin-speaking-backend-api -p 8000:8000 mandarin-speaking-backend
docker logs mandarin-speaking-backend-api
docker rm -f mandarin-speaking-backend-api
```

## Troubleshooting

### Browser shows `ERR_CONNECTION_REFUSED` for frontend

Start Vite and verify the port:

```powershell
npm.cmd run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

Open http://127.0.0.1:5173.

### Browser shows `ERR_CONNECTION_REFUSED` for backend

Start the backend and verify:

```powershell
curl http://localhost:8000/health
```

### Opening `/api/analyze` directly shows an error

That endpoint is a `POST` file-upload endpoint. Use the frontend recording flow or Swagger UI at http://localhost:8000/docs.

### AI feedback says `provider: local`

No supported AI key is configured, or the provider request failed. Add `OPENAI_API_KEY` or `GEMINI_API_KEY` to `backend/.env` and restart the backend.

### Praat analysis fails

- Make sure the uploaded audio is not empty.
- Prefer WAV audio.
- If using local Python, install dependencies with `pip install -r backend/requirements.txt`.
- If using Docker, rebuild the backend image after dependency changes.

## License

MIT
