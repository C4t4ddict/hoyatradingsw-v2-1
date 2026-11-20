"""Bounded HTTPS requests for public news and translation sources."""

import http.client
import ipaddress
import socket
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, build_opener


MAX_FEED_BYTES = 4 * 1024 * 1024


def _validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.port not in (None, 443)):
        raise ValueError('Public feeds require HTTPS on port 443 without embedded credentials')
    return parsed.hostname.lower().removeprefix('www.')


def _connect_public(address, timeout, source_address):
    hostname, port = address
    addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    destinations = [entry[4][0] for entry in addresses]
    if not destinations or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast
                               for ip in destinations):
        raise OSError('Public feed hostname must resolve only to public addresses')
    last_error = None
    for ip in dict.fromkeys(destinations):
        try:
            # Connect to the address we checked, while retaining the hostname for TLS verification.
            return socket.create_connection((ip, port), timeout, source_address)
        except OSError as error:
            last_error = error
    raise last_error


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        return self.do_open(_PublicHTTPSConnection, request, context=self._context)


class _SamePublisherRedirect(HTTPRedirectHandler):
    max_redirections = 3

    def redirect_request(self, request, response, code, message, headers, new_url):
        if _validate_url(new_url) != _validate_url(request.full_url):
            raise ValueError('Cross-publisher feed redirect is disabled')
        return super().redirect_request(request, response, code, message, headers, new_url)


def open_public_request(request, *, timeout):
    _validate_url(request.full_url)
    opener = build_opener(ProxyHandler({}), _PublicHTTPSHandler(), _SamePublisherRedirect())
    return opener.open(request, timeout=timeout)


def read_public_body(response):
    payload = response.read(MAX_FEED_BYTES + 1)
    if len(payload) > MAX_FEED_BYTES:
        raise ValueError('Public feed exceeds the response size limit')
    return payload
