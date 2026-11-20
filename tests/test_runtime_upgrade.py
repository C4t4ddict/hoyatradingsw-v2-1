import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException

from runtime_data import BAR_MS, RuntimeStore
from runtime_evaluation import EvaluationStore
from signal_quality import SignalQualityStore
from paper_engine import EventDrivenPaperEngine, FOUR_HOURS_MS
from paper_ledger import TradingLedger


def candle(ts, price=100):
    return [ts, price, price+1, price-1, price, 10]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'runtime.db')
        self.store = EvaluationStore(self.path)
        self.quality = SignalQualityStore(str(Path(self.tmp.name) / 'quality.db'))

    def test_gap_repair_and_completed_only(self):
        self.store.put_candles('BTC/USDT', [candle(0), candle(2*BAR_MS)], 4*BAR_MS)
        exchange = Mock()
        exchange.fetch_ohlcv.return_value = [candle(i*BAR_MS) for i in range(1,5)]
        result = self.store.collect_candles(exchange, 'BTC/USDT', 4*BAR_MS, required=4)
        self.assertTrue(result['ready'])
        self.assertEqual(exchange.fetch_ohlcv.call_args.kwargs['since'], BAR_MS)
        self.assertEqual(len(self.store.candles('BTC/USDT', 4*BAR_MS)), 4)
        self.store.collect_candles(exchange, 'BTC/USDT', 4*BAR_MS, required=4)
        self.assertEqual(exchange.fetch_ohlcv.call_count, 1)

    def test_paginated_bootstrap(self):
        exchange = Mock()
        def fetch(symbol, tf, since, limit):
            return [candle(i*BAR_MS) for i in range(since//BAR_MS, min(1400, since//BAR_MS+limit))]
        exchange.fetch_ohlcv.side_effect = fetch
        self.assertTrue(self.store.collect_candles(exchange, 'BTC/USDT', 1400*BAR_MS)['ready'])
        self.assertEqual(exchange.fetch_ohlcv.call_count, 2)

    def test_bad_rows_do_not_replace_good_cache(self):
        self.store.put_candles('BTC/USDT', [candle(0)], BAR_MS)
        for bad in ([0,float('nan'),101,99,100,10], [0,100,90,99,100,10], [1,100,101,99,100,10]):
            with self.assertRaises(ValueError):
                self.store.put_candles('BTC/USDT', [bad], BAR_MS)
        self.assertEqual(self.store.candles('BTC/USDT', BAR_MS)[0][1], 100)

    def test_no_progress_reports_failure(self):
        exchange = Mock()
        exchange.fetch_ohlcv.return_value = []
        with self.assertRaisesRegex(ValueError, 'no progress'):
            self.store.collect_candles(exchange, 'BTC/USDT', 4*BAR_MS, required=4)

    def test_staleness_advances_without_new_write(self):
        self.store.put_candles('BTC/USDT', [candle(0)], BAR_MS)
        self.assertTrue(self.store.quality('BTC/USDT', BAR_MS, 1)['ready'])
        self.assertTrue(self.store.quality('BTC/USDT', 2*BAR_MS, 1)['stale'])

    def test_retry_is_persistent_and_independent(self):
        fail = Mock(side_effect=RuntimeError('offline'))
        self.store.run_job('one', fail, 60, now=100)
        self.store.run_job('one', fail, 60, now=110)
        self.assertEqual(fail.call_count, 1)
        restarted = RuntimeStore(self.path)
        restarted.run_job('two', lambda: {'ok':True}, 60, now=110)
        restarted.control('retry')
        restarted.run_job('one', lambda: {'recovered':True}, 60, now=111)
        rows = {r['name']:r for r in restarted.status(now=111)['jobs']}
        self.assertIsNone(rows['one']['error'])
        self.assertEqual(rows['one']['failures'], 0)
        self.assertEqual(rows['two']['succeeded'], 110)

    def test_worker_lease_owner_and_expiry(self):
        self.assertTrue(self.store.lease('one', now=10, seconds=60))
        self.assertFalse(RuntimeStore(self.path).lease('two', now=11))
        self.store.release('two')
        self.assertFalse(self.store.lease('two', now=12))
        self.assertTrue(self.store.lease('two', now=71))
        self.store.control('pause')
        self.assertFalse(self.store.status(now=72)['worker']['enabled'])

    def test_funding_stale_and_dedup(self):
        exchange = Mock()
        exchange.fetch_funding_rate_history.return_value = [{'timestamp':BAR_MS,'fundingRate':.001}]*2
        self.assertEqual(self.store.collect_funding(exchange, BAR_MS)['rows'], 1)
        exchange.fetch_funding_rate_history.return_value = []
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.store.collect_funding(exchange, 10*BAR_MS)

    def observe(self, **kwargs):
        return self.store.observe(key='prediction-v1',kind='ml_shadow',symbol='BTC/USDT',
                                  observed_ms=1,probability=.7,now_ms=1,**kwargs)

    def test_future_signal_rejected(self):
        with self.assertRaises(ValueError):
            self.store.observe(key='x',kind='intel_shadow',symbol='BTC/USDT',observed_ms=2,now_ms=1)

    def test_outcome_maturity_exact_prices_cost_and_idempotence(self):
        self.assertTrue(self.observe(cost=.002))
        self.assertFalse(self.observe(cost=.5))
        self.store.put_candles('BTC/USDT', [candle(BAR_MS,100),candle(2*BAR_MS,110)], 3*BAR_MS)
        self.store.settle(self.quality, now_ms=3*BAR_MS-1)
        self.assertEqual(self.store.signal_status()['totals'][0]['pending'], 1)
        self.store.settle(self.quality, now_ms=3*BAR_MS)
        row = self.store.signal_status()['recent'][0]
        self.assertAlmostEqual(row['net'], .098)
        self.store.settle(self.quality, now_ms=4*BAR_MS)
        self.assertEqual(self.quality.summary('ml_shadow')['observations'], 1)
        self.assertEqual(self.quality.summary('ml')['observations'], 0)

    def test_missing_exact_entry_is_not_silently_shifted(self):
        self.observe()
        self.store.put_candles('BTC/USDT', [candle(2*BAR_MS),candle(3*BAR_MS)], 4*BAR_MS)
        self.store.settle(self.quality, now_ms=4*BAR_MS)
        self.assertEqual(self.store.signal_status()['totals'][0]['pending'], 1)

    def test_down_direction_and_threshold(self):
        self.observe(direction=-1, threshold=.15)
        self.store.put_candles('BTC/USDT', [candle(BAR_MS,100),candle(2*BAR_MS,90)], 3*BAR_MS)
        self.store.settle(self.quality, now_ms=3*BAR_MS)
        row = self.store.signal_status()['recent'][0]
        self.assertEqual(row['actual'], 0)
        self.assertAlmostEqual(row['gross'], .1)

    def paper(self, ts, nav=1000):
        return {'session_id':'paper-one','metrics':{'virtual_balance':nav},
                'strategy_decision':{'as_of_ms':ts,'data_quality':{'ok':True}}}

    def test_campaign_needs_observed_time_and_closed_trades(self):
        fills = [dict(status='filled',order_id=str(i),execution_ms=i,side='buy',fee=.1) for i in range(250)]
        self.store.record_paper(self.paper(0), fills, now_ms=BAR_MS)
        self.store.record_paper(self.paper(200*BAR_MS), fills, now_ms=201*BAR_MS)
        result = self.store.campaign('paper-one')
        self.assertEqual(result['fills'], 250)
        self.assertEqual(result['closed_trades'], 0)
        self.assertEqual(result['observed_days'], 0)
        self.assertEqual(result['gap_intervals'], 199)
        self.assertEqual(result['status'], 'collecting')
        self.assertEqual(self.store.campaign('other')['samples'], 0)

    def test_campaign_daily_persistence_costs_and_no_duplicate_samples(self):
        fills = [dict(status='filled',order_id='closed',execution_ms=BAR_MS,side='sell',realized_pnl=-2,fee=.1)]
        self.store.record_paper(self.paper(0), [], now_ms=BAR_MS)
        self.store.record_paper(self.paper(BAR_MS,998), fills, now_ms=2*BAR_MS)
        self.store.record_paper(self.paper(BAR_MS,998), fills, now_ms=2*BAR_MS)
        result = EvaluationStore(self.path).campaign('paper-one')
        self.assertEqual(result['samples'], 2)
        self.assertEqual(result['closed_trades'], 1)
        self.assertAlmostEqual(result['max_drawdown_pct'], .2)
        self.assertEqual(result['profit_factor'], 0)
        self.assertTrue(self.store.campaigns()['daily'])

    def test_paper_hold_preserves_nav_and_positions(self):
        import paper_live
        state = self.paper(0)
        state.update(config={'initial_usdt':1000},running=True,
                     event_engine={'portfolio':{'initial_cash':1000,'cash':0,'units':{'BTC/USDT':1},'equity_peak':1000}})
        with patch('paper_live._paper_candles', return_value=[]), \
             patch('paper_live.LEDGER_PATH', str(Path(self.tmp.name)/'ledger.db')), \
             patch('paper_live._persist_session_snapshot'), patch('paper_live._release_lock'):
            result = paper_live._update_vol_target_session(state,state['config'],str(Path(self.tmp.name)/'state.json'))
        self.assertEqual(result['metrics']['virtual_balance'], 1000)
        self.assertEqual(result['event_engine']['portfolio']['units']['BTC/USDT'], 1)
        self.assertEqual(result['fallback_mode'], 'data_quality_hold')

    def test_expired_pending_order_does_not_fill_late(self):
        ledger = TradingLedger(str(Path(self.tmp.name)/'ledger.db'))
        engine = EventDrivenPaperEngine(session_id='one', initial_cash=1000, ledger=ledger)
        engine.pending_orders = [dict(order_id='one',symbol='BTC/USDT',side='buy',execute_after_ms=BAR_MS,notional=100)]
        self.assertEqual(engine.on_bar_open(timestamp_ms=2*BAR_MS,open_prices={'BTC/USDT':100}), [])
        self.assertEqual(engine.portfolio.cash, 1000)
        self.assertEqual(engine.pending_orders, [])
        self.assertEqual(ledger.list_events()[0]['event_type'], 'order_expired')

    def test_daily_loss_counter_resets_and_persists(self):
        engine = EventDrivenPaperEngine(session_id='one',initial_cash=1000,ledger=TradingLedger(str(Path(self.tmp.name)/'ledger.db')))
        engine.portfolio.daily_realized_pnl = -20
        engine.pnl_day = '1970-01-01'
        engine.on_bar_open(timestamp_ms=BAR_MS,open_prices={})
        self.assertEqual(engine.portfolio.daily_realized_pnl, -20)
        engine.on_bar_open(timestamp_ms=86400000,open_prices={})
        self.assertEqual(engine.portfolio.daily_realized_pnl, 0)
        self.assertEqual(engine.snapshot()['pnl_day'], '1970-01-02')

    def test_settings_auth_on_mutation(self):
        from backend.app.routes.runtime import runtime_control, RuntimeControl
        with patch('backend.app.routes.security.resolve_secret',return_value='expected'):
            with self.assertRaises(HTTPException) as caught:
                runtime_control(RuntimeControl(action='pause'),x_settings_token='wrong')
            self.assertEqual(caught.exception.status_code, 401)
        self.assertTrue(self.store.status()['worker']['enabled'])

    def test_windows_health_query_closes_handle_without_signalling(self):
        import paper_live
        kernel = Mock()
        kernel.OpenProcess.return_value = 42
        def exit_code(handle, code):
            code._obj.value = 259
            return True
        kernel.GetExitCodeProcess.side_effect = exit_code
        with patch('ctypes.WinDLL', return_value=kernel, create=True), patch('os.kill') as kill:
            self.assertTrue(paper_live._windows_pid_alive(123))
        kernel.OpenProcess.assert_called_once_with(0x1000, False, 123)
        kernel.CloseHandle.assert_called_once_with(42)
        kill.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows process liveness regression')
    def test_health_check_does_not_terminate_real_windows_process(self):
        import paper_live
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertTrue(paper_live._is_pid_alive(child.pid))
            self.assertTrue(paper_live._is_pid_alive(child.pid))
            self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
