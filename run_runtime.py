"""Public-data scheduler. No training, credentials, or live-order calls."""
import argparse
import os
import time
import uuid

from dotenv import load_dotenv

from runtime_data import SYMBOLS
from runtime_evaluation import EvaluationStore


def collect_news(store):
    from market_intel import _iter_sources, _parse_source, SOURCE_TIMEOUT_SEC
    from ml_dataset import append_events
    from predict_model_bidirectional import predict_event_bidirectional, positive_probability

    def source_job(source):
        events = _parse_source(source, 12, min(SOURCE_TIMEOUT_SEC, 5))
        written = append_events(events)
        observed_ms = int(time.time() * 1000)
        for event in events:
            key = event.get('event_id')
            if not key:
                continue
            score = float(event.get('score', 0))
            for horizon in (4, 24):
                store.observe(key=key, kind='intel_shadow', symbol='BTC/USDT', observed_ms=observed_ms,
                              horizon=horizon, direction=1 if score >= 0 else -1,
                              score=score, source=source.name, now_ms=observed_ms)
            # This is shadow evaluation on a 4h execution grid, never an ML activation gate.
            for target, result in predict_event_bidirectional(event).items():
                if not result.get('ok') or not target.endswith(('_4h', '_24h')):
                    continue
                horizon = int(target.rsplit('_', 1)[1][:-1])
                version = result.get('validation', {}).get('trained_at', 'unknown')
                store.observe(key=f'{key}|{target}|{version}', kind='ml_shadow', symbol='BTC/USDT',
                              observed_ms=observed_ms, horizon=horizon,
                              direction=-1 if '_down_' in target else 1,
                              probability=positive_probability(result), source=f'{source.name}|{version}',
                              threshold=.015 if horizon == 4 else .025, now_ms=observed_ms)
        return dict(fetched=len(events), written=written,
                    source_url=source.url, transport=source.transport)

    for source in _iter_sources():
        store.run_job(f'news:{source.name}', lambda source=source: source_job(source), 300)


def cycle(store, owner):
    from exchange import get_exchange
    from signal_quality import SignalQualityStore
    if not store.lease(owner):
        return False
    if not store.status()['worker']['enabled']:
        return True
    spot = get_exchange(read_only=True, market_type='spot')
    swap = get_exchange(read_only=True, market_type='swap')
    spot.timeout = swap.timeout = 10000
    for symbol in SYMBOLS:
        store.run_job(f'candles:{symbol}', lambda symbol=symbol: store.collect_candles(spot, symbol), 60)
        if not store.lease(owner):
            return False
    store.run_job('funding:BTC', lambda: store.collect_funding(swap), 3600)
    collect_news(store)
    store.run_job('signals:settle', lambda: store.settle(
        SignalQualityStore(os.getenv('SIGNAL_QUALITY_PATH', 'data/signal_quality.sqlite3'))), 60)
    # Restart only a previously running paper session. A user pause is preserved.
    def paper_watchdog():
        from paper_live import load_state, get_audit_payload, resume_session
        state = load_state()
        if state.get('running') and not state.get('paused') and not get_audit_payload()['worker']['alive']:
            resume_session()
        return {'running_requested': bool(state.get('running'))}
    store.run_job('paper:watchdog', paper_watchdog, 60)
    store.lease(owner)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    load_dotenv()
    store, owner = EvaluationStore(), str(uuid.uuid4())
    try:
        while True:
            if not cycle(store, owner):
                print('Another runtime worker holds the lease.', flush=True)
                return
            if args.once:
                print(store.status(), flush=True)
                return
            time.sleep(10)
    finally:
        store.release(owner)


if __name__ == '__main__':
    main()
