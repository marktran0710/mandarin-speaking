# Speech to Text App

A modern React web application that records user speech and converts it to text using one of three options: **Web Speech API (Free)**, **OpenAI Whisper**, or **Google Gemini**.

## Features

- 🎤 Real-time audio recording using Web Audio API
- 🔄 Convert speech to text with **3 different models**:
  - 🌐 **Web Speech API** (Free, offline, no API key needed)
  - 🤖 **OpenAI Whisper** (High accuracy, cloud-based)
  - ✨ **Google Gemini** (Advanced AI, cloud-based)
- 📝 Display transcription history with timestamps and model info
- 🎨 Beautiful, responsive UI
- 📱 Works on desktop and mobile browsers
- 🔀 Switch between models with a dropdown selector

## Setup

### 1. Install Dependencies

```bash
npm install
```

### 2. Set Up API Keys (Optional)

For **Web Speech API**: No API key needed! Works offline in your browser.

For **OpenAI & Gemini**, create a `.env.local` file (optional):

```bash
cp .env.example .env.local
```

**For OpenAI Whisper:**
- Get your key from [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

**For Google Gemini:**
- Get your key from [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

Your `.env.local` should look like:
```
VITE_OPENAI_API_KEY=sk-your-openai-key-here
VITE_GEMINI_API_KEY=your-gemini-key-here
```

### 3. Start Development Server

```bash
npm run dev
```

The app will open at `http://localhost:5173`

## Usage

1. Select your preferred model from the dropdown:
   - **Web Speech API** - Use this first! It's free and works offline
   - **OpenAI** - Better accuracy for difficult audio
   - **Gemini** - Advanced transcription with additional features
2. Click **"Start Recording"** to begin recording audio
3. Speak clearly into your microphone
4. Click **"Stop Recording"** when done
5. The app will automatically transcribe your speech
6. The transcribed text will appear in the "Transcriptions" section with the model name

## Model Comparison

| Feature | Web Speech API | OpenAI Whisper | Google Gemini |
|---------|---|---|---|
| Cost | **FREE** | Pay per minute | Free tier (limited) |
| Offline | ✅ Yes | ❌ Cloud only | ❌ Cloud only |
| Accuracy | Good | Very High | Very High |
| Languages | Limited | 99+ | Multiple |
| API Key | ❌ Not needed | ✅ Required | ✅ Required |
| Browser Support | Chrome, Edge, Safari | All | All |

### 🎯 Recommendation

- **Start with Web Speech API** - It's free, fast, and works offline!
- **Use OpenAI** for professional/production use with highest accuracy
- **Use Gemini** if you have free tier quota or a paid plan

## Requirements

- Modern browser with microphone access
- Internet connection (only for OpenAI/Gemini)
- API keys for OpenAI/Gemini (optional - Web Speech API works without them)

## Project Structure

```
├── src/
│   ├── App.tsx          # Main app with 3 model options
│   ├── main.tsx         # React entry point
│   └── index.css        # Styling
├── index.html           # HTML template
├── vite.config.ts       # Vite configuration
├── tsconfig.json        # TypeScript configuration
├── package.json         # Dependencies
└── .env.example         # Environment variables template
```

## Technology Stack

- **React 18** - UI library
- **TypeScript** - Type-safe JavaScript
- **Vite** - Fast build tool
- **Web Audio API** - Audio recording
- **Web Speech API** - Browser-native speech recognition
- **OpenAI Whisper API** - Advanced speech-to-text
- **Google Gemini API** - Advanced speech-to-text

## Troubleshooting

- **"Failed to access microphone"**: Check browser permissions for microphone access
- **Web Speech API not working**: Use Chrome, Edge, or Safari. Firefox has limited support.
- **"API key not configured"**: Make sure `.env.local` exists if using OpenAI/Gemini
- **Blank transcriptions**: Ensure audio input is working and API key (if used) is valid
- **Quota exceeded**: This applies to OpenAI/Gemini. Switch to Web Speech API which is unlimited!

## License

MIT


