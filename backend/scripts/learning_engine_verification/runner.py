from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

@dataclass
class CheckResult:
    name: str
    status: str
    expected: Any = None
    actual: Any = None
    detail: str | None = None
    def as_dict(self) -> dict[str, Any]: return asdict(self)

def write_report(results: list[CheckResult], output_dir: Path, engine: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    payload = {'engine': engine, 'generated_at': datetime.now(timezone.utc).isoformat(), 'results': [r.as_dict() for r in results], 'summary': {s: sum(r.status == s for r in results) for s in ('PASS','FAIL','BLOCKED')}}
    jp, mp = output_dir / f'learning-engine-{engine}-{stamp}.json', output_dir / f'learning-engine-{engine}-{stamp}.md'
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [f'# Learning engine verification: `{engine}`', '', f"Generated: `{payload['generated_at']}`", '', '| Check | Status | Expected | Actual |', '|---|---|---|---|']
    for r in results:
        lines.append(f'| {r.name} | **{r.status}** | `{json.dumps(r.expected, ensure_ascii=False)}` | `{json.dumps(r.actual, ensure_ascii=False)}` |')
        if r.detail: lines.append(f'\n> {r.detail}')
    mp.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return mp, jp
