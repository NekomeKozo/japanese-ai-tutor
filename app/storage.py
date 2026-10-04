"""Small SQL compatibility boundary for the application's existing migrations.

Only application-owned SQL is accepted here; values always remain bound parameters.
Postgres stores double precision values to match SQLite REAL, and serializes short
transactions to preserve the prototype's SQLite write semantics across workers.
"""
import re
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import conninfo_to_dict


class PostgresConnection:
    def __init__(self, connection):
        self.raw = connection

    def execute(self, sql, params=()):
        sql = sql.strip().rstrip(';')
        if sql == 'BEGIN IMMEDIATE':
            # The enclosing repository transaction already owns this lock.
            return self.raw.execute('SELECT 1')
        if sql == 'PRAGMA user_version':
            return self.raw.execute('SELECT version FROM schema_version WHERE id=1')
        version = re.fullmatch(r'PRAGMA user_version=(\d+)', sql)
        if version:
            return self.raw.execute('UPDATE schema_version SET version=%s WHERE id=1', (int(version[1]),))
        if 'sqlite_master' in sql:
            table = re.search(r"name='([a-z_]+)'", sql)
            if not table:
                raise ValueError('Unsupported schema inspection')
            return self.raw.execute('SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=%s', (table[1],))
        if sql.startswith('PRAGMA'):
            raise ValueError('Unsupported storage operation')
        if sql.startswith('INSERT OR IGNORE INTO '):
            sql = sql.replace('INSERT OR IGNORE INTO ', 'INSERT INTO ', 1) + ' ON CONFLICT DO NOTHING'
        if sql.startswith('INSERT OR REPLACE INTO mastery_history '):
            sql = sql.replace('INSERT OR REPLACE INTO ', 'INSERT INTO ', 1)
            sql += ' ON CONFLICT(learner_id,topic_id,event_id) DO UPDATE SET recorded_at=excluded.recorded_at,snapshot_json=excluded.snapshot_json'
        if sql.startswith('CREATE TABLE'):
            sql = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', sql)
        # Split off SQL string literals so question marks and percentages in literals
        # cannot be mistaken for bind markers. Current queries use positional binds.
        parts = re.split(r"('(?:''|[^'])*')", sql)
        for index in range(0, len(parts), 2):
            parts[index] = parts[index].replace('?', '%s')
        sql = ''.join(parts)
        sql = sql.replace('%s IS NULL', 'CAST(%s AS TEXT) IS NULL')
        return self.raw.execute(sql, params or None)

    def executescript(self, sql):
        # Used only by the fixed v1 DDL, which has no semicolons inside literals.
        for statement in sql.split(';'):
            if statement.strip():
                self.execute(statement)


@contextmanager
def postgres_connection(url, *, initialize=False, serialize=True):
    # Supabase's session pooler can pool these short-lived connections. Disable
    # prepared statements for compatibility with its transaction pooler too.
    options = conninfo_to_dict(url)
    if options.get('host') not in ('localhost', '127.0.0.1', '::1'):
        # Remote learner data is never sent on an unencrypted connection.
        if options.get('sslmode') not in ('verify-ca', 'verify-full'):
            options['sslmode'] = 'require'
    with psycopg.connect(**options, connect_timeout=5, prepare_threshold=None) as connection:
        connection.execute("SET LOCAL statement_timeout='10s'")
        connection.execute("SET LOCAL lock_timeout='5s'")
        if serialize:
            connection.execute('SELECT pg_advisory_xact_lock(650065)')
        if initialize:
            connection.execute('CREATE SCHEMA IF NOT EXISTS tutor_private')
            connection.execute('REVOKE ALL ON SCHEMA tutor_private FROM PUBLIC')
        connection.execute('SET LOCAL search_path TO tutor_private')
        if initialize:
            connection.execute('CREATE TABLE IF NOT EXISTS schema_version (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)')
            connection.execute('INSERT INTO schema_version VALUES (1,0) ON CONFLICT DO NOTHING')
        yield PostgresConnection(connection)
