# Canonical Lesson 5 quiz banks

These UTF-8 CSV files are canonical quiz sources for Modern Chinese 1. The
Lesson 5 banks retain the focused 5-2 and 5-3 sources. The full
`modern-chinese-ch5-to-ch8-question-bank.csv` is the exported Questions sheet
from `modern_chinese_ch5_to_ch8_question_bank_english.xlsx`: 216 vocabulary and
phrase items, each with one question for each of the three rounds (648 total)
across lesson parts 5-1 through 8-3.

Validate or prepare a bank without changing the database:

```powershell
python backend/scripts/import_vocab_assessment.py backend/scripts/data/quiz_assessments/l5-2-vocab-assessment.csv
```

Use `l5-3-vocab-assessment.csv` for the Lesson 5-3 vocabulary-list bank. To publish by lesson metadata after the corresponding stories have been created or imported, run:

```powershell
python backend/scripts/seed_quiz_assessments.py --lesson-part 5-2 --publish
python backend/scripts/seed_quiz_assessments.py --lesson-part 5-3 --publish
```

To validate or publish the complete Chapters 5–8 workbook export, run:

```powershell
python backend/scripts/import_question_bank_workbook.py
python backend/scripts/import_question_bank_workbook.py --publish
```

The workbook's current round design is preserved: Round 1 is an English-meaning
MCQ, Round 2 is typed pinyin, and Round 3 is a context-cloze MCQ. Publishing
requires one existing story for each lesson part and the explicit `--publish`
flag.

Publishing requires the explicit `--publish` flag and exactly one existing story for the requested part. The files do not restore or modify the separately managed Materials records.
