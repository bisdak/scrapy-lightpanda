import asyncio
import base64
import inspect
import traceback
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scrapy import Request
from scrapy.exceptions import NotSupported

try:
    from scrapy_lightpanda import middleware
except ImportError:
    middleware = None


@pytest.fixture
def middleware_module():
    if middleware is None:
        pytest.skip("Lightpanda middleware has not been implemented")
    return middleware


def test_middleware_module_is_available():
    assert middleware is not None, "Lightpanda middleware has not been implemented"


def run_inline(function, *args, **kwargs):
    return function(*args, **kwargs)


async def await_result(result):
    return result


def patch_thread_offload(monkeypatch, middleware, offload):
    monkeypatch.setattr(middleware, "deferToThread", offload)
    monkeypatch.setattr(middleware, "maybe_deferred_to_future", await_result)


def run_request(middleware_instance, request):
    return asyncio.run(middleware_instance.process_request(request, spider=None))


def response_result(payload):
    return SimpleNamespace(json=Mock(return_value={"http_status": 200, **payload}))


def middleware_with_timeout(middleware_module, timeout):
    settings = Mock()
    settings.getfloat.return_value = timeout
    crawler = SimpleNamespace(settings=settings)
    return middleware_module.LightpandaMiddleware.from_crawler(crawler)


@pytest.mark.parametrize("meta", [{}, {"lightpanda": False}])
def test_unmarked_request_uses_normal_scrapy_downloader(monkeypatch, middleware_module, meta):
    middleware = middleware_module
    fetch = Mock()
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    mw = middleware.LightpandaMiddleware()

    result = run_request(mw, Request("https://example.com", meta=meta))

    assert result is None
    fetch.assert_not_called()


def test_opted_in_request_fetches_in_worker_and_returns_html_response(monkeypatch, middleware_module):
    middleware = middleware_module
    payload = {
        "content": "<html><h1>Rendered</h1></html>",
        "http_status": 201,
        "headers": {"Content-Type": "text/html; charset=utf-8", "X-Test": "yes"},
    }
    fetch = Mock(return_value=response_result(payload))
    offload = Mock(side_effect=run_inline)
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, offload)
    mw = middleware.LightpandaMiddleware()
    request = Request(
        "https://example.com/page",
        meta={
            "lightpanda": True,
            "lightpanda_wait_until": "networkidle",
            "lightpanda_wait_selector": "main",
        },
    )
    responses = []

    responses.append(run_request(mw, request))

    offload.assert_called_once()
    fetch.assert_called_once_with(
        "https://example.com/page",
        json=True,
        wait_until="networkidle",
        wait_selector="main",
    )
    response = responses[0]
    assert response.status == 201
    assert response.url == request.url
    assert response.request is request
    assert response.text == "<html><h1>Rendered</h1></html>"
    assert response.headers[b"Content-Type"] == b"text/html; charset=utf-8"
    assert response.headers[b"X-Test"] == b"yes"


