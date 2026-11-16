# Scrapy Request Context and Timeouts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Forward safe Scrapy request context and honor Scrapy download timeouts for requests rendered by Lightpanda, with explicit opt-in before secrets are sent through process arguments.

**Architecture:** Run the middleware after Scrapy request-preparation middleware but before cache middleware (priority `800`). Convert safe prepared headers, proxy metadata, and request timeout into Lightpanda options; never send credentials as global origin headers, and reserve `lightpanda_allow_sensitive_headers` for credentialed proxy URLs.

**Tech Stack:** Python 3.10+, Scrapy 2.11+, `lightpanda-py`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-scrapy-request-context-design.md`

## Global Constraints

- Forward only `Accept`, `Accept-Language`, and `User-Agent`; never forward `Referer`, cookies, authorization, or custom headers because Lightpanda applies CLI headers to cross-origin subrequests too.
- Require `meta["lightpanda_allow_sensitive_headers"] is True` to forward credentialed proxy URLs; do not forward sensitive origin headers even with opt-in.
- Fail clearly for a credentialed proxy without the sensitive-header opt-in; do not silently bypass it. Reconstruct Scrapy's stripped Basic proxy credentials from `Proxy-Authorization` only after opt-in; never pass that header as an origin header.
- Use `request.meta["download_timeout"]` when set; otherwise use Scrapy's `DOWNLOAD_TIMEOUT`; convert seconds to milliseconds for Lightpanda's `http_timeout`.
- Keep unmarked requests on Scrapy's normal downloader and preserve GET-only support.
- Keep `LightpandaMiddleware` after request preparation and before HTTP cache using priority `800` in examples and documentation; mark opted-in requests uncacheable.
- Document that subprocess arguments may be visible to same-user process inspection and that `http_timeout` is not a guaranteed process hard-kill.

## Review Focus

- Header names are matched case-insensitively; repeated `Accept` values combine safely and `User-Agent` uses Lightpanda's dedicated option (Task 1).
- Cookies, authorization, custom headers, and Referer never become global Lightpanda CLI headers, including with opt-in (review fix).
- Credentialed proxy URLs fail without opt-in, while an unauthenticated proxy is forwarded (Task 1).
- Per-request timeout overrides the global Scrapy timeout and seconds convert to milliseconds (Task 1).
- Middleware priorities remain after the built-in request-preparation middleware in both example spiders (Task 1).
- Rendered requests do not share HTTP-cache entries with ordinary requests (review fix).
- Real Lightpanda response headers and final URLs are represented correctly; zero status is retryable failure (review fixes).

---

### Task 1: Forward request context and timeout safely

**Files:**
- Modify: `src/scrapy_lightpanda/middleware.py`
- Modify: `tests/test_middleware.py`
- Modify: `tests/test_example.py`
- Modify: `README.md`
- Modify: `examples/spider.py`
- Modify: `examples/quotes_spider.py`

**Interfaces:**
- Consumes: Scrapy's prepared `Request.headers`, `Request.meta["proxy"]`, `Request.meta["download_timeout"]`, and crawler `DOWNLOAD_TIMEOUT` setting.
- Produces: `LightpandaMiddleware.from_crawler(crawler)` configured with default timeout; `process_request(request, spider=None)` forwards safe options to `lightpanda.fetch`.
- Sensitive opt-in: `request.meta["lightpanda_allow_sensitive_headers"] is True`.

- [x] **Step 1: Write failing middleware tests**

Add tests asserting that the case-insensitive allowlist combines repeated `Accept` values, maps `User-Agent` to Lightpanda's dedicated `user_agent` option, excludes `Referer`, cookies, authorization, and custom headers even with opt-in, and rejects sensitive origin headers when opt-in is set; `Proxy-Authorization` is not sent as an origin header; a credentialed proxy raises `NotSupported` without opt-in; Scrapy's stripped Basic proxy credentials are reconstructed into `http_proxy` only with opt-in, preserving Latin-1 bytes; an unauthenticated proxy maps to `http_proxy`; environment proxy conflicts fail closed; request timeout overrides the crawler default and rounds positive sub-millisecond values up; missing request timeout uses `DOWNLOAD_TIMEOUT`; zero/missing statuses become retryable timeout exceptions; Lightpanda network timeouts map to Scrapy retry exceptions; real-shaped response header entries preserve repeated `Set-Cookie` values, discard stale content encoding/length metadata, and use Lightpanda's final URL; credentialed-proxy failures are redacted; and rendered requests bypass cache.

- [x] **Step 2: Run the focused tests and verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_middleware.py -q`
Expected: FAIL because request headers, proxy, and timeout options are not currently mapped.

- [x] **Step 3: Implement safe context mapping**

Update `LightpandaMiddleware.from_crawler` to read `DOWNLOAD_TIMEOUT`. In `process_request`, validate sensitive headers and proxy environment, mark opted-in requests uncacheable, derive timeout from `request.meta["download_timeout"]` or the setting and round positive milliseconds up, then offload fetching. Forward only the safe allowlist, combine repeated list-valued `Accept` headers, and use `user_agent` for User-Agent. Forward `request.meta["proxy"]`; when Scrapy has split Basic proxy credentials into `Proxy-Authorization`, rebuild the proxy URL using percent-encoded raw bytes only if opt-in is true. Reject unsupported proxy authorization schemes and inherited proxy environment conflicts. Redact failures when credentials are in the proxy URL. Map Lightpanda's `OperationTimedout` errors and zero/missing HTTP statuses to Scrapy `DownloadTimeoutError`. Convert response header entries to Scrapy `Headers`, strip stale content-encoding/length metadata, and use the final result URL.

- [x] **Step 4: Run middleware tests**

Run: `./.venv/bin/python -m pytest tests/test_middleware.py -q`
Expected: PASS without browser or network access.

- [x] **Step 5: Update integration priorities and documentation**

Change the middleware priority to `800` in both example spiders and README configuration, after request preparation and before HTTP cache. Document the allowlist, proxy-only opt-in, proxy environment behavior, timeout conversion, cache behavior, Lightpanda User-Agent restriction, and subprocess-argument / hard-kill limitations. Add tests asserting both spider examples configure priority `800`.

- [x] **Step 6: Run the full standalone suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: all tests pass without launching Lightpanda or making network requests.
