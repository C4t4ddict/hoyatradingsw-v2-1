import asyncio
import io
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.main import app
from public_http import read_public_body
from webhook_server import _authorize_webhook


class SecurityBoundariesTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, method, path, **headers):
        sent = []
        request_consumed = asyncio.Event()

        async def receive():
            if request_consumed.is_set():
                await asyncio.Future()
            request_consumed.set()
            return {'type': 'http.request', 'body': b''}

        async def send(message):
            sent.append(message)

        request_headers = {'host': '127.0.0.1', **headers}
        await app({
            'type': 'http', 'asgi': {'spec_version': '2.4'}, 'path': path, 'scheme': 'http', 'method': method,
            'headers': [(key.lower().encode(), value.encode()) for key, value in request_headers.items()],
            'query_string': b'',
        }, receive, send)
        return sent[0]['status'], dict(sent[0]['headers']), b''.join(message['body'] for message in sent[1:])

    @patch('backend.app.routes.security.resolve_secret', return_value='fixture-token')
    @patch('backend.app.routes.paper.pause_paper', return_value={'paused': True})
    async def test_web_operator_authorization(self, pause, resolve):
        route = '/api/paper/pause'
        self.assertEqual((await self.request('POST', route))[0], 401)
        self.assertEqual((await self.request('POST', route, **{'X-Hoya-Desktop': 'fixture-token'}))[0], 401)
        pause.assert_not_called()
        status, headers, payload = await self.request('POST', route, **{'X-Settings-Token': 'fixture-token'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload), {'paused': True})
        self.assertEqual(headers[b'cache-control'], b'no-store')

    async def test_local_origin_and_host_policy(self):
        headers = {'Origin': 'http://127.0.0.1:3001', 'Access-Control-Request-Method': 'GET'}
        self.assertEqual((await self.request('OPTIONS', '/healthz', **headers))[0], 200)
        headers['Origin'] = 'https://example.invalid'
        _, refused, _ = await self.request('OPTIONS', '/healthz', **headers)
        self.assertNotIn(b'access-control-allow-origin', refused)
        self.assertEqual((await self.request('GET', '/healthz', host='example.invalid'))[0], 400)

    def test_legacy_rejects_unconfigured_token(self):
        with patch('webhook_server.WEBHOOK_TOKEN', ''):
            with self.assertRaises(HTTPException) as error:
                _authorize_webhook(None)
        self.assertEqual(error.exception.status_code, 503)

    def test_public_body_size_limit(self):
        with patch('public_http.MAX_FEED_BYTES', 2):
            self.assertEqual(read_public_body(io.BytesIO(b'ab')), b'ab')
            with self.assertRaises(ValueError):
                read_public_body(io.BytesIO(b'abc'))