@pytest.mark.parametrize("content", ["", "<p>café ☕</p>"])
def test_optional_response_fields_default_and_html_is_utf8(monkeypatch, content, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": content}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request("https://example.com", meta={"lightpanda": True})
    responses = []

    responses.append(run_request(middleware.LightpandaMiddleware(), request))

    response = responses[0]
    assert response.status == 200
    assert response.body == content.encode("utf-8")
    assert response.headers == {}


def test_opted_in_post_request_is_rejected_without_fetch(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock()
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    request = Request("https://example.com", method="POST", meta={"lightpanda": True})

    with pytest.raises(NotSupported, match="GET"):
        run_request(middleware.LightpandaMiddleware(), request)

    fetch.assert_not_called()


def test_fetch_exception_propagates_from_async_middleware(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(side_effect=RuntimeError("browser failed"))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request("https://example.com", meta={"lightpanda": True})

    with pytest.raises(RuntimeError, match="browser failed"):
        run_request(middleware.LightpandaMiddleware(), request)


def test_safe_headers_proxy_and_request_timeout_are_forwarded(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "ok"}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request(
        "https://example.com",
        headers={
            b"accept": [b"text/html", b"application/xhtml+xml"],
            b"Accept-Language": b"en-US",
            b"Referer": b"https://referrer.example/",
            b"User-Agent": b"scraper-test",
            b"Cookie": b"session=secret",
            b"Authorization": b"Bearer secret",
            b"X-API-Key": b"secret",
        },
        meta={
            "lightpanda": True,
            "proxy": "http://proxy.example:8080",
            "download_timeout": 2.5,
        },
    )

    run_request(middleware_with_timeout(middleware, 8), request)

    kwargs = fetch.call_args.kwargs
    assert kwargs["json"] is True
    assert {
        name.lower(): value
        for name, _, value in (
            header.partition(": ") for header in kwargs["http_header"]
        )
    } == {
        "accept": "text/html, application/xhtml+xml",
        "accept-language": "en-US",
    }
    assert kwargs["user_agent"] == "scraper-test"
    assert kwargs["http_proxy"] == "http://proxy.example:8080"
    assert kwargs["http_timeout"] == 2500


def test_sensitive_origin_headers_are_rejected_even_with_opt_in(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "ok"}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request(
        "https://example.com",
        headers={
            b"Authorization": b"Bearer secret",
            b"Cookie": b"session=secret",
            b"X-API-Key": b"secret",
            b"Proxy-Authorization": b"Basic dXNlcjpwYXNzd29yZA==",
        },
        meta={
            "lightpanda": True,
            "lightpanda_allow_sensitive_headers": True,
            "proxy": "http://proxy.example:8080",
        },
    )

    with pytest.raises(NotSupported, match="origin headers"):
        run_request(middleware_with_timeout(middleware, 8), request)

    fetch.assert_not_called()


def test_credentialed_proxy_requires_sensitive_opt_in(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "ok"}))
    offload = Mock(side_effect=run_inline)
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, offload)
    request = Request(
        "https://example.com",
        meta={"lightpanda": True, "proxy": "http://user:password@proxy.example:8080"},
    )

    with pytest.raises(NotSupported, match="lightpanda_allow_sensitive_headers"):
        run_request(middleware_with_timeout(middleware, 8), request)

    offload.assert_not_called()
    fetch.assert_not_called()


def test_scrapy_proxy_authorization_requires_sensitive_opt_in(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "ok"}))
    offload = Mock(side_effect=run_inline)
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, offload)
    request = Request(
        "https://example.com",
        headers={b"Proxy-Authorization": b"Basic dXNlcjpwYXNzd29yZA=="},
        meta={"lightpanda": True, "proxy": "http://proxy.example:8080"},
    )

    with pytest.raises(NotSupported, match="lightpanda_allow_sensitive_headers"):
        run_request(middleware_with_timeout(middleware, 8), request)

    fetch.assert_not_called()


def test_crawler_download_timeout_is_used_when_request_has_no_override(
    monkeypatch, middleware_module
):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "ok"}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request("https://example.com", meta={"lightpanda": True})

    run_request(middleware_with_timeout(middleware, 6.75), request)

    assert fetch.call_args.kwargs["http_timeout"] == 6750


def test_positive_submillisecond_timeout_rounds_up(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "ok"}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request(
        "https://example.com",
        meta={"lightpanda": True, "download_timeout": 0.0005},
    )

    run_request(middleware.LightpandaMiddleware(), request)

    assert fetch.call_args.kwargs["http_timeout"] == 1


def test_non_ascii_forwarded_header_is_rejected(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock()
    offload = Mock(side_effect=run_inline)
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, offload)
    request = Request(
        "https://example.com",
        headers={b"Accept": "café".encode("utf-8")},
        meta={"lightpanda": True},
    )

    with pytest.raises(NotSupported, match="non-ASCII"):
        run_request(middleware.LightpandaMiddleware(), request)

    offload.assert_called_once()
    fetch.assert_not_called()


