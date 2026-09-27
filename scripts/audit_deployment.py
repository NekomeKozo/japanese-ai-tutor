"""Read-only source/history audit. Never prints matched secret material."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', '-C', str(ROOT), *args])


def private(path):
    parts = Path(path).parts
    name = Path(path).name
    return (any(p in {'reference', 'references', 'knowledge_base', '.venv', 'node_modules'} for p in parts)
            or (parts and parts[0] == 'data')
            or (name.startswith('.env') and name != '.env.example')
            or bool(re.search(r'\.(db|sqlite|sqlite3|pdf|epub)(-|$)', name, re.I)))


PATTERNS = {
    'Gemini key': rb'AIza[0-9A-Za-z_-]{30,}',
    'OpenAI key': rb'sk-(?:proj-)?[A-Za-z0-9_-]{24,}',
    'Groq key': rb'gsk_[A-Za-z0-9]{30,}',
    'GitHub token': rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
}


def main():
    secrets = []
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line:
                name, value = line.split('=', 1)
                value = value.strip().strip('\"\'')
                if any(s in name.upper() for s in ('KEY', 'SECRET', 'PASSWORD', 'DATABASE_URL', 'ACCESS_CODE')) and len(value) > 15:
                    secrets.append(value.encode())
    findings = set()
    def inspect(path, body, where):
        if private(path):
            findings.add((where, path, 'private file'))
        for label, pattern in PATTERNS.items():
            if re.search(pattern, body):
                findings.add((where, path, label))
        if any(value in body for value in secrets):
            findings.add((where, path, 'configured local secret'))
        # Ignore documented placeholders and the throwaway loopback CI database.
        for match in re.finditer(rb'postgres(?:ql)?://[^\s:@]+:([^\s@]+)@([^\s/]+)', body):
            if not match[2].startswith((b'localhost', b'127.0.0.1')) and match[1] not in (b'<password>', b'[YOUR-PASSWORD]'):
                findings.add((where, path, 'database credentials'))
    paths = git('ls-files', '--cached', '--others', '--exclude-standard', '-z').decode().split('\0')
    for path in filter(None, paths):
        file = ROOT / path
        if file.is_file():
            inspect(path, file.read_bytes(), 'working tree')
    for entry in git('rev-list', '--objects', '--all').decode().splitlines():
        oid, _, path = entry.partition(' ')
        if path and git('cat-file', '-t', oid).strip() == b'blob':
            inspect(path, git('cat-file', 'blob', oid), 'history')
    if not (ROOT / 'app/assessment/data/questions.json').is_file():
        findings.add(('working tree', 'app/assessment/data/questions.json', 'missing question bank'))
    if findings:
        for where, path, label in sorted(findings):
            print(f'{where}: {path}: {label}')
        raise SystemExit(1)
    print('Source and available Git history audit passed; no secret candidates or private files found.')


if __name__ == '__main__':
    main()
