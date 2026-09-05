#!/usr/bin/env python3
"""Validate the open format, optional UI metadata, and local resource links."""
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
from skills_ref import read_properties, validate


def validate_repository(root):
    skill = root / 'skills' / 'research-report'
    errors = list(validate(skill))
    properties = read_properties(skill)
    if properties.name != skill.name:
        errors.append('Skill name must match its parent directory.')
    entry = (skill / 'SKILL.md').read_text(encoding='utf-8')
    if len(entry.splitlines()) >= 500:
        errors.append('Move conditional detail out of the entrypoint.')
    if '[TODO:' in entry:
        errors.append('Unfinished initializer placeholder.')
    ui = yaml.safe_load((skill / 'agents' / 'openai.yaml').read_text(encoding='utf-8'))
    interface = ui.get('interface', {})
    if not isinstance(interface.get('display_name'), str) or not interface['display_name'].strip():
        errors.append('UI display_name is missing.')
    short = interface.get('short_description', '')
    if not isinstance(short, str) or not 25 <= len(short) <= 64:
        errors.append('UI short_description must be 25–64 characters.')
    if '$research-report' not in interface.get('default_prompt', ''):
        errors.append('UI default_prompt must mention the skill.')
    if ui.get('policy', {}).get('allow_implicit_invocation', True) is not True:
        errors.append('This skill uses normal automatic discovery.')

    paths = sorted(skill.rglob('*')) + [root / 'README.md']
    checked_links = 0
    for path in paths:
        if path.is_symlink():
            errors.append(f'Package resource must not be a symlink: {path.relative_to(root)}')
        if not path.is_file() or path.suffix not in {'.md', '.html', '.css', '.yaml'}:
            continue
        content = path.read_text(encoding='utf-8')
        if path.suffix == '.md':
            links = re.findall(r'\]\(([^)]+)\)', content) + re.findall(r'(?:href|src)="([^"]+)"', content)
        elif path.suffix == '.html':
            links = re.findall(r'(?:href|src)="([^"]+)"', content)
        else:
            links = []
        for link in links:
            parsed = urlparse(link)
            if parsed.scheme or not parsed.path:
                continue
            target = (path.parent / unquote(parsed.path)).resolve()
            boundary = root if path == root / 'README.md' else skill
            if not target.is_relative_to(boundary.resolve()) or not target.exists():
                errors.append(f'Unresolved local resource: {path.relative_to(root)} -> {link}')
            checked_links += 1
    for required in ['LICENSE', 'assets/html/report.css', 'assets/html/example.html',
                     'scripts/render_html.py', 'scripts/requirements.txt']:
        if not (skill / required).is_file():
            errors.append(f'Missing resource: {required}')
    return {'skill': properties.name, 'entrypoint_lines': len(entry.splitlines()),
            'checked_local_links': checked_links, 'errors': errors}


if __name__ == '__main__':
    result = validate_repository(Path(__file__).resolve().parents[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result['errors'] else 0)
