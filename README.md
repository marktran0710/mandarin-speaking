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
- Optional OpenAI Whisper, Gemini, local FunASR, or local VibeVoice-ASR transcription through the backend
- Praat/Parselmouth pitch and formant analysis
- Mandarin tone detection and tone-accuracy scoring
- Interactive pitch contour chart with Chart.js
- AI language feedback for fluency, grammar, and vocabulary
- Saved story history and teacher story activities in a backend SQLite database, with local storage fallback
- Docker backend option for machines without local Python

## Architecture

```text
React + Vite frontend
  -> records speech and converts audio to WAV
  -> calls FastAPI backend

FastAPI backend
  -> /api/analyze: Praat acoustic analysis + optional local ASR + AI language feedback
  -> /api/transcribe: OpenAI, Gemini, FunASR, or VibeVoice-ASR transcription
  -> /api/audio-records and /api/custom-stories: SQLite persistence
  -> /uploads/audio and /uploads/images: saved voice and story image files
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
AI_FEEDBACK_PROVIDER=gemini
OPENAI_FEEDBACK_MODEL=gpt-4o-mini
GEMINI_FEEDBACK_MODEL=gemini-2.0-flash
FUNASR_MODEL=paraformer-zh
FUNASR_VAD_MODEL=fsmn-vad
FUNASR_PUNC_MODEL=ct-punc
VIBEVOICE_ASR_MODEL=microsoft/VibeVoice-ASR-HF
VIBEVOICE_DEVICE=-1
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DATABASE_PATH=./mandarin_stories.db
UPLOAD_DIR=./uploads
```

Notes:

- API keys stay on the backend and are not exposed to the browser.
- In production, set `CORS_ORIGINS` to the deployed frontend URL.
- In production, the frontend must set `VITE_BACKEND_URL` to the deployed backend URL. GitHub Pages cannot run Praat by itself.
- The backend creates a SQLite database at `DATABASE_PATH` and stores voice/image files under `UPLOAD_DIR`. Point both at a persistent disk or volume in production.
- AI coach feedback prefers Gemini 2.0 Flash by default when `GEMINI_API_KEY` is configured. Set `AI_FEEDBACK_PROVIDER=openai` only if you want OpenAI to be tried first.
- If no OpenAI or Gemini key is configured, AI coach feedback falls back to local heuristic feedback.
- Web Speech API transcription does not require an API key, but browser support varies.
- FunASR transcription runs on the backend and does not require an API key. The first run may download model files, so the backend needs network access and enough disk/memory for the ASR models.
- VibeVoice-ASR transcription runs on the backend through Hugging Face Transformers and does not require an API key. Use `VIBEVOICE_DEVICE=-1` for CPU or a GPU device index such as `0` when the backend has CUDA available.

## Deployment

This project deploys as two services:

- Frontend: Vite static site on Vercel, Netlify, or another static host
- Backend: FastAPI Docker service on Render, Railway, Fly.io, or Cloud Run

### Backend on Render

The repository includes `render.yaml` and `backend/Dockerfile`.

1. Push the repository to GitHub.
2. In Render, create a new Blueprint from the repository.
3. After the backend URL is created, update the backend environment variable:

```env
CORS_ORIGINS=https://marktran0710.github.io
```

4. Add optional AI keys if needed:

```env
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key
AI_FEEDBACK_PROVIDER=gemini
```

5. Verify:

```powershell
curl https://your-backend-domain.onrender.com/health
```

### Frontend on Vercel

The repository includes `vercel.json`.

Set this Vercel environment variable before production deploy:

```env
VITE_BACKEND_URL=https://your-backend-domain.onrender.com
```

Then deploy:

```powershell
npm.cmd run build
npx vercel --prod
```

After Vercel gives you the frontend URL, add that exact URL to the backend `CORS_ORIGINS` value and redeploy/restart the backend.

### Frontend on GitHub Pages

The repository also includes `.github/workflows/deploy-pages.yml` for a no-CLI deployment path.

1. Push the repository to GitHub.
2. In GitHub, open **Settings -> Pages**.
3. Set **Source** to **GitHub Actions**.
4. Push to `main` or manually run the **Deploy Frontend to GitHub Pages** workflow.

Expected frontend URL:

```text
https://marktran0710.github.io/mandarin-speaking/
```

If you deploy the backend later, add a repository variable in GitHub:

```env
VITE_BACKEND_URL=https://your-backend-domain.example.com
```

Then rerun the Pages workflow. Without `VITE_BACKEND_URL`, the static UI deploys, but Praat/Gemini analysis cannot run because the browser has no production backend to call.

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

Analyzes a WAV audio upload with Praat and returns language feedback. If `transcription` is empty and `asr_model` is provided, the backend transcribes first and then runs Praat on the same uploaded audio.

Form fields:

- `file`: audio file
- `transcription`: optional transcription text
- `asr_model`: optional ASR provider for combined transcription + Praat analysis, for example `vibevoice`

### `POST /api/transcribe`

Transcribes an audio upload with OpenAI, Gemini, local FunASR, or local VibeVoice-ASR.

Form fields:

- `file`: audio file
- `model`: `openai`, `gemini`, `funasr`, or `vibevoice`

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
│   ├── database.py
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
- In production, verify `VITE_BACKEND_URL` points to a live HTTPS backend.
- Verify the backend `CORS_ORIGINS` includes the frontend origin, for example `https://marktran0710.github.io`.
- If using local Python, install dependencies with `pip install -r backend/requirements.txt`.
- If using Docker, rebuild the backend image after dependency changes.

## License

MIT
