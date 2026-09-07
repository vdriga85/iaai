import socket

import pytest

from iaai.errors import IAAIError
from iaai.http_acquisition import PublicHTTPAcquisition
from iaai.source_urls import canonical_url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http://localhost/",
        "http://127.0.0.1",
        "http://[::1]",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://169.254.169.254",
        "http://224.0.0.1",
        "http://0.0.0.0",
        "http://[fc00::1]",
        "https://user:password@example.com",
        "https://example.com:8080",
        "http://example.com\\@localhost",
        "http://[::ffff:127.0.0.1]",
        "http://example.com\n",
    ],
)
def test_unsafe_urls(url):
    with pytest.raises(IAAIError):
        canonical_url(url)


class Response:
    def __init__(self, status=200, headers=None, body=b"<p>ok</p>"):
        self.status, self.headers, self.body = (
            status,
            headers or {"Content-Type": "text/html"},
            body,
        )
        self.offset = 0

    def read1(self, size, **kwargs):
        result = self.body[self.offset : self.offset + size]
        self.offset += len(result)
        return result

    def close(self):
        pass


def adapter(responses, ips=("93.184.215.14",)):
    calls = []

    class Pool:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def urlopen(self, *args, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

    def factory(ip, host, scheme, port, policy):
        assert ip == ips[0]
        return Pool()

    def resolver(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    return PublicHTTPAcquisition(resolver, factory), calls


def test_pinned_transport_no_auth(service):
    fetcher, calls = adapter([Response()])
    result = fetcher.fetch("https://example.com/", service.corpus.policy)
    assert result.status == "FETCHED"
    assert calls[0]["redirect"] is False and calls[0]["retries"] is False
    assert calls[0]["headers"]["Host"] == "example.com"
    assert "Cookie" not in calls[0]["headers"] and "Authorization" not in calls[0]["headers"]


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.1.1", "::1", "224.0.0.1"])
def test_dns_private_rejected(service, ip):
    fetcher, calls = adapter([Response()], (ip,))
    assert (
        fetcher.fetch("https://example.com", service.corpus.policy).status == "UNSAFE_DESTINATION"
    )
    assert not calls


def test_redirect_private_and_limit(service):
    fetcher, _ = adapter([Response(302, {"Location": "http://127.0.0.1/"})])
    assert fetcher.fetch("https://example.com", service.corpus.policy).status == "UNSAFE_URL"
    fetcher, _ = adapter([Response(302, {"Location": "/again"}) for _ in range(6)])
    assert fetcher.fetch("https://example.com", service.corpus.policy).status == "REDIRECT_LIMIT"


def test_oversize_response_and_encoding(service):
    policy = service.corpus.policy
    for response in (
        Response(body=b"x" * (policy.max_fetch_bytes + 1)),
        Response(headers={"Content-Length": str(policy.max_fetch_bytes + 1)}),
    ):
        fetcher, _ = adapter([response])
        result = fetcher.fetch("https://example.com", policy)
        assert result.status == "FETCH_TOO_LARGE" and result.body is None
    fetcher, _ = adapter([Response(headers={"Content-Encoding": "gzip"})])
    assert fetcher.fetch("https://example.com", policy).status == "UNSUPPORTED_ENCODING"


def test_safe_canonical_url():
    assert canonical_url("https://EXAMPLE.com:443/a?x=1#frag") == "https://example.com/a?x=1"


def test_redirect_dns_revalidated(service):
    fetcher, calls = adapter([Response(302, {"Location": "https://second.example/"})])

    def resolve(host, port, **kwargs):
        ip = "93.184.215.14" if host == "example.com" else "10.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    fetcher.resolver = resolve
    result = fetcher.fetch("https://example.com", service.corpus.policy)
    assert result.status == "UNSAFE_DESTINATION" and len(calls) == 1


def test_deadline_and_read_failure(service, monkeypatch):
    import iaai.http_acquisition as http

    times = iter([0, 1000])
    monkeypatch.setattr(http.time, "monotonic", lambda: next(times))
    fetcher, calls = adapter([Response()])
    assert fetcher.fetch("https://example.com", service.corpus.policy).status == "FETCH_TIMEOUT"
    assert not calls


def test_transport_tls_pins_hostname(service):
    pool = PublicHTTPAcquisition._pool(
        "93.184.215.14", "example.com", "https", 443, service.corpus.policy
    )
    assert pool.host == "93.184.215.14"
    assert pool.assert_hostname == "example.com"
    assert pool.conn_kw["server_hostname"] == "example.com"
    pool.close()
