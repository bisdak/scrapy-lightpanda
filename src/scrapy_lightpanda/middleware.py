"""Scrapy downloader middleware backed by Lightpanda's ephemeral browser."""

from __future__ import annotations

import asyncio
import base64
import binascii
import math
import os
from urllib.parse import quote_from_bytes, urlsplit, urlunsplit
from urllib.request import proxy_bypass

import lightpanda
from scrapy import Request, Spider
from scrapy.exceptions import NotSupported
from scrapy.http import Headers, HtmlResponse, Response
from twisted.internet.error import TimeoutError as TwistedTimeoutError

try:
    from scrapy.exceptions import DownloadTimeoutError
except ImportError:  # Scrapy < 2.20 uses Twisted timeout exceptions for retries.
    DownloadTimeoutError = TwistedTimeoutError


class LightpandaMiddleware:
    """Render requests marked with ``meta={"lightpanda": True}``."""

    _safe_headers = {"accept", "accept-language", "user-agent"}
    _sensitive_headers = {
        "authorization",
        "cookie",
        "proxy-authorization",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-access-token",
    }
    _proxy_environment = (
        "http_proxy",
        "HTTP_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
    )

    def __init__(self, default_download_timeout: float | None = None):
        self.default_download_timeout = default_download_timeout

    @classmethod
    def from_crawler(cls, crawler) -> LightpandaMiddleware:
        """Construct the middleware using Scrapy's downloader middleware API."""
        return cls(crawler.settings.getfloat("DOWNLOAD_TIMEOUT"))

    async def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> Response | None:
        """Fetch opted-in GET requests asynchronously from Scrapy's perspective."""
        if not request.meta.get("lightpanda"):
            return None
        if request.method != "GET":
            raise NotSupported("LightpandaMiddleware only supports opted-in GET requests")
        proxy = request.meta.get("proxy")
        allow_sensitive = request.meta.get("lightpanda_allow_sensitive_headers") is True
        proxy_authorization = request.headers.get(b"Proxy-Authorization")
        sensitive_origin_headers = self._sensitive_headers - {"proxy-authorization"}
        for name in request.headers:
            normalized_name = name.decode("latin-1").lower()
            if allow_sensitive and normalized_name in sensitive_origin_headers:
                raise NotSupported(
                    "Sensitive origin headers cannot be forwarded to Lightpanda; "
                    "Lightpanda applies CLI headers to cross-origin subrequests"
                )
        if proxy_authorization is not None and not allow_sensitive:
            raise NotSupported(
                "Credentialed Lightpanda proxies require "
                "meta['lightpanda_allow_sensitive_headers']=True"
            )
        if proxy and self._proxy_has_credentials(proxy) and not allow_sensitive:
            raise NotSupported(
                "Credentialed Lightpanda proxies require "
                "meta['lightpanda_allow_sensitive_headers']=True"
            )
        if proxy and proxy_authorization is not None:
            proxy = self._proxy_with_authorization(proxy, proxy_authorization)
        self._validate_proxy_environment(request.url, proxy)
        request.meta["dont_cache"] = True
        return await asyncio.to_thread(self._fetch_response, request, proxy)

    @classmethod
    def _validate_proxy_environment(cls, url: str, proxy: str | None) -> None:
        if proxy is None and any(os.environ.get(name) for name in cls._proxy_environment):
            raise NotSupported(
                "Lightpanda inherits proxy environment variables; clear them or "
                "set an explicit Scrapy proxy to avoid proxy environment conflicts"
            )
        if proxy is not None and proxy_bypass(urlsplit(url).hostname or ""):
            raise NotSupported(
                "The no_proxy environment bypasses this request's explicit Scrapy proxy"
            )

    @staticmethod
    def _proxy_has_credentials(proxy: str) -> bool:
        proxy_parts = urlsplit(proxy)
        return proxy_parts.username is not None or proxy_parts.password is not None

    @staticmethod
    def _proxy_with_authorization(proxy: str, proxy_authorization: bytes) -> str:
        try:
            scheme, encoded_credentials = proxy_authorization.split(None, 1)
            if scheme.lower() != b"basic":
                raise NotSupported("Only Basic proxy authorization is supported by Lightpanda")
            credentials = base64.b64decode(encoded_credentials, validate=True)
            username, password = credentials.split(b":", 1)
        except (ValueError, binascii.Error) as exc:
            raise NotSupported("Invalid Basic Proxy-Authorization header") from exc

        parts = urlsplit(proxy)
        user_info = f"{quote_from_bytes(username, safe='')}:{quote_from_bytes(password, safe='')}@"
        host_port = parts.netloc.rsplit("@", 1)[-1]
        return urlunsplit(
            (parts.scheme, user_info + host_port, parts.path, parts.query, parts.fragment)
        )

    def _fetch_response(self, request: Request, proxy: str | None) -> HtmlResponse:
        options: dict[str, str | int | list[str]] = {}
        wait_until = request.meta.get("lightpanda_wait_until")
        wait_selector = request.meta.get("lightpanda_wait_selector")
        if wait_until is not None:
            options["wait_until"] = wait_until
        if wait_selector is not None:
            options["wait_selector"] = wait_selector

        forwarded_headers: list[str] = []
        for name in request.headers:
            normalized_name = name.decode("latin-1").lower()
            if normalized_name in {"proxy-authorization", "referer"}:
                continue
            if normalized_name not in self._safe_headers:
                continue
            values = request.headers.getlist(name)
            if normalized_name == "user-agent":
                if values:
                    options["user_agent"] = self._decode_header_value(values[0])
                continue
            if values:
                header_values = [self._decode_header_value(value) for value in values]
                forwarded_headers.append(
                    f"{name.decode('ascii')}: {', '.join(header_values)}"
                )
        if forwarded_headers:
            options["http_header"] = forwarded_headers

        if proxy:
            options["http_proxy"] = proxy

        timeout = request.meta.get("download_timeout", self.default_download_timeout)
        if timeout is not None:
            timeout_ms = float(timeout) * 1000
            options["http_timeout"] = max(1, math.ceil(timeout_ms)) if timeout_ms > 0 else 0

        has_proxy_credentials = bool(proxy and self._proxy_has_credentials(proxy))
        try:
            result = lightpanda.fetch(request.url, json=True, **options).json()
        except Exception as exc:
            if has_proxy_credentials:
                raise RuntimeError(
                    "Lightpanda fetch failed while using a credentialed proxy; "
                    "error details redacted"
                ) from None
            if isinstance(exc, lightpanda.Error) and "OperationTimedout" in str(exc):
                raise DownloadTimeoutError("Lightpanda request timed out") from None
            raise

        content = result.get("content", "")
        body = content if isinstance(content, bytes) else str(content).encode("utf-8")
        status_value = result.get("http_status")
        if not status_value:
            raise DownloadTimeoutError("Lightpanda did not receive an HTTP response")
        status = int(status_value)
        headers = self._response_headers(result.get("headers"))

        return HtmlResponse(
            url=result.get("url") or request.url,
            status=status,
            headers=headers,
            body=body,
            encoding="utf-8",
            request=request,
        )

    @staticmethod
    def _decode_header_value(value: bytes) -> str:
        try:
            return value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise NotSupported(
                "Lightpanda CLI header values must be ASCII; non-ASCII bytes "
                "cannot be preserved through subprocess arguments"
            ) from exc

    @staticmethod
    def _response_headers(raw_headers) -> Headers:
        headers = Headers()
        if isinstance(raw_headers, dict):
            for name, value in raw_headers.items():
                values = value if isinstance(value, list) else [value]
                for item in values:
                    headers.appendlist(name, item)
        else:
            for header in raw_headers or []:
                headers.appendlist(header["name"], header["value"])
        for name in (b"Content-Encoding", b"Content-Length", b"Transfer-Encoding"):
            headers.pop(name, None)
        return headers
