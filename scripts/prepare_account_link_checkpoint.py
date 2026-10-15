"""Offline sealing of previously reviewed evidence. Never connects to a DB.

No IDs/keys are printed. Preparing an artifact does not grant rollout/link consent.
Use an encrypted private secret file outside the checkout; never static hosting.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.fernet import Fernet, MultiFernet
from app.accounts import AccountService
from app.account_link_checkpoint import seal_review
from app.config import PROJECT_ROOT, Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--selection', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if (not args.output.is_absolute() or args.output.resolve().is_relative_to(PROJECT_ROOT)
            or args.output.exists()):
        parser.error('Use a new absolute private output path outside the checkout.')
    # Settings validates keys/allowlists; constructing no service or repository
    # avoids initialization, Auth calls, session touches, or database connections.
    import time
    settings = Settings()
    if not settings.account_auth_enabled:
        parser.error('Account configuration must already be active; no setting is changed here.')
    class Sealer:
        allowed = set(settings.account_invited_ids.get_secret_value().split(','))
        bootstrap_owners = set(settings.account_owner_bootstrap_ids.get_secret_value().split(','))
        keys = settings.account_session_encryption_keys.get_secret_value().split(',')
        cipher = MultiFernet([Fernet(key.encode()) for key in keys])
        key_version = hashlib.sha256(keys[0].encode()).hexdigest()[:16]
        encrypt = AccountService.encrypt
    try:
        sealed = seal_review(args.review.read_bytes(), json.loads(args.selection.read_text(encoding='utf-8')), Sealer(), now=time.time())
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(sealed)
    except Exception:
        # Never print private evidence, validation values, paths or exceptions.
        print('checkpoint_prepared=false')
        return 1
    print('checkpoint_prepared=true; production_unchanged=true')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
