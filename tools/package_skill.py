#!/usr/bin/env python3
"""Build a deterministic, standalone ZIP from tracked skill files."""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from validate_skill import validate_repository


def main():
    root = Path(__file__).resolve().parents[1]
    result = validate_repository(root)
    if result['errors']:
        raise ValueError(result['errors'])
    output = root / 'dist' / 'research-report-v1.0.0.zip'
    if output.exists():
        raise ValueError('Release archive already exists; preserve it or choose a new version.')
    raw = subprocess.check_output(
        ['git', 'ls-files', '-z', '--', 'skills/research-report'], cwd=root
    )
    files = [root / item.decode('utf-8') for item in raw.split(b'\0') if item]
    if not files or not any(path.name == 'SKILL.md' for path in files):
        raise ValueError('Add the completed skill files to Git before packaging.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f'Unexpected tracked resource: {path.name}')
            name = path.relative_to(root / 'skills').as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive integrity validation failed.')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.parent / 'SHA256SUMS').write_text(f'{digest}  {output.name}\n', encoding='utf-8')
    print(json.dumps({'archive': output.name, 'files': len(files), 'sha256': digest}, indent=2))


if __name__ == '__main__':
    main()