def test_lightpanda_headers_and_final_url_are_converted(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(
        return_value=response_result(
            {
                "content": "ok",
                "http_status": 200,
                "url": "https://example.com/new/index",
                "headers": [
                    {"name": "Content-Type", "value": "text/html"},
                    {"name": "Content-Encoding", "value": "br"},
                    {"name": "Content-Length", "value": "12345"},
                    {"name": "Set-Cookie", "value": "a=1; Path=/"},
                    {"name": "Set-Cookie", "value": "b=2; Path=/"},
                ],
            }
        )
    )
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request("https://example.com/old", meta={"lightpanda": True})

    response = run_request(middleware.LightpandaMiddleware(), request)

    assert response.url == "https://example.com/new/index"
    assert response.request is request
    assert response.headers.getlist(b"Set-Cookie") == [b"a=1; Path=/", b"b=2; Path=/"]
    assert response.headers[b"Content-Type"] == b"text/html"
    assert b"Content-Encoding" not in response.headers
    assert b"Content-Length" not in response.headers


def test_zero_http_status_becomes_retryable_download_timeout(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "", "http_status": 0}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request("https://example.com", meta={"lightpanda": True})

    with pytest.raises(middleware.DownloadTimeoutError):
        run_request(middleware.LightpandaMiddleware(), request)


def test_lightpanda_network_timeout_is_mapped_to_scrapy_retry_exception(
    monkeypatch, middleware_module
):
    middleware = middleware_module
    fetch = Mock(side_effect=middleware.lightpanda.Error('err="OperationTimedout"', 1))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request("https://example.com", meta={"lightpanda": True})

    with pytest.raises(middleware.DownloadTimeoutError, match="Lightpanda request timed out"):
        run_request(middleware.LightpandaMiddleware(), request)


def test_missing_http_status_becomes_retryable_download_timeout(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "" , "http_status": None}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request("https://example.com", meta={"lightpanda": True})

    with pytest.raises(middleware.DownloadTimeoutError):
        run_request(middleware.LightpandaMiddleware(), request)


def test_proxy_environment_conflict_fails_closed(monkeypatch, middleware_module):
    middleware = middleware_module
    monkeypatch.setenv("http_proxy", "http://unintended-proxy.example:8080")
    fetch = Mock()
    offload = Mock(side_effect=run_inline)
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, offload)
    request = Request(
        "https://example.com",
        meta={"lightpanda": True, "proxy": None},
    )

    with pytest.raises(NotSupported, match="proxy environment"):
        run_request(middleware.LightpandaMiddleware(), request)

    offload.assert_not_called()
    fetch.assert_not_called()


def test_no_proxy_cannot_silently_bypass_explicit_scrapy_proxy(
    monkeypatch, middleware_module
):
    middleware = middleware_module
    monkeypatch.setenv("no_proxy", "example.com")
    fetch = Mock()
    offload = Mock(side_effect=run_inline)
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, offload)
    request = Request(
        "https://example.com",
        meta={"lightpanda": True, "proxy": "http://scrapy-proxy.example:8080"},
    )

    with pytest.raises(NotSupported, match="no_proxy environment"):
        run_request(middleware.LightpandaMiddleware(), request)

    offload.assert_not_called()
    fetch.assert_not_called()


def test_credentialed_proxy_basic_bytes_support_latin1(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "ok"}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    credentials = "usér:päss".encode("latin-1")
    auth = b"Basic " + base64.b64encode(credentials)
    request = Request(
        "https://example.com",
        headers={b"Proxy-Authorization": auth},
        meta={
            "lightpanda": True,
            "lightpanda_allow_sensitive_headers": True,
            "proxy": "http://proxy.example:8080",
        },
    )

    run_request(middleware.LightpandaMiddleware(), request)

    assert fetch.call_args.kwargs["http_proxy"] == "http://us%E9r:p%E4ss@proxy.example:8080"


def test_credentialed_proxy_errors_do_not_expose_credentials(monkeypatch, middleware_module):
    middleware = middleware_module
    secret_proxy = "http://user:topsecret@proxy.example:8080"
    fetch = Mock(side_effect=RuntimeError(f"failed command: --http-proxy {secret_proxy}"))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request(
        "https://example.com",
        meta={
            "lightpanda": True,
            "lightpanda_allow_sensitive_headers": True,
            "proxy": secret_proxy,
        },
    )

    with pytest.raises(RuntimeError) as error:
        run_request(middleware.LightpandaMiddleware(), request)

    assert "topsecret" not in "".join(traceback.format_exception(error.value))


def test_lightpanda_request_is_not_cached(monkeypatch, middleware_module):
    middleware = middleware_module
    fetch = Mock(return_value=response_result({"content": "ok"}))
    monkeypatch.setattr(middleware.lightpanda, "fetch", fetch)
    patch_thread_offload(monkeypatch, middleware, run_inline)
    request = Request("https://example.com", meta={"lightpanda": True})

    run_request(middleware.LightpandaMiddleware(), request)

    assert request.meta["dont_cache"] is True


def test_from_crawler_constructs_middleware(middleware_module):
    middleware = middleware_module
    middleware_instance = middleware_with_timeout(middleware, 8)

    assert isinstance(middleware_instance, middleware.LightpandaMiddleware)


def test_process_request_spider_argument_is_optional(middleware_module):
    parameter = inspect.signature(middleware_module.LightpandaMiddleware.process_request).parameters[
        "spider"
    ]

    assert parameter.default is None


def test_process_request_is_a_coroutine(middleware_module):
    assert inspect.iscoroutinefunction(middleware_module.LightpandaMiddleware.process_request)
