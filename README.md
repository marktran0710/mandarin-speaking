# 🎤 Mandarin Speaking App with Praat Analysis

A modern web application for learning Mandarin Chinese through interactive speech recording, transcription, and AI-powered acoustic analysis using Praat.

## ✨ Features

- 🎤 **Real-time audio recording** - Record Mandarin speech with Web Audio API
- 🔄 **Multi-model transcription** - Choose from Web Speech API (free), OpenAI Whisper, or Google Gemini
- 📊 **Praat acoustic analysis** - Extract pitch, formants, speech rate, and fluency metrics
- 🎯 **Tone detection** - Identify which Mandarin tone (1-4) was spoken
- 📈 **Tone accuracy scoring** - Compare your pitch contour to reference tones
- 📉 **Pitch visualization** - Interactive charts showing your pitch vs reference patterns
- 💾 **Audio history** - Save and review all recordings with detailed metrics
- 🛡️ **Secure API keys** - Backend-based key management (no keys exposed to browser)
- 🎨 **Beautiful UI** - Responsive design with modern gradient aesthetics

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Node.js 16+
- Praat 6.0+ ([download](https://www.fon.hum.uva.nl/praat/))

### Setup (5 minutes)

1. **Install dependencies:**

   ```bash
   npm install
   cd backend && pip install -r requirements.txt
   ```

2. **Configure API keys:**

   ```bash
   cd backend
   cp .env.example .env
   # Edit .env with your OpenAI and/or Gemini API keys
   ```

3. **Start backend:**

   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```

4. **Start frontend:**

   ```bash
   npm run dev
   ```

5. **Open browser:**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000/docs

**👉 See [SETUP_GUIDE.md](./SETUP_GUIDE.md) for detailed setup instructions.**

## 📚 How It Works

### User Flow

1. Select a learning topic and story image
2. Record yourself speaking Mandarin
3. Choose transcription model (Web Speech, OpenAI, or Gemini)
4. Backend analyzes with Praat
5. View results:
   - Detected tone + accuracy %
   - Pitch contour chart
   - Speech rate and fluency scores
   - Formant frequencies
   - AI-generated feedback

### Architecture

```
Frontend (React)
    ↓
Backend (Python FastAPI)
    ├→ Praat (acoustic analysis)
    ├→ OpenAI Whisper API (transcription)
    └→ Google Gemini API (transcription)
```

## 📊 Mandarin Tone Metrics

### Detected Tone

- **Tone 1 (妈 mā)**: High, flat pitch
- **Tone 2 (麻 má)**: Rising pitch
- **Tone 3 (马 mǎ)**: Falling-rising (valley)
- **Tone 4 (骂 mà)**: Sharp falling pitch

### Key Metrics

| Metric        | Range         | Meaning                               |
| ------------- | ------------- | ------------------------------------- |
| Tone Accuracy | 0-100%        | How well your pitch matches reference |
| Speech Rate   | syllables/sec | Optimal: 4-5                          |
| Fluency       | 0-100         | Pitch smoothness and consistency      |
| Formants      | F1, F2, F3 Hz | Vowel characteristics                 |

## 🔐 Security

✅ **API keys are NOT exposed to browser**

- Keys stored in `backend/.env`
- Backend proxies all API requests
- Frontend only needs backend URL

## 📁 Project Structure

```
e:\MyFolder\Lab\Speaking App\
├── src/
│   ├── App.tsx              (Main app with recording/analysis)
│   ├── TopicSelector.tsx    (Topic selection component)
│   ├── PitchChart.tsx       (Chart.js visualization)
│   ├── main.tsx            (React entry point)
│   └── index.css           (Styling)
├── backend/
│   ├── main.py             (FastAPI app)
│   ├── praat_analyzer.py   (Praat integration)
│   ├── chinese_tones.py    (Mandarin tone logic)
│   ├── requirements.txt    (Python dependencies)
│   └── .env.example        (Environment template)
├── package.json
├── vite.config.ts
├── tsconfig.json
├── SETUP_GUIDE.md          (Detailed setup guide)
└── README.md              (This file)
```

## 🛠️ Technology Stack

### Frontend

- React 18 - UI framework
- TypeScript - Type safety
- Vite - Fast build tool
- Chart.js - Data visualization
- Web Audio API - Audio recording

### Backend

- Python 3.10+ - Language
- FastAPI - Web framework
- Uvicorn - ASGI server
- Parselmouth - Praat Python bindings
- NumPy/SciPy - Signal processing
- OpenAI/Gemini APIs - Speech transcription

## 📖 API Documentation

### Endpoints

**POST /api/analyze** - Analyze Chinese speech with Praat

```json
Request: multipart/form-data with audio file
Response: {
  "detected_tone": 2,
  "tone_accuracy": 85.5,
  "pitch_contour": [[time, freq], ...],
  "speech_rate": 5.2,
  "fluency_score": 78.3,
  "formants": {"F1": 720, "F2": 1220, "F3": 2600},
  "feedback": "..."
}
```

**POST /api/transcribe** - Transcribe audio

```json
Request: multipart/form-data with audio file + model
Response: {"text": "你好", "model": "openai"}
```

**GET /api/reference-tone/{tone}** - Get reference tone pattern

```json
Response: {
  "tone": 2,
  "name": "Rising",
  "pitch_pattern": [0.5, 0.6, 0.7, ...],
  ...
}
```

See [SETUP_GUIDE.md](./SETUP_GUIDE.md) for full API documentation.

## 🧪 Testing

### Test the backend directly:

```bash
# Health check
curl http://localhost:8000/health

# Analyze audio
curl -X POST http://localhost:8000/api/analyze \
  -F "file=@sample.wav"

# List reference tones
curl http://localhost:8000/api/all-tones
```

### Browser testing:

1. Open http://localhost:5173
2. Record a Mandarin sentence
3. Check console for network requests
4. Verify metrics display

## 🐛 Troubleshooting

**Backend won't start:**

- Ensure Praat is installed and in PATH: `praat --version`
- Check Python version: `python --version` (need 3.10+)
- Reinstall parselmouth: `pip install --upgrade parselmouth-praat`

**Frontend can't connect to backend:**

- Check backend is running on http://localhost:8000
- Check `VITE_BACKEND_URL` in `.env.local`
- Check browser console for CORS errors

**Pitch analysis not working:**

- Ensure audio file is > 0.5 seconds
- Check that Praat installation is valid
- See [SETUP_GUIDE.md](./SETUP_GUIDE.md) for detailed troubleshooting

## 📝 License

MIT

## 🙋 Support

See [SETUP_GUIDE.md](./SETUP_GUIDE.md) for comprehensive setup, troubleshooting, and API documentation.
