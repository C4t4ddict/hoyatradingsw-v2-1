import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import market_intel
from market_intel import Source, _parse_source
from news_sources import publisher_matches, treasury_entries
from run_runtime import collect_news
from runtime_evaluation import EvaluationStore


class Response:
    def __init__(self, payload):
        self.payload = payload.encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.payload


def rss(*items):
    return '<rss version="2.0"><channel><title>News</title>' + ''.join(items) + '</channel></rss>'


def article(source_url='https://www.reuters.com', link='https://news.google.com/rss/articles/123'):
    source = f'<source url="{source_url}">Reuters</source>' if source_url is not None else ''
    return f'<item><title>Bitcoin ETF approval</title><link>{link}</link><pubDate>Thu, 19 Nov 2026 00:00:00 GMT</pubDate>{source}</item>'


def release(url='/news/press-releases/sb9999/', title='Treasury sanctions crypto exchange', date='2026-11-18T12:00:00Z'):
    time = f'<span><time datetime="{date}">November 18</time></span>' if date is not None else ''
    return f'<div>{time}<h3 class="featured-stories__headline"><a href="{url}">{title}</a></h3></div>'


class SourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.reuters = next(s for s in market_intel.DEFAULT_SOURCES if s.name == 'Reuters Business')
        self.treasury = next(s for s in market_intel.DEFAULT_SOURCES if s.name == 'U.S. Treasury')

    def test_default_sources_replace_broken_endpoints_without_renaming_jobs(self):
        sources = {s.name:s for s in market_intel.DEFAULT_SOURCES}
        for name in ('Reuters Business', 'Reuters World'):
            self.assertTrue(sources[name].url.startswith('https://news.google.com/rss/search?'))
            self.assertEqual(sources[name].publisher_domain, 'reuters.com')
        self.assertEqual(self.treasury.transport, 'treasury_html')
        self.assertFalse(self.treasury.url.endswith('/rss'))

    def test_publisher_validation_rejects_missing_and_lookalike_hosts(self):
        for url in ('', None, 'http://reuters.com', 'https://reuters.com.evil.test',
                    'https://notreuters.com', 'https://reuters.com@evil.test',
                    'https://reuters.com:8080', 'https://[broken'):
            with self.subTest(url=url):
                self.assertFalse(publisher_matches(url, 'reuters.com'))
        self.assertTrue(publisher_matches('https://www.reuters.com', 'reuters.com'))

    def test_reuters_filter_precedes_limit_and_preserves_transport_metadata(self):
        payload = rss(article('https://other.test'), article(None), article())
        with patch('market_intel.urlopen', return_value=Response(payload)) as request:
            rows = _parse_source(self.reuters, 1, 1.25)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], 'Reuters Business')
        self.assertEqual(rows[0]['source_transport'], 'google_news_rss')
        self.assertEqual(rows[0]['publisher_url'], 'https://www.reuters.com')
        self.assertEqual(rows[0]['source_url'], self.reuters.url)
        self.assertEqual(rows[0]['published'], 'Thu, 19 Nov 2026 00:00:00 GMT')
        self.assertEqual(request.call_args.kwargs['timeout'], 1.25)

    def test_unverified_reuters_entries_are_not_scored(self):
        with patch('market_intel.urlopen', return_value=Response(rss(article(None), article('https://reuters.com.evil.test')))):
            self.assertEqual(_parse_source(self.reuters, 12, 1), [])

    def test_html_error_and_invalid_xml_are_failures_not_empty_success(self):
        for payload in ('<html><title>Access denied</title></html>', '<rss><broken'):
            with self.subTest(payload=payload), patch('market_intel.urlopen', return_value=Response(payload)):
                with self.assertRaises(ValueError):
                    _parse_source(Source('RSS','https://example.test','news',.7), 12, 1)

    def test_valid_empty_rss_and_regular_rss_remain_supported(self):
        src = Source('RSS','https://example.test','news',.7)
        with patch('market_intel.urlopen', return_value=Response(rss())):
            self.assertEqual(_parse_source(src, 12, 1), [])
        with patch('market_intel.urlopen', return_value=Response(rss(article(None)))):
            self.assertEqual(len(_parse_source(src, 12, 1)), 1)

    def test_treasury_dates_entities_links_and_dedup(self):
        html = '<main>' + release(title='Treasury <em>sanctions</em> crypto &amp; banks')*2 + '</main>'
        entries = treasury_entries(html.encode())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['title'], 'Treasury sanctions crypto & banks')
        self.assertEqual(entries[0]['published'], '2026-11-18T12:00:00Z')
        self.assertEqual(entries[0]['link'], 'https://home.treasury.gov/news/press-releases/sb9999')
        with patch('market_intel.urlopen', return_value=Response(html)):
            row = _parse_source(self.treasury, 12, 1)[0]
        self.assertEqual(row['source_transport'], 'treasury_html')
        self.assertEqual(row['kind'], 'official')
        self.assertNotEqual(row['event_time'], row['published'])

    def test_treasury_rejects_menu_external_links_and_date_leakage(self):
        html = release(url='/news/press-releases/menu/') + '<main>' + ''.join([
            release(), release(url='/news/press-releases/no-date/', date=None),
            release(url='https://evil.test/news/press-releases/evil/'),
            release(url='/news/press-releases/statements-remarks/'),
            release(url='/news/press-releases/bad-date/', date='yesterday'),
        ]) + '</main>'
        self.assertEqual(len(treasury_entries(html.encode())), 1)

    def test_treasury_markup_change_is_visible_failure(self):
        for html in ('<html>maintenance</html>', '<main>'+release(date=None)+'</main>'):
            with self.assertRaisesRegex(ValueError, 'listing not found'):
                treasury_entries(html.encode())

    def test_success_clears_existing_job_error_and_retains_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationStore(str(Path(directory)/'runtime.db'))
            name = 'news:Reuters Business'
            def fail():
                raise OSError('old DNS failure')
            store.run_job(name, fail, 300, now=1)
            with patch('market_intel._iter_sources', return_value=[self.reuters]), \
                 patch('market_intel.urlopen', return_value=Response(rss(article()))), \
                 patch('ml_dataset.append_events', return_value=1), \
                 patch('predict_model_bidirectional.predict_event_bidirectional', return_value={}):
                collect_news(store)
            job = next(j for j in store.status()['jobs'] if j['name']==name)
            self.assertIsNone(job['error'])
            self.assertEqual(job['failures'], 0)
            self.assertEqual(job['details']['fetched'], 1)
            self.assertEqual(job['details']['transport'], 'google_news_rss')
            self.assertEqual(job['details']['source_url'], self.reuters.url)
            self.assertEqual(store.signal_status()['totals'][0]['total'], 2)

    def test_bad_source_does_not_block_other_sources_or_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationStore(str(Path(directory)/'runtime.db'))
            with patch('market_intel._iter_sources', return_value=[self.reuters,self.treasury]), \
                 patch('market_intel.urlopen', side_effect=[OSError('offline'),Response('<main>'+release()+'</main>')]), \
                 patch('ml_dataset.append_events', return_value=1), \
                 patch('predict_model_bidirectional.predict_event_bidirectional', return_value={}):
                collect_news(store)
            jobs = {j['name']:j for j in store.status()['jobs']}
            self.assertIn('offline', jobs['news:Reuters Business']['error'])
            self.assertIsNone(jobs['news:U.S. Treasury']['error'])


if __name__ == '__main__':
    unittest.main()
