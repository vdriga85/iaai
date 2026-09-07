"""Public HTTP only. Pin validated DNS answers; never reuse browser/proxy credentials."""

import socket
import ssl
import time
from email.message import Message
from urllib.parse import urljoin, urlsplit

import urllib3

from iaai.corpus_ports import FetchResult
from iaai.errors import IAAIError
from iaai.source_urls import canonical_url, public_address


class PublicHTTPAcquisition:
    version = "urllib3-public-pinned-v1"

    def __init__(self, resolver=socket.getaddrinfo, pool_factory=None):
        self.resolver = resolver
        self.pool_factory = pool_factory or self._pool

    @staticmethod
    def _pool(ip, host, scheme, port, policy):
        options = {
            "host": ip,
            "port": port,
            "retries": False,
            "timeout": urllib3.Timeout(
                connect=policy.connect_timeout_seconds, read=policy.read_timeout_seconds
            ),
        }
        if scheme == "https":
            return urllib3.HTTPSConnectionPool(
                **options,
                server_hostname=host,
                assert_hostname=host,
                ssl_context=ssl.create_default_context(),
            )
        return urllib3.HTTPConnectionPool(**options)

    def fetch(self, url, policy):
        requested = canonical_url(url)
        current, chain = requested, []
        status, media, charset, http_status, count = "FETCH_FAILED", None, None, None, 0
        deadline = time.monotonic() + policy.fetch_deadline_seconds
        try:
            for redirect_number in range(policy.max_redirects + 1):
                current = canonical_url(current)
                parsed = urlsplit(current)
                host, port = (
                    parsed.hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                )
                addresses = sorted(
                    {item[4][0] for item in self.resolver(host, port, type=socket.SOCK_STREAM)}
                )
                if not addresses or not all(public_address(ip) for ip in addresses):
                    raise IAAIError(
                        "UNSAFE_DESTINATION", "Непубличный адрес назначения заблокирован."
                    )
                if time.monotonic() >= deadline:
                    raise IAAIError("FETCH_TIMEOUT", "Истёк срок загрузки.")
                # Connection uses this exact numeric IP, no second hostname DNS lookup.
                with self.pool_factory(addresses[0], host, parsed.scheme, port, policy) as pool:
                    response = pool.urlopen(
                        "GET",
                        parsed.path + ("?" + parsed.query if parsed.query else ""),
                        headers={
                            "Host": parsed.netloc,
                            "User-Agent": "IAAI/0.2 public-source-import",
                            "Accept": "text/html,application/xhtml+xml",
                            "Accept-Encoding": "identity",
                        },
                        redirect=False,
                        retries=False,
                        preload_content=False,
                        decode_content=False,
                        assert_same_host=False,
                    )
                    try:
                        http_status = response.status
                        if http_status in (301, 302, 303, 307, 308):
                            if redirect_number == policy.max_redirects:
                                raise IAAIError("REDIRECT_LIMIT", "Слишком много перенаправлений.")
                            location = response.headers.get("Location")
                            if not location:
                                raise IAAIError("INVALID_REDIRECT", "Нет адреса перенаправления.")
                            chain.append(current)
                            current = canonical_url(urljoin(current, location))
                            continue
                        header = Message()
                        header["content-type"] = response.headers.get(
                            "Content-Type", "application/octet-stream"
                        )
                        media, charset = header.get_content_type(), header.get_content_charset()
                        if (
                            response.headers.get("Content-Encoding", "identity").lower()
                            != "identity"
                        ):
                            raise IAAIError(
                                "UNSUPPORTED_ENCODING", "Сжатый ответ не поддерживается."
                            )
                        length = response.headers.get("Content-Length")
                        if length and int(length) > policy.max_fetch_bytes:
                            raise IAAIError("FETCH_TOO_LARGE", "Ответ превышает лимит размера.")
                        pieces = []
                        while True:
                            if time.monotonic() >= deadline:
                                raise IAAIError("FETCH_TIMEOUT", "Истёк срок загрузки.")
                            piece = response.read1(
                                min(65536, policy.max_fetch_bytes - count + 1), decode_content=False
                            )
                            if not piece:
                                break
                            count += len(piece)
                            if count > policy.max_fetch_bytes:
                                raise IAAIError("FETCH_TOO_LARGE", "Ответ превышает лимит размера.")
                            pieces.append(piece)
                        status = (
                            "HTTP_ERROR"
                            if not 200 <= http_status < 300
                            else "UNSUPPORTED_MEDIA_TYPE"
                            if media not in policy.supported_media_types
                            else "FETCHED"
                        )
                        return FetchResult(
                            requested,
                            current,
                            tuple(chain),
                            http_status,
                            media,
                            charset,
                            b"".join(pieces),
                            count,
                            status,
                            (),
                            self.version,
                        )
                    finally:
                        response.close()
        except IAAIError as exc:
            status = exc.code
        except (OSError, urllib3.exceptions.HTTPError, ValueError):
            status = "NETWORK_ERROR"
        return FetchResult(
            requested,
            current,
            tuple(chain),
            http_status,
            media,
            charset,
            None,
            count,
            status,
            (status,),
            self.version,
        )
