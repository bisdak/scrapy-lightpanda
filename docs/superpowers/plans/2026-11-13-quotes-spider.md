# Quotes Spider Example Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runnable Scrapy example that uses the Lightpanda middleware to extract quotes from a JavaScript-rendered site and follow its pagination.

**Architecture:** A dedicated spider requests `https://quotes.toscrape.com/js/` through the existing middleware, extracts quote text, author, and tags, then schedules the next page with the Lightpanda metadata flag. Tests use local `HtmlResponse` fixtures and never access the public site.

**Tech Stack:** Python 3.10+, Scrapy, pytest, existing `scrapy-lightpanda` middleware.

**Spec:** `docs/superpowers/specs/2026-11-13-quotes-spider-design.md`

## Global Constraints

- Add a separate `examples/quotes_spider.py`; leave `examples/spider.py` unchanged.
- Use the existing `LightpandaMiddleware`; do not modify middleware behavior or dependencies.
- Opt in every initial and pagination request using `meta={"lightpanda": True}`.
- Extract `.quote`, `.text`, `.author`, `.tag`, and `li.next > a` using Scrapy selectors.
- Tests must use local HTML fixtures only, with no browser or live network.

## Review Focus

- Pagination request must preserve Lightpanda opt-in and resolve a relative `href` against the response URL (Task 1).
- A page without a next link must emit quote items and stop without scheduling another request (Task 1).
- Quote strings, author, and multiple tags must be extracted and whitespace-normalized from rendered markup (Task 1).
- The spider's start request must target the exact JavaScript demo URL and opt in (Task 1).
- The new README command must name the new file and be runnable after the documented package installation (Task 1).

---

### Task 1: Add the paginated JavaScript quotes spider example

**Files:**
- Create: `examples/quotes_spider.py`
- Create: `tests/test_quotes_spider.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `scrapy_lightpanda.middleware.LightpandaMiddleware`.
- Produces: `QuotesSpider`, a Scrapy spider yielding items with `text`, `author`, and `tags` keys.

- [ ] **Step 1: Write local-fixture spider tests**

Add tests asserting the start request URL is `https://quotes.toscrape.com/js/` and has `meta["lightpanda"] is True`; parsing a local HTML response with two quotes emits normalized text/author/tag items and yields a next-page request with a resolved URL and Lightpanda opt-in; and a response without a next link yields only items, with no follow-up request.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_quotes_spider.py -q`
Expected: FAIL because `examples.quotes_spider` does not exist.

- [ ] **Step 3: Implement the spider**

Create `QuotesSpider` in `examples/quotes_spider.py`. Enable `scrapy_lightpanda.middleware.LightpandaMiddleware` through `custom_settings`; implement `start_requests` for the JavaScript demo URL with `meta={"lightpanda": True}`; parse each `.quote` into whitespace-normalized `text`, `author`, and `tags`; and follow the first `li.next > a` with `response.follow(..., meta={"lightpanda": True})`.

- [ ] **Step 4: Document the command**

Add a README subsection with `scrapy runspider examples/quotes_spider.py`, describe the emitted fields and pagination, and clarify that running it requires network access.

- [ ] **Step 5: Run the full standalone suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: all tests pass without launching Lightpanda or making network requests.
