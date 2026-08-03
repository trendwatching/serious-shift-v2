"""Fail CI when repository safety controls silently drift."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / '.github' / 'workflows'
SHA = re.compile(r'^\s*-\s+uses:\s+[^\s@]+@([0-9a-f]{40})(?:\s+#.*)?$')


def main() -> None:
    errors: list[str] = []
    owners = ROOT / '.github' / 'CODEOWNERS'
    if not owners.is_file() or '@kalp-shah-57' not in owners.read_text(encoding='utf-8'):
        errors.append('CODEOWNERS must assign the repository to @kalp-shah-57')

    for workflow in sorted(WORKFLOWS.glob('*.yml')):
        text = workflow.read_text(encoding='utf-8')
        if 'permissions:\n  contents: read' not in text:
            errors.append(f'{workflow.name}: missing read-only top-level permissions')
        if 'timeout-minutes:' not in text:
            errors.append(f'{workflow.name}: every job needs a timeout')
        if 'releases/latest/' in text:
            errors.append(f'{workflow.name}: floating release download')
        for line_number, line in enumerate(text.splitlines(), 1):
            if re.match(r'^\s*-\s+uses:', line) and not SHA.match(line):
                errors.append(f'{workflow.name}:{line_number}: action is not pinned to a full SHA')

    for filename, schedule in (
        ('railway.ingest.json', '0 22 * * 0'),
        ('railway.synthesize.json', '0 2 * * 1'),
    ):
        value = json.loads((ROOT / filename).read_text(encoding='utf-8'))
        if value.get('deploy', {}).get('cronSchedule') != schedule:
            errors.append(f'{filename}: expected cron {schedule!r}')

    for workflow_name in ('backend.yml', 'db.yml', 'frontend.yml', 'pipeline.yml'):
        if '"railway*.json"' not in (WORKFLOWS / workflow_name).read_text(encoding='utf-8'):
            errors.append(f'{workflow_name}: Railway config changes bypass this check')

    if errors:
        raise SystemExit('\n'.join(f'- {error}' for error in errors))
    print('repository governance checks passed')


if __name__ == '__main__':
    main()
