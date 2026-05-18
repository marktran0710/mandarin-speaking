# Praat Speech Analysis Backend - Setup & Usage Guide

## Overview

This guide explains how to set up and run the Python backend for Mandarin Chinese speech analysis using Praat.

## Architecture

```
Frontend (React) ← → Backend (Python FastAPI) ← → Praat Analysis
                                              ← → OpenAI Whisper
                                              ← → Google Gemini
```

**Key Changes:**

- ✅ API keys moved from frontend to backend (secure)
- ✅ Speech transcription handled by backend
- ✅ Praat acoustic analysis runs on backend
- ✅ Frontend displays Praat metrics + pitch contour charts

---

## Prerequisites

### System Requirements

1. **Python 3.10 or higher**

   ```bash
   python --version
   ```

2. **Praat 6.0 or higher**
   - Download: https://www.fon.hum.uva.nl/praat/
   - Installation:
     - **Windows:** Download installer, run it, add Praat to PATH
     - **Mac:** Download DMG or use Homebrew: `brew install praat`
     - **Linux:** Install via package manager or download binary
   - **Verify Praat installation:**
     ```bash
     praat --version
     ```

---

## Backend Setup

### Step 1: Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

**What gets installed:**

- FastAPI - web framework
- uvicorn - ASGI server
- parselmouth - Praat Python bindings
- numpy, scipy - audio processing
- httpx - async HTTP client for API calls

### Step 2: Configure Environment Variables

Create `backend/.env` with your API keys:

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`:

```
OPENAI_API_KEY=sk-your-openai-key-here
GEMINI_API_KEY=your-gemini-key-here
```

**How to get API keys:**

- **OpenAI:** https://platform.openai.com/api-keys
- **Gemini:** https://aistudio.google.com/apikey

### Step 3: Start Backend Server

```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Expected output:**

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

**Verify backend is running:**

- Navigate to http://localhost:8000/health
- Should see: `{"status": "ok", "service": "Speaking App Backend"}`

**API Documentation:**

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Frontend Setup

### Step 1: Install Dependencies

```bash
npm install
```

This will install Chart.js and other dependencies.

### Step 2: Configure Frontend Environment

The `.env.local` already points to backend:

```
VITE_BACKEND_URL=http://localhost:8000
```

Change this if your backend is on a different host/port.

### Step 3: Start Frontend Dev Server

```bash
npm run dev
```

**Expected output:**

