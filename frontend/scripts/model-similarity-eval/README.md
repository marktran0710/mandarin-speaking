# Model-similarity evaluation harness

Reproduces the numbers in `docs/model-similarity-evaluation.md`. Read-only: it
only SELECTs from the dev database and never writes to it.

```bash
# 1. export teacher model contours + real learner attempts (run in the backend container)
docker cp frontend/scripts/model-similarity-eval/export_data.py mandarin-speaking-dev-backend-1:/tmp/
docker exec mandarin-speaking-dev-backend-1 sh -c "cd /app && PYTHONPATH=/app python /tmp/export_data.py"
docker cp mandarin-speaking-dev-backend-1:/tmp/export.json ./export.json

# 2. bundle + run a script against the REAL scorer in src/entities/speech
cd frontend
npx esbuild scripts/model-similarity-eval/evaluate.ts --bundle --platform=node --format=esm --outfile=/tmp/evaluate.mjs
EXPORT=../export.json OCTAVE=1 node /tmp/evaluate.mjs      # synthetic degradations, octave errors injected
EXPORT=../export.json OCTAVE=0 node /tmp/evaluate.mjs      # same, clean tracker
```

| script | what it answers |
|---|---|
| `evaluate.ts` | Can each candidate tell a natural re-recording of a teacher sentence from a degraded one (AUC + score distribution)? `CANDIDATES='[{"name":"x","opts":{"algorithm":"v2","params":{"rhoFull":0.7}}}]'` sweeps parameters; `COMPACT=1` prints one line each. |
| `real.ts` | How do legacy and v2 score the real learner attempts, and how many teacher tokens does octave cleaning touch? |
| `real-word-flexibility.ts` | On real learner words, does a more forgiving shape measure (wider shifts, smoothing, direction agreement, syllable-aware warp, chance correction) keep telling the right teacher word from a wrong one? Uses `export_after_regen.json`. |
| `teacher-quality.ts` | How noisy are the stored teacher contours (edge jumps, ranges)? Runs the production scorer over the real attempts. |

The synthetic classes are built from the teacher's own contours: a "natural
re-recording" (time warp +-15%, range x0.75-1.25, level shift, tracker jitter,
5% dropouts) versus flat, half-range, mirrored, time-reversed, other-word and
random-walk versions. Those labels are ours, not a teacher's: the harness shows
what a score can and cannot separate, not how a human would rate it.
