"""Candidate A exception: synthetic data and disposable loopback PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import secrets

import pytest

from app.accounts import COOKIE
from app.account_link_checkpoint import history, keyed, owner_state, seal_review, KIND
from tests.test_account_links import linked_context, login, preview, confirm, table_snapshot
from tests.test_accounts import bootstrap
from tests.test_postgres import pg_settings


def evidence(client, learner, owner, ids, key):
    account = client.authority.payload['sub']
    with client.app.state.repository.connection() as db:
        state = owner_state(db, account, key)
        hist = history(db, learner, key)
    # Equivalent prior review/checkpoint structure. No real checkpoint or ID is
    # loaded by tests. An arbitrary Candidate B cannot be chosen by the sealer.
    item = {'learner_digest': keyed(key, learner), 'history': {}}
    review = {'version': 1, 'key': key.hex(), 'approved_owner_sha256': hashlib.sha256(account.encode()).hexdigest(),
              'approved_owner_state_digest': state, 'legacy_context_digest': keyed(key, owner),
              'eligible_set_digest': keyed(key, json.dumps(sorted(keyed(key, value) for value in ids))),
              'candidates': {'Candidate A': item}}
    # Use the actual 22-table evidence to match offline sealing and production
    # read-only review; capture only row hashes, never private row contents.
    from app.account_link_checkpoint import DIRECT, CHILDREN
    with client.app.state.repository.connection() as db:
        for table in (*DIRECT, *CHILDREN):
            if table in DIRECT:
                query = f"SELECT encode(sha256(convert_to(row_to_json(t)::text,'UTF8')),'hex') FROM {table} t WHERE t.learner_id=?"
            else:
                parent, foreign, pk = CHILDREN[table]
                query = f"SELECT encode(sha256(convert_to(row_to_json(t)::text,'UTF8')),'hex') FROM {table} t JOIN {parent} p ON t.{foreign}=p.{pk} WHERE p.learner_id=?"
            hashes = sorted(r[0] for r in db.execute(query, (learner,)).fetchall())
            item['history'][table] = {'count': len(hashes), 'digest': keyed(key, json.dumps(hashes))}
    raw = json.dumps(review).encode()
    selection = {'version': 1, 'candidate': 'Candidate A',
                 'verified_at': datetime.fromtimestamp(client.app.state.accounts.clock() - 1, timezone.utc).isoformat(),
                 'review_checkpoint_sha256': hashlib.sha256(raw).hexdigest(),
                 **{k: review[k] for k in ('approved_owner_sha256', 'approved_owner_state_digest', 'legacy_context_digest', 'eligible_set_digest')},
                 'selected_learner_digest': item['learner_digest'], 'selected_history_digest': hist}
    selection['selection_binding_digest'] = keyed(key, json.dumps(selection, sort_keys=True))
    return raw, selection


@pytest.fixture
def checkpoint_context(linked_context, tmp_path):
    client, learner, authority = linked_context
    repo = client.app.state.repository
    # Only disposable fixture provider metadata; never change Supabase tables.
    with repo.connection() as db:
        db.execute("ALTER TABLE auth.users ADD created_at TIMESTAMPTZ NOT NULL DEFAULT '2026-01-01T00:00:00Z', ADD email_confirmed_at TIMESTAMPTZ DEFAULT '2026-01-01T00:00:00Z', ADD deleted_at TIMESTAMPTZ, ADD banned_until TIMESTAMPTZ, ADD is_anonymous BOOLEAN NOT NULL DEFAULT false")
    # Populate selected history before independent review, then create B and C.
    assert client.post(f'/api/learners/{learner}/sessions').status_code == 201
    assert client.patch(f'/api/learners/{learner}/preferences', json={'primary_goal': 'travel'}).status_code == 200
    others = [client.post('/api/learners').json()['learner_id'] for _ in range(2)]
    with repo.connection() as db:
        owner = db.execute("SELECT owner_id FROM staging_resources WHERE kind='learner' AND resource_id=?", (learner,)).fetchone()[0]
    login(client)
    raw, selection = evidence(client, learner, owner, [learner, *others], secrets.token_bytes(32))
    artifact = tmp_path / 'private-owner-checkpoint'
    artifact.write_text(seal_review(raw, selection, client.app.state.accounts, now=client.app.state.accounts.clock()))
    client.app.state.settings.account_learner_checkpoint_path = str(artifact)
    client.checkpoint = artifact
    client.review_evidence = raw, selection
    client.other_candidates = others
    client.legacy_owner = owner
    yield client, learner, authority


@pytest.mark.parametrize('linked_context', ['postgres-history'], indirect=True)
def test_selected_preview_link_retry_and_history_preservation(checkpoint_context):
    client, learner, _ = checkpoint_context
    before = table_snapshot(client.app.state.repository)
    response = client.get('/api/account/link-preview')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['summary']['estimated_level']
    assert all(value not in response.text for value in [learner, *client.other_candidates, client.authority.payload['sub'], client.legacy_owner])
    assert table_snapshot(client.app.state.repository) == before
    with client.app.state.repository.connection() as db:
        assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0] == 0
    proof = data['confirmation']
    assert confirm(client, proof).status_code == 200
    assert confirm(client, proof).status_code == 200
    with client.app.state.repository.connection() as db:
        rows = db.execute('SELECT learner_id,proof_method FROM account_learner_links').fetchall()
    assert rows == [(learner, 'checkpoint_legacy_owner_v1')]
    assert table_snapshot(client.app.state.repository) == before
    for other in client.other_candidates:
        assert client.get(f'/api/learners/{other}/profile').status_code == 409


@pytest.mark.parametrize('linked_context', ['postgres'], indirect=True)
@pytest.mark.parametrize('failure', [
    'tampered', 'expired', 'missing', 'different-artifact', 'eligible-added',
    'eligible-removed', 'history', 'owner-state', 'learner-linked', 'owner-linked',
    'stale-session', 'stale-auth', 'legacy-context', 'csrf', 'origin', 'cross-site',
    'other-session', 'unconfirmed', 'provider-session', 'policy', 'flag-off',
    'candidate-b', 'candidate-c', 'browser-id', 'checkpoint-disabled', 'other-candidate-linked',
    'forged-selected-b', 'forged-selected-c', 'expired-artifact', 'expired-confirmation'])
def test_confirmation_fails_closed(checkpoint_context, monkeypatch, failure):
    client, learner, authority = checkpoint_context
    repo = client.app.state.repository
    proof = preview(client)
    headers = bootstrap(client)
    body = {'confirm': True, 'confirmation': proof}
    if failure == 'tampered': client.checkpoint.write_text('invalid')
    elif failure == 'expired': client.app.state.accounts.clock = lambda: 10**12
    elif failure == 'missing': client.checkpoint.unlink()
    elif failure == 'different-artifact':
        raw, selection = client.review_evidence
        client.checkpoint.write_text(seal_review(raw, selection, client.app.state.accounts, now=client.app.state.accounts.clock()))
    elif failure == 'eligible-added':
        extra = client.app.state.learners.create()['learner_id']
        with repo.connection() as db: db.execute('INSERT INTO staging_resources VALUES (?,?,?)', ('learner', extra, client.legacy_owner))
    elif failure == 'eligible-removed':
        with repo.connection() as db: db.execute("DELETE FROM staging_resources WHERE kind='learner' AND resource_id=?", (learner,))
    elif failure == 'history':
        with repo.connection() as db: db.execute("UPDATE learner_state SET last_activity_at='2026-10-01T00:00:00Z' WHERE learner_id=?", (learner,))
    elif failure == 'owner-state':
        with repo.connection() as db: db.execute("UPDATE auth.users SET created_at=created_at+INTERVAL '1 second' WHERE id=?", (authority.payload['sub'],))
    elif failure in ('learner-linked', 'owner-linked'):
        account = authority.second['sub'] if failure == 'learner-linked' else authority.payload['sub']
        target = learner if failure == 'learner-linked' else client.other_candidates[0]
        with repo.connection() as db: db.execute('INSERT INTO account_learner_links VALUES (?,?,?,?,?,?,?,?)', (account, target, 0, 1, 'signed_legacy_owner_v1', 'fixture', 'fixture', 'fixture'))
    elif failure == 'stale-session':
        with repo.connection() as db: db.execute('UPDATE account_sessions SET absolute_expiry=0')
    elif failure == 'stale-auth':
        now = client.app.state.accounts.clock(); client.app.state.accounts.clock = lambda: now + 601
    elif failure == 'legacy-context':
        monkeypatch.setattr('app.safeguards.read_session', lambda *args, **kwargs: None)
    elif failure == 'csrf': headers['X-CSRF-Token'] = 'invalid'
    elif failure == 'origin': headers['Origin'] = 'https://foreign.test'
    elif failure == 'cross-site': headers['Sec-Fetch-Site'] = 'cross-site'
    elif failure == 'other-session': login(client); headers = bootstrap(client)
    elif failure == 'unconfirmed': authority.user.pop('email_confirmed_at')
    elif failure == 'provider-session':
        with repo.connection() as db: db.execute('DELETE FROM auth.sessions WHERE user_id=?', (authority.payload['sub'],))
    elif failure == 'policy': authority.public = True
    elif failure == 'flag-off': client.app.state.settings.account_learner_linking_enabled = False
    elif failure in ('candidate-b', 'candidate-c'): body['candidate'] = 'Candidate B' if failure == 'candidate-b' else 'Candidate C'
    elif failure == 'browser-id': body['learner_id'] = client.other_candidates[0]
    elif failure == 'checkpoint-disabled': client.app.state.settings.account_learner_checkpoint_path = ''
    elif failure == 'other-candidate-linked':
        with repo.connection() as db: db.execute('INSERT INTO account_learner_links VALUES (?,?,?,?,?,?,?,?)', (authority.second['sub'], client.other_candidates[0], 0, 1, 'signed_legacy_owner_v1', 'fixture', 'fixture', 'fixture'))
    elif failure.startswith('forged-selected-'):
        # A proof for B/C is rejected even if encrypted with the fixture server's
        # key: checkpoint resolution, not the encrypted learner field, wins.
        payload = client.app.state.accounts.decrypt(proof)
        payload['learner'] = client.other_candidates[0 if failure.endswith('b') else 1]
        body['confirmation'] = client.app.state.accounts.encrypt(payload)
    elif failure == 'expired-artifact':
        accounts = client.app.state.accounts
        payload = accounts.decrypt(client.checkpoint.read_text())
        payload['issued'] = accounts.clock() - 3601; payload['expires'] = accounts.clock() - 1
        client.checkpoint.write_text(accounts.encrypt(payload))
    elif failure == 'expired-confirmation':
        now = client.app.state.accounts.clock(); client.app.state.accounts.clock = lambda: now + 301
    with repo.connection() as db: before_links = db.execute('SELECT * FROM account_learner_links').fetchall()
    before = table_snapshot(repo)
    result = client.post('/api/account/link-learner', json=body, headers=headers)
    assert result.status_code in (401, 403, 409, 422, 503), result.text
    with repo.connection() as db: assert db.execute('SELECT * FROM account_learner_links').fetchall() == before_links
    assert table_snapshot(repo) == before


@pytest.mark.parametrize('linked_context', ['postgres'], indirect=True)
def test_concurrent_link_revalidates_and_inserts_only_a(checkpoint_context):
    client, learner, _ = checkpoint_context
    proof = preview(client)
    before = table_snapshot(client.app.state.repository)
    nonce = client.cookies.get(COOKIE)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.app.state.account_links.confirm(nonce, client.legacy_owner, proof), range(4)))
    assert all(result['state'] == 'linked' for result in results)
    with client.app.state.repository.connection() as db:
        assert db.execute('SELECT learner_id FROM account_learner_links').fetchall() == [(learner,)]
    assert table_snapshot(client.app.state.repository) == before


@pytest.mark.parametrize('linked_context', ['postgres'], indirect=True)
def test_general_ambiguity_rejection_and_no_checkpoint_fallback(checkpoint_context):
    client, _, _ = checkpoint_context
    client.app.state.settings.account_learner_checkpoint_path = ''
    assert client.get('/api/account/link-preview').json()['error']['code'] == 'link_context_ambiguous'
    client.app.state.settings.account_learner_checkpoint_path = str(client.checkpoint)
    client.checkpoint.write_text('invalid')
    assert client.get('/api/account/link-preview').status_code == 409


@pytest.mark.parametrize('linked_context', ['postgres'], indirect=True)
def test_sealer_rejects_unreviewed_selection_wrong_owner_and_stale_evidence(checkpoint_context):
    client, _, _ = checkpoint_context
    raw, original = client.review_evidence
    accounts = client.app.state.accounts
    for change in ({'candidate': 'Candidate B'}, {'selected_learner_digest': 'arbitrary'}, {'review_checkpoint_sha256': 'wrong'}):
        with pytest.raises(Exception): seal_review(raw, original | change, accounts, now=accounts.clock())
    with pytest.raises(Exception): seal_review(raw, original, accounts, now=accounts.clock() + 86401)
    accounts.bootstrap_owners = {client.authority.second['sub']}
    with pytest.raises(Exception): seal_review(raw, original, accounts, now=accounts.clock())


@pytest.mark.parametrize('linked_context', ['postgres'], indirect=True)
def test_wrong_account_cannot_consume_a_checkpoint(checkpoint_context):
    client, _, authority = checkpoint_context
    accounts = client.app.state.accounts
    # Even making a different fixture account the sole bootstrap owner does not
    # let it consume the independently sealed original-account evidence.
    accounts.bootstrap_owners = {authority.second['sub']}
    authority.payload = authority.second
    authority.active = authority.payload
    authority.user = {'id': authority.payload['sub'], 'email': 'other@example.test', 'email_confirmed_at': '2026-01-01T00:00:00Z', 'is_anonymous': False}
    login(client, 'other@example.test')
    assert client.get('/api/account/link-preview').status_code == 409


@pytest.mark.parametrize('linked_context', ['postgres-history'], indirect=True)
def test_populated_placement_study_mastery_review_jlpt_audio_and_tutor_unchanged(checkpoint_context, monkeypatch):
    from tests import test_account_links as flows
    client, learner, _ = checkpoint_context
    original = flows.preview
    def reviewed_preview(current):
        # Simulate independent reviewed evidence AFTER synthetic study history
        # has been populated. This helper is test-only, never an application API.
        raw, selection = evidence(current, learner, current.legacy_owner, [learner, *current.other_candidates], secrets.token_bytes(32))
        current.checkpoint.write_text(seal_review(raw, selection, current.app.state.accounts, now=current.app.state.accounts.clock()))
        return original(current)
    monkeypatch.setattr(flows, 'preview', reviewed_preview)
    client.cookies.delete(COOKIE)  # Seed history through the existing legacy flow.
    flows.test_full_history_is_unchanged_by_link_and_restore(checkpoint_context, monkeypatch)


@pytest.mark.parametrize('linked_context', ['postgres'], indirect=True)
def test_operator_sealing_is_offline_private_and_never_overwrites(checkpoint_context, tmp_path, monkeypatch, capsys):
    from scripts import prepare_account_link_checkpoint as cli
    client, learner, _ = checkpoint_context
    raw, selection = client.review_evidence
    review = tmp_path / 'review.json'; review.write_bytes(raw)
    selected = tmp_path / 'selection.json'; selected.write_text(json.dumps(selection))
    output = tmp_path / 'new-private-artifact'
    monkeypatch.setattr(cli, 'Settings', lambda: client.app.state.settings)
    monkeypatch.setattr('sys.argv', ['prepare_account_link_checkpoint.py', '--review', str(review), '--selection', str(selected), '--output', str(output)])
    # Scope the network prohibition to sealing so fixture database cleanup can
    # still run regardless of pytest's dynamically requested fixture order.
    with monkeypatch.context() as offline:
        offline.setattr('psycopg.connect', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Sealing must remain offline')))
        assert cli.main() == 0
        text = output.read_text()
        assert learner not in text and client.authority.payload['sub'] not in text and json.loads(raw)['key'] not in text
        assert capsys.readouterr().out == 'checkpoint_prepared=true; production_unchanged=true\n'
        before = output.read_bytes()
        with pytest.raises(SystemExit): cli.main()
        assert output.read_bytes() == before