```
  VITE v5.0.0  ready in 123 ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

---

## Running the Full Application

### Terminal 1: Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### Terminal 2: Frontend

```bash
npm run dev
```

### Terminal 3 (Optional): Monitor

```bash
# Watch for Python file changes in backend
```

**Now:**

1. Open http://localhost:5173 in your browser
2. Select a topic
3. Record Mandarin speech
4. Wait for analysis (1-3 seconds)
5. See Praat metrics + pitch chart + feedback

---

## API Endpoints

### Speech Analysis

**POST** `/api/analyze`

- Input: audio file (WAV/WebM)
- Output: JSON with all metrics
- Example response:

```json
{
  "pitch_contour": [[0.0, 150.5], [0.01, 155.2], ...],
  "detected_tone": 2,
  "tone_accuracy": 85.5,
  "formants": {"F1": 720, "F2": 1220, "F3": 2600},
  "speech_rate": 5.2,
  "fluency_score": 78.3,
  "pitch_statistics": {
    "mean_frequency": 200.0,
    "min_frequency": 150.0,
    "max_frequency": 250.0,
    "frequency_range": 100.0
  },
  "feedback": "Good tone 2 rising pattern. Work on steadier speech rate."
}
```

### Transcription

**POST** `/api/transcribe`

- Input: audio file + model selection (openai/gemini)
- Output: transcribed text
- Example:

```json
{
  "text": "你好，我是学生",
  "model": "openai"
}
```

### Reference Tones

**GET** `/api/reference-tone/{tone_number}`

- Input: tone_number (1-4)
- Output: reference pitch pattern for comparison
- Example:

```json
{
  "tone": 2,
  "name": "Rising",
  "character": "麻",
  "pinyin": "má",
  "description": "Rising from mid to high",
  "pitch_pattern": [0.5, 0.6, 0.7, 0.8, 0.85],
  "frequency_range": [200, 300],
  "expected_mean": 240
}
```

---

## Understanding Mandarin Tone Metrics

### Detected Tone

- **Tone 1 (High Level)**: 妈 (mā) - flat, steady pitch
- **Tone 2 (Rising)**: 麻 (má) - rises from middle to high
- **Tone 3 (Falling-Rising)**: 马 (mǎ) - falls then rises (valley shape)
- **Tone 4 (Falling)**: 骂 (mà) - falls sharply from high to low

### Tone Accuracy (0-100%)

- Compares your pitch contour to reference tone
- 85%+ = Excellent
- 70-84% = Good
- 55-69% = Acceptable
- <55% = Needs improvement

### Speech Rate (syllables/sec)

- Optimal for Mandarin: 4-5 syllables/sec
- <3.5: Speaking too slowly
- > 5.5: Speaking too fast

### Fluency (0-100)

- Based on pitch smoothness and consistency
- Higher = smoother transitions between tones
- Lower = abrupt pitch changes or hesitations

### Formants (F1, F2, F3)

- Frequency characteristics of vowels
- Indicates vowel quality and pronunciation
- Used for detailed phonetic analysis

---

## Troubleshooting

### Backend Issues

**Error: "Praat not found"**

- Solution: Install Praat and ensure it's in PATH
- Test: `praat --version`

**Error: "parselmouth import error"**

- Solution: Reinstall parselmouth

```bash
pip uninstall parselmouth
pip install parselmouth-praat
```

**Error: "API key not configured"**

- Solution: Check `backend/.env` has correct keys
- Make sure backend is restarted after env changes

**Backend won't start on port 8000**

- Solution: Port might be in use

```bash
# Change port
uvicorn main:app --reload --port 8001
# Update frontend VITE_BACKEND_URL to http://localhost:8001
```

### Frontend Issues

**Error: "Failed to connect to backend"**

- Check backend is running on http://localhost:8000
- Check `VITE_BACKEND_URL` in `.env.local`
- Check browser console for CORS errors

**Pitch chart not showing**

- Make sure Chart.js was installed: `npm install`
- Check browser console for JavaScript errors
- Ensure audio has sufficient length (>0.5 seconds)

**No transcription**

- Check selected model matches your API keys
- Verify API keys in `backend/.env` are valid
- Check backend logs for error messages

---

## Development Tips

### Testing the Backend Directly

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test with sample audio file
curl -X POST http://localhost:8000/api/analyze \
  -F "file=@sample.wav"

# List all reference tones
curl http://localhost:8000/api/all-tones
```

### Building for Production

```bash
# Frontend
npm run build

# Backend
# Use gunicorn or similar for production:
# pip install gunicorn
# gunicorn -w 4 -b 0.0.0.0:8000 main:app
```

### Monitoring

- Check backend logs for errors
- Use Chrome DevTools to inspect network requests
- Monitor CPU/memory usage during analysis

---

## Next Steps

1. **Record your first Mandarin speech** - Try saying "你好" (Hello)
2. **Experiment with different tones** - Try all 4 tones of "妈"
3. **Compare to reference tones** - Use the pitch chart
4. **Track progress** - Audio history saves all recordings with metrics
5. **Adjust speech rate** - Work on speaking at 4-5 syllables/sec

---

## Support & Resources

- **Praat Documentation:** https://www.fon.hum.uva.nl/praat/
- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **Parselmouth Docs:** https://parselmouth.readthedocs.io/
- **Mandarin Tones:** https://en.wikipedia.org/wiki/Tone_(linguistics)
