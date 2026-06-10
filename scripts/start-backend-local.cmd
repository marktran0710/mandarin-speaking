@echo off
cd /d D:\hautran\Lab\mandarin-speaking\backend
set CORS_ORIGINS=http://localhost:5175,http://127.0.0.1:5175,http://localhost:5173,http://127.0.0.1:5173
set ASR_FALLBACK_ORDER=vibevoice,gemini,openai
"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8001 >> D:\hautran\Lab\mandarin-speaking\backend\uvicorn-active.log 2>&1
