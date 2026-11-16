# Scrapy Request Context and Timeouts — Design

## Intent

Make opted-in Lightpanda requests preserve safe Scrapy request context and honor Scrapy's configured download timeout, while avoiding cross-origin credential disclosure and cache confusion.

## Goals and boundaries

- Run the Lightpanda middleware after Scrapy's request-preparation middleware but before HTTP cache middleware so prepared headers, proxy metadata, and `download_timeout` are available without mixing rendered and ordinary cache entries.
- Forward only `Accept`, `Accept-Language`, and `User-Agent`; do not forward cookies, authorization, `Referer`, or custom headers because Lightpanda applies CLI headers to every outgoing request, including cross-origin subrequests.
- Continue to require explicit per-request opt-in before forwarding a credentialed proxy URL; credentials are sent only to that proxy, not as origin headers.
- Convert Scrapy's per-request timeout (seconds) to Lightpanda's `http_timeout` (milliseconds), using the configured `DOWNLOAD_TIMEOUT` as a fallback.
- Keep unmarked requests on Scrapy's normal downloader and leave current GET-only behavior unchanged.
- Do not add browser reuse, concurrency control, new HTTP methods, or promise cancellation of a Lightpanda subprocess already running in a worker thread.

## Approaches considered

1. **Place Lightpanda after request preparation and before HTTP cache (chosen):** set priority to `800`, then pass safe prepared context into Lightpanda. This follows default header/cookie/proxy preparation while allowing rendered requests to bypass cache lookup and storage.
2. **Reconstruct request context at the current priority:** rejected because Scrapy's cookie and proxy middleware have not yet populated the request, and reproducing their behavior would duplicate Scrapy logic.

## Design calls

- Update example middleware priorities to `800` and document that the middleware runs after request preparation but before HTTP cache.
- Forward only `Accept` and `Accept-Language` as `http_header`; combine repeated values with commas because Lightpanda uses the last repeated `--http-header`. Map `User-Agent` to `user_agent`. Omit `Referer`, cookies, authorization, and all custom headers even when opt-in is set, since CLI headers apply to cross-origin subrequests.
- Map `User-Agent` to Lightpanda's dedicated `user_agent` option; send the other allowed headers as repeated `http_header` values because the CLI rejects `User-Agent` in `http_header`.
- `meta["lightpanda_allow_sensitive_headers"] is True` permits credentialed proxy URLs only; never forward sensitive or custom origin headers. Document subprocess argument visibility.
- Pass non-credentialed `request.meta["proxy"]` as `http_proxy`. Scrapy's `HttpProxyMiddleware` strips Basic credentials from that URL and places them in `Proxy-Authorization`; detect that form, require the same opt-in, and reconstruct a credentialed proxy URL for Lightpanda. Never forward `Proxy-Authorization` as an origin header. Reject unsupported proxy authorization schemes and credentialed proxy URLs without opt-in.
- Read `request.meta["download_timeout"]` when set, otherwise use `crawler.settings["DOWNLOAD_TIMEOUT"]`; pass the selected seconds value to Lightpanda as integer milliseconds in `http_timeout`.
- Mark opted-in requests `dont_cache` before Scrapy's cache middleware and choose a middleware priority after cookies/proxy/default headers (800) but before HTTP cache (900).
- Treat Lightpanda results with absent or zero HTTP status as `DownloadTimeoutError`, parse the CLI response header-entry list into Scrapy `Headers`, and use the final URL reported by Lightpanda.
- Fail closed when inherited proxy environment variables could contradict Scrapy's prepared proxy choice; do not mutate process-global environment from concurrent worker threads.
- Redact Lightpanda subprocess failures when credentialed proxy values were supplied. Reject non-ASCII forwarded header values instead of silently changing their bytes, preserve proxy credential bytes when reconstructing Basic auth, and round positive timeouts up to at least one millisecond.
- Convert Lightpanda's response-header entry list to Scrapy `Headers`, retaining repeated headers such as `Set-Cookie` while dropping body-encoding and length metadata that no longer describes serialized rendered HTML. Use Lightpanda's final URL.

## Constraints and limitation

Use documented `lightpanda-py` options (`http_header`, `http_proxy`, and `http_timeout`). Its HTTP timeout limits Lightpanda's network request, but `lightpanda-py` runs the browser using `subprocess.run` without a Python subprocess timeout; cancellation of `asyncio.to_thread` is not a guaranteed hard kill. Document that limitation rather than promising a hard wall-clock deadline.
