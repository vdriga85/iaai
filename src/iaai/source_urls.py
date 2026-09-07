"""Conservative URL identity, with no DNS or HTTP implementation."""

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

from iaai.errors import IAAIError


def canonical_url(url: str) -> str:
    try:
        if not url or any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url:
            raise ValueError
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if "%" in host:
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
            if not public_address(str(address)):
                raise ValueError
            host = f"[{address}]" if address.version == 6 else str(address)
        except ValueError:
            if ":" in host or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host):
                raise ValueError from None
            if host.endswith((".localhost", ".local", ".internal")):
                raise ValueError
            # Numeric private literals must not escape through hostname parsing.
            if re.fullmatch(r"[0-9.]+", host):
                raise ValueError
        port = parsed.port
        if port is not None and port != (443 if parsed.scheme == "https" else 80):
            raise ValueError  # Step 2 accepts standard web ports only.
        return urlunsplit((parsed.scheme, host, parsed.path or "/", parsed.query, ""))
    except (ValueError, UnicodeError) as exc:
        raise IAAIError(
            "UNSAFE_URL", "Требуется публичный HTTP(S) URL без пароля и нестандартного порта."
        ) from exc


def public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (
        ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
        and not ip.is_loopback
        and not ip.is_link_local
        and not getattr(ip, "ipv4_mapped", None)
        and not (ip.version == 6 and (ip.sixtofour or ip.teredo))
    )
