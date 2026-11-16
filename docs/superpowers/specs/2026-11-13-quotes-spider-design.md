# Quotes Spider Example — Design

## Intent

Add a concrete second example showing the middleware rendering a JavaScript-driven site. Use `https://quotes.toscrape.com/js/`, the public JavaScript-rendered demo used by `lightpanda-py` itself.

## Goals and boundaries

- Add a dedicated Scrapy spider that opts each page request into Lightpanda, extracts quote text, author, and tags, and follows the site's next-page link.
- Keep the existing generic static-versus-rendered example unchanged.
- Document how to run the new spider.
- Do not add browser interactions, new middleware behavior, or live-network requirements to the unit test suite.

## Approaches considered

1. **Add a dedicated quotes spider (chosen):** a site-specific example demonstrates rendered extraction and pagination while preserving the generic example.
2. **Change the current example's default URL:** less code, but removes the current generic static/rendered comparison.

## Design calls

- Add `examples/quotes_spider.py`, with Lightpanda enabled on its start and pagination requests.
- Use Scrapy selectors for `.quote`, `.text`, `.author`, `.tag`, and `li.next > a`.
- Update the README with a command to run the example and note that it requires network access when run.

## Constraints

Use the existing middleware and project dependency set. Unit tests should verify the spider's request metadata and extraction from a local HTML fixture, not access the public site.
