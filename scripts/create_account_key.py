"""Create a private operator key file, never emit its value or overwrite a key."""
import os
from pathlib import Path
import subprocess

from cryptography.fernet import Fernet


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / '.env.account-key'
    ignored = subprocess.run(['git', '-C', str(root), 'check-ignore', '--quiet', str(target)], check=False)
    if ignored.returncode != 0:
        raise SystemExit('Key file must be ignored by Git before generation.')
    try:
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SystemExit('A private key file already exists. It has not been changed.') from None
    with os.fdopen(descriptor, 'wb') as output:
        output.write(Fernet.generate_key() + b'\n')
    print('Created private .env.account-key. Copy its value directly to Render; never paste it into chat or Git.')


if __name__ == '__main__':
    main()
