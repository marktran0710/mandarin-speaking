# Canonical Lesson 5 quiz banks

These UTF-8 CSV files are the canonical vocabulary-assessment source for the Modern Chinese 1 Lesson 5 dialogue and reading. They use the textbook's Traditional Chinese, pinyin, meanings, and example sentences from printed pages 119-123 (5-2) and 127-129 (5-3). Each file provides one Easy, Medium, and Hard observation for every referenced lesson word: 16 words / 48 questions for 5-2 and 11 words / 33 questions for 5-3.

Validate or prepare a bank without changing the database:

```powershell
python backend/scripts/import_vocab_assessment.py backend/scripts/data/quiz_assessments/l5-2-vocab-assessment.csv
```

Use `l5-3-vocab-assessment.csv` for the Lesson 5-3 reading bank. To publish by lesson metadata after the corresponding stories have been created or imported, run:

```powershell
python backend/scripts/seed_quiz_assessments.py --lesson-part 5-2 --publish
python backend/scripts/seed_quiz_assessments.py --lesson-part 5-3 --publish
```

Publishing requires the explicit `--publish` flag and exactly one existing story for the requested part. The files do not restore or modify the separately managed Materials records.
