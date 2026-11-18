# scrapy-lightpanda

[![CI](https://github.com/bisdak/scrapy-lightpanda/actions/workflows/ci.yml/badge.svg)](https://github.com/bisdak/scrapy-lightpanda/actions/workflows/ci.yml)

An opt-in Scrapy downloader middleware that renders selected GET requests with [Lightpanda](https://github.com/lightpanda-io/browser) via [`lightpanda-py`](https://github.com/tclesius/lightpanda-py). Unmarked requests continue through Scrapy's normal downloader.

## Install

Install the package from PyPI:

```bash
python -m pip install scrapy-lightpanda-middleware
```

For development from this repository:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
```

`lightpanda-py` bundles the Lightpanda executable for supported platforms.

## Enable the middleware

Enable it in a spider's `custom_settings` or your Scrapy project's settings:

```python
DOWNLOADER_MIDDLEWARES = {
    "scrapy_lightpanda.middleware.LightpandaMiddleware": 800,
}
```

Keep this middleware after Scrapy's request-preparation middleware, but before HTTP cache middleware. Priority `800` places it after Scrapy's default headers, cookies, and proxy middleware and before HTTP cache. Opted-in requests are marked uncacheable so rendered and ordinary responses cannot share cache entries.

Opt in individual requests with `meta={"lightpanda": True}`:

```python
yield scrapy.Request(
    "https://example.com/javascript-page",
    callback=self.parse,
    meta={
        "lightpanda": True,
        "lightpanda_wait_until": "networkidle",
        "lightpanda_wait_selector": "main article",
    },
)
```

The middleware accepts these optional per-request settings:

- `lightpanda_wait_until`: Lightpanda navigation readiness event, such as `load`, `domcontentloaded`, `networkalmostidle`, `networkidle`, or `done`.
- `lightpanda_wait_selector`: CSS selector to wait for before returning the rendered page.

Only `Accept`, `Accept-Language`, and `User-Agent` are forwarded. Repeated `Accept` and `Accept-Language` values are combined, and `User-Agent` uses Lightpanda's dedicated option. `Referer`, cookies, authorization, and custom headers are not forwarded, even with opt-in: Lightpanda applies CLI headers to every outgoing request, including cross-origin subrequests. Sensitive origin headers cause a clear error when the opt-in is set rather than risking disclosure.

An unauthenticated Scrapy proxy (`request.meta["proxy"]`) is forwarded to Lightpanda. Scrapy's Basic proxy credentials are reconstructed from `Proxy-Authorization` into the proxy URL only when `lightpanda_allow_sensitive_headers=True`; other proxy authorization schemes are not supported. This opt-in is only for proxy credentials. Credentialed proxy values become subprocess arguments and may be visible to same-user process inspection; Lightpanda errors are redacted when such credentials are in use. Inherited proxy environment variables can override Scrapy's decision, so the middleware fails clearly if they conflict rather than silently using or bypassing a proxy.

Scrapy's per-request `download_timeout` (seconds), or the configured `DOWNLOAD_TIMEOUT` when no request override is set, becomes Lightpanda's `http_timeout` in milliseconds. Positive sub-millisecond values round up to one millisecond. Results without an HTTP status are treated as retryable download timeouts. The timeout limits Lightpanda's network request but is not a hard deadline for its subprocess; cancelling the Scrapy worker thread does not guarantee that the subprocess is stopped. Lightpanda also rejects browser-impersonating User-Agent strings containing `Mozilla`; use a compatible custom value if setting `USER_AGENT`.

The returned object is a Scrapy `HtmlResponse`, so callbacks can use the usual `.css()`, `.xpath()`, `.text`, and `.url` APIs. The synchronous Lightpanda fetch runs in a worker thread rather than blocking Scrapy's reactor. Lightpanda errors are passed back through Scrapy's normal request failure handling.

Only opted-in GET requests are supported. An opted-in request using another HTTP method raises Scrapy's `NotSupported` exception; it is not silently sent through a different request path.

## Example

[`examples/spider.py`](examples/spider.py) issues one normal Scrapy request and one Lightpanda-rendered request to the same URL:

```bash
scrapy runspider examples/spider.py -a url=https://example.com
```

Lightpanda is a lightweight browser engine, not a full desktop browser. JavaScript and browser feature coverage can differ from Chromium or Firefox, so verify the rendered output for your target site.

## JavaScript-rendered quotes example

[`examples/quotes_spider.py`](examples/quotes_spider.py) visits [Quotes to Scrape's JavaScript demo](https://quotes.toscrape.com/js/), emits each quote's text, author, and tags, and follows the next-page link using Lightpanda for every page:

```bash
scrapy runspider examples/quotes_spider.py
```

Run it from this project directory after installation. It requires network access to the demo site.

## Releases

The PyPI distribution is named `scrapy-lightpanda-middleware` (the Python import remains `scrapy_lightpanda`). Releases use PyPI Trusted Publishing; no PyPI API token is stored in GitHub.

Before the first release, configure a PyPI pending Trusted Publisher for:

- PyPI project: `scrapy-lightpanda-middleware`
- GitHub owner: `bisdak`
- Repository: `scrapy-lightpanda`
- Workflow filename: `publish.yml` (the file is `.github/workflows/publish.yml`)
- GitHub environment: `pypi`

Create the `pypi` environment in GitHub repository settings with a required reviewer and deployment tags restricted to `v*`; enable prevention of self-review and disallow administrator bypass where the repository plan permits. Protect changes to the release workflow with required PR review/branch protection. These controls matter because PyPI trusts the configured workflow identity and environment, not the workflow's event trigger.

Once the pending publisher and environment protections are configured and CI is green, publish a GitHub Release tagged `v0.1.0` to upload the first release. The release workflow verifies the tag matches `pyproject.toml` and publishes only after the full test matrix, wheel/sdist checks, and tests against the extracted source distribution pass. The shorter PyPI name `scrapy-lightpanda` belongs to a separate, unrelated project and must not be used.
