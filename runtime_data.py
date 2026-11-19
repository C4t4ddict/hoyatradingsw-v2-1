"""Durable public market cache and restartable collection job state."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from security import mask_text

BAR_MS = 4 * 60 * 60 * 1000
SYMBOLS = ('BTC/USDT', 'ETH/USDT', 'SOL/USDT')


class RuntimeStore:
    def __init__(self, path=None):
        self.path = str(path or os.getenv('RUNTIME_DB_PATH', 'data/runtime.sqlite3'))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
                    PRIMARY KEY(symbol,ts));
                CREATE TABLE IF NOT EXISTS funding (
                    symbol TEXT, ts INTEGER, rate REAL, PRIMARY KEY(symbol,ts));
                CREATE TABLE IF NOT EXISTS jobs (
                    name TEXT PRIMARY KEY, attempted REAL, succeeded REAL, failures INTEGER DEFAULT 0,
                    next_run REAL DEFAULT 0, error TEXT, details TEXT DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS worker (
                    id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER DEFAULT 1,
                    owner TEXT, expires REAL DEFAULT 0, heartbeat REAL);
                INSERT OR IGNORE INTO worker(id) VALUES(1);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def lease(self, owner, now=None, seconds=1800):
        now = time.time() if now is None else now
        with self.connection() as db:
            return bool(db.execute('''UPDATE worker SET owner=?, expires=?, heartbeat=?
                WHERE id=1 AND (owner=? OR expires<=?)''',
                (owner, now + seconds, now, owner, now)).rowcount)

    def release(self, owner):
        with self.connection() as db:
            db.execute('UPDATE worker SET owner=NULL,expires=0 WHERE id=1 AND owner=?', (owner,))

    def control(self, action):
        if action not in {'pause', 'resume', 'retry'}:
            raise ValueError('지원하지 않는 작업입니다')
        with self.connection() as db:
            if action != 'retry':
                db.execute('UPDATE worker SET enabled=? WHERE id=1', (action == 'resume',))
            if action in {'resume', 'retry'}:
                db.execute('UPDATE jobs SET next_run=0')

    def run_job(self, name, fn, interval, now=None):
        now = time.time() if now is None else now
        with self.connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE name=?', (name,)).fetchone()
            if row and row['next_run'] > now:
                return
            db.execute('INSERT OR IGNORE INTO jobs(name) VALUES(?)', (name,))
            db.execute('UPDATE jobs SET attempted=? WHERE name=?', (now, name))
        try:
            result = fn() or {}
        except Exception as exc:
            failures = (row['failures'] if row else 0) + 1
            with self.connection() as db:
                db.execute('UPDATE jobs SET failures=?,next_run=?,error=? WHERE name=?',
                           (failures, now + min(3600, 30 * 2 ** min(failures - 1, 7)),
                            mask_text(f'{type(exc).__name__}: {exc}')[:500], name))
        else:
            with self.connection() as db:
                db.execute('UPDATE jobs SET succeeded=?,failures=0,next_run=?,error=NULL,details=? WHERE name=?',
                           (now, now + interval, json.dumps(result, ensure_ascii=False), name))

    def put_candles(self, symbol, rows, now_ms):
        valid = []
        for row in rows:
            if len(row) < 6:
                raise ValueError('incomplete OHLCV row')
            ts, o, h, low, c, v = map(float, row[:6])
            if not all(math.isfinite(x) for x in (ts, o, h, low, c, v)):
                raise ValueError('non-finite OHLCV')
            if ts % BAR_MS or min(o, h, low, c) <= 0 or v < 0 or low > min(o, c) or h < max(o, c) or low > h:
                raise ValueError('invalid OHLCV')
            if ts + BAR_MS <= now_ms:
                valid.append((symbol, int(ts), o, h, low, c, v))
        with self.connection() as db:
            db.executemany('INSERT OR REPLACE INTO candles VALUES(?,?,?,?,?,?,?)', valid)

    def candles(self, symbol, now_ms=None, limit=1400):
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        with self.connection() as db:
            rows = db.execute('SELECT ts,o,h,l,c,v FROM candles WHERE symbol=? AND ts<=? ORDER BY ts DESC LIMIT ?',
                              (symbol, now_ms - BAR_MS, limit)).fetchall()
        return [list(row) for row in reversed(rows)]

    def quality(self, symbol, now_ms=None, required=1400):
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        end = now_ms // BAR_MS * BAR_MS
        expected = set(range(end - required * BAR_MS, end, BAR_MS))
        rows = self.candles(symbol, now_ms, required)
        present = {row[0] for row in rows}
        missing = sorted(expected - present)
        return dict(symbol=symbol, rows=len(expected & present), required=required,
                    missing=len(missing), first_missing=missing[0] if missing else None,
                    latest_ms=rows[-1][0] if rows else None,
                    ready=not missing, stale=not rows or rows[-1][0] < end - BAR_MS)

    def collect_candles(self, exchange, symbol, now_ms=None, required=1400):
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        # Repairs leading/internal gaps as well as the newest bars. Bounds API use.
        for _ in range(6):
            quality = self.quality(symbol, now_ms, required)
            if quality['ready']:
                return quality
            cursor = quality['first_missing']
            rows = exchange.fetch_ohlcv(symbol, '4h', since=cursor, limit=1000)
            self.put_candles(symbol, rows, now_ms)
            if self.quality(symbol, now_ms, required)['first_missing'] == cursor:
                raise ValueError(f'{symbol}: public candles made no progress at {cursor}')
        quality = self.quality(symbol, now_ms, required)
        if not quality['ready']:
            raise ValueError(f'{symbol}: {quality["missing"]} candles still missing')
        return quality

    def collect_funding(self, exchange, now_ms=None):
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        symbol = 'BTC/USDT:USDT'
        with self.connection() as db:
            last = db.execute('SELECT MAX(ts) FROM funding WHERE symbol=?', (symbol,)).fetchone()[0]
        cursor = last + 1 if last else now_ms - 30 * 86400000
        for _ in range(6):
            rows = exchange.fetch_funding_rate_history(symbol, since=cursor, limit=1000)
            valid = [(symbol, int(r['timestamp']), float(r['fundingRate'])) for r in rows
                     if cursor <= int(r['timestamp']) <= now_ms and math.isfinite(float(r['fundingRate']))]
            with self.connection() as db:
                db.executemany('INSERT OR IGNORE INTO funding VALUES(?,?,?)', valid)
            if not valid:
                break
            cursor = max(r[1] for r in valid) + 1
            if len(rows) < 1000:
                break
        with self.connection() as db:
            count, latest = db.execute('SELECT COUNT(*),MAX(ts) FROM funding').fetchone()
        if latest is None or now_ms - latest > 12 * 3600000:
            raise ValueError('funding history is stale or empty')
        return dict(rows=count, latest_ms=latest)

    def status(self, now=None):
        now = time.time() if now is None else now
        with self.connection() as db:
            worker = dict(db.execute('SELECT * FROM worker WHERE id=1').fetchone())
            jobs = [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY name')]
        worker['alive'] = bool(worker['owner'] and worker['expires'] > now and
                               worker['heartbeat'] and now - worker['heartbeat'] < 1800)
        for row in jobs:
            row['details'] = json.loads(row['details'])
        return dict(worker=worker, jobs=jobs, market=[self.quality(s, int(now * 1000)) for s in SYMBOLS])
