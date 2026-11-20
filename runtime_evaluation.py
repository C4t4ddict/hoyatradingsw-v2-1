"""Point-in-time signal outcomes and paper campaign evidence (never live approval)."""
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from statistics import mean, pstdev

from runtime_data import BAR_MS, RuntimeStore


class EvaluationStore(RuntimeStore):
    def __init__(self, path=None):
        super().__init__(path)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, kind TEXT, symbol TEXT, observed_ms INTEGER,
                    horizon INTEGER, direction INTEGER, probability REAL, score REAL,
                    source TEXT, cost REAL, threshold REAL DEFAULT 0,
                    entry_ms INTEGER, exit_ms INTEGER, gross REAL, net REAL,
                    actual INTEGER, exported INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS paper_samples (
                    session TEXT, ts INTEGER, nav REAL, PRIMARY KEY(session,ts));
                CREATE TABLE IF NOT EXISTS paper_fills (
                    session TEXT, id TEXT, ts INTEGER, side TEXT, pnl REAL, fee REAL,
                    PRIMARY KEY(session,id));
                CREATE TABLE IF NOT EXISTS paper_daily (
                    session TEXT, day TEXT, payload TEXT, PRIMARY KEY(session,day));
            ''')

    def observe(self, *, key, kind, symbol, observed_ms, horizon=4, direction=1,
                probability=None, score=0, source='', cost=0.002, threshold=0, now_ms=None):
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        if horizon not in (4, 24) or direction not in (-1, 1) or observed_ms > now_ms or observed_ms < 0:
            raise ValueError('invalid signal time/horizon/direction')
        if not all(math.isfinite(float(x)) for x in (observed_ms, score, cost, threshold)) or cost < 0 or threshold < 0:
            raise ValueError('invalid signal values')
        if probability is not None and (not math.isfinite(probability) or not 0 <= probability <= 1):
            raise ValueError('invalid probability')
        identity = hashlib.sha256(f'{kind}|{key}|{symbol}|{horizon}|{direction}'.encode()).hexdigest()
        with self.connection() as db:
            return bool(db.execute('''INSERT OR IGNORE INTO observations
                (id,kind,symbol,observed_ms,horizon,direction,probability,score,source,cost,threshold)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (identity, kind, symbol, observed_ms, horizon, direction, probability, score, source, cost, threshold)).rowcount)

    def settle(self, quality_store, now_ms=None):
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        with self.connection() as db:
            rows = db.execute('SELECT * FROM observations WHERE net IS NULL ORDER BY observed_ms LIMIT 5000').fetchall()
            for row in rows:
                entry = math.ceil(row['observed_ms'] / BAR_MS) * BAR_MS
                exit_ms = entry + row['horizon'] * 3600000
                if exit_ms + BAR_MS > now_ms:
                    continue
                prices = db.execute('SELECT ts,o FROM candles WHERE symbol=? AND ts IN (?,?) ORDER BY ts',
                                    (row['symbol'], entry, exit_ms)).fetchall()
                if len(prices) != 2:
                    continue
                forward = prices[1]['o'] / prices[0]['o'] - 1
                gross = forward * row['direction']
                db.execute('UPDATE observations SET entry_ms=?,exit_ms=?,gross=?,net=?,actual=? WHERE id=? AND net IS NULL',
                           (entry, exit_ms, gross, gross - row['cost'], int(gross > row['threshold']), row['id']))
        # Crash between the two stores is safe: quality observation IDs are unique.
        with self.connection() as db:
            resolved = db.execute('SELECT * FROM observations WHERE net IS NOT NULL AND exported=0').fetchall()
        for row in resolved:
            if row['probability'] is not None:
                quality_store.record(signal_type=row['kind'], horizon=f'{row["horizon"]}h',
                                     predicted_probability=row['probability'], actual=row['actual'],
                                     signed_score=row['score'], forward_return=row['gross'],
                                     source=row['source'], observation_id=row['id'],
                                     occurred_at=datetime.fromtimestamp(row['exit_ms']/1000, timezone.utc).isoformat())
            with self.connection() as db:
                db.execute('UPDATE observations SET exported=1 WHERE id=?', (row['id'],))
        return self.signal_status()

    def signal_status(self):
        with self.connection() as db:
            totals = [dict(r) for r in db.execute('''SELECT kind,COUNT(*) total,
                SUM(net IS NULL) pending,SUM(net IS NOT NULL) resolved,AVG(net) mean_net_return
                FROM observations GROUP BY kind''')]
            recent = [dict(r) for r in db.execute('SELECT * FROM observations ORDER BY observed_ms DESC LIMIT 30')]
        return dict(totals=totals, recent=recent)

    def record_paper(self, state, fills, now_ms=None):
        session = state.get('session_id')
        if not session:
            return {}
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        decision = state.get('strategy_decision') or {}
        ts = decision.get('as_of_ms')
        nav = float((state.get('metrics') or {}).get('virtual_balance', 0))
        quality = decision.get('data_quality', {}).get('ok')
        with self.connection() as db:
            for fill in fills:
                if fill.get('status') == 'filled':
                    db.execute('INSERT OR IGNORE INTO paper_fills VALUES(?,?,?,?,?,?)',
                               (session, fill['order_id'], fill['execution_ms'], fill['side'],
                                fill.get('realized_pnl', 0), fill.get('fee', 0)))
            if quality and ts is not None and now_ms - BAR_MS * 2 < ts <= now_ms - BAR_MS and math.isfinite(nav) and nav > 0:
                db.execute('INSERT OR IGNORE INTO paper_samples VALUES(?,?,?)', (session, ts, nav))
        result = self.campaign(session)
        day = datetime.fromtimestamp(now_ms/1000, timezone.utc).date().isoformat()
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO paper_daily VALUES(?,?,?)', (session, day, json.dumps(result)))
        if quality and ts is not None:
            for symbol, signal in (decision.get('signals') or {}).items():
                for horizon in (4, 24):
                    self.observe(key=f'{session}|{ts}', kind='strategy_shadow', symbol=symbol,
                                 observed_ms=now_ms, horizon=horizon, score=signal.get('target_weight', 0),
                                 source=decision.get('strategy_version', ''),
                                 cost=2*(float(state.get('config', {}).get('fee_pct', .0005)) +
                                         float(state.get('config', {}).get('slippage_pct', .0005))), now_ms=now_ms)
        return result

    def campaign(self, session):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM paper_samples WHERE session=? ORDER BY ts', (session,)).fetchall()
            fills = db.execute('SELECT * FROM paper_fills WHERE session=? ORDER BY ts', (session,)).fetchall()
        returns = [b['nav']/a['nav'] - 1 for a,b in zip(rows, rows[1:]) if b['ts']-a['ts'] == BAR_MS]
        days = len(returns)/6
        peak, mdd = 0, 0
        for row in rows:
            peak = max(peak, row['nav'])
            mdd = max(mdd, 1 - row['nav']/peak)
        closed = [f for f in fills if f['side'] == 'sell']
        profits = sum(max(0, f['pnl']) for f in closed)
        losses = -sum(min(0, f['pnl']) for f in closed)
        return dict(session_id=session, observed_days=round(days, 3), target_days=28,
                    calendar_days=(rows[-1]['ts']-rows[0]['ts'])/86400000 if rows else 0,
                    gap_intervals=sum(max(0, (b['ts']-a['ts'])//BAR_MS - 1) for a,b in zip(rows, rows[1:])),
                    samples=len(rows), closed_trades=len(closed), target_trades=60, fills=len(fills),
                    fees=sum(f['fee'] for f in fills), realized_pnl=sum(f['pnl'] for f in closed),
                    return_pct=(rows[-1]['nav']/rows[0]['nav']-1)*100 if rows else None,
                    sharpe=mean(returns)/pstdev(returns)*math.sqrt(6*365) if len(returns)>1 and pstdev(returns)>0 else None,
                    max_drawdown_pct=mdd*100, profit_factor=profits/losses if losses else None,
                    status='ready_for_review' if days >= 28 and len(closed) >= 60 else 'collecting')

    def campaigns(self):
        with self.connection() as db:
            sessions = [r[0] for r in db.execute('SELECT session FROM paper_daily GROUP BY session ORDER BY MAX(day) DESC LIMIT 10')]
            daily = [dict(r) for r in db.execute('SELECT * FROM paper_daily ORDER BY day DESC LIMIT 30')]
        return dict(sessions=[self.campaign(s) for s in sessions], daily=[{**r,'payload':json.loads(r['payload'])} for r in daily])
