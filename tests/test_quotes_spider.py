import asyncio

import pytest
from scrapy import Request
from scrapy.http import HtmlResponse

try:
    from examples.quotes_spider import QuotesSpider
except ImportError:
    QuotesSpider = None


def test_quotes_spider_is_available():
    assert QuotesSpider is not None, "quotes spider has not been implemented"


@pytest.fixture
def quotes_spider():
    if QuotesSpider is None:
        pytest.skip("quotes spider has not been implemented")
    return QuotesSpider()


def test_quotes_spider_starts_on_js_demo_with_lightpanda_opt_in(quotes_spider):
    request = next(quotes_spider.start_requests())

    assert request.url == "https://quotes.toscrape.com/js/"
    assert request.meta["lightpanda"] is True


def test_scrapy_async_start_yields_the_opted_in_start_request(quotes_spider):
    async def collect_requests():
        return [request async for request in quotes_spider.start()]

    requests = asyncio.run(collect_requests())

    assert [request.url for request in requests] == ["https://quotes.toscrape.com/js/"]
    assert requests[0].meta["lightpanda"] is True


def test_parse_extracts_normalized_quotes_and_follows_next_page(quotes_spider):
    html = """
    <div class="quote">
      <span class="text"> “First\n quote” </span>
      <small class="author"> Albert Einstein </small>
      <a class="tag"> change </a><a class="tag"> life </a>
    </div>
    <div class="quote">
      <span class="text">Second quote</span>
      <small class="author">Author Two</small>
      <a class="tag">simple</a>
    </div>
    <li class="next"><a href="/js/page/2/">Next</a></li>
    """
    response = HtmlResponse(
        "https://quotes.toscrape.com/js/",
        body=html.encode("utf-8"),
        encoding="utf-8",
    )

    results = list(quotes_spider.parse(response))

    assert results[:2] == [
        {"text": "“First quote”", "author": "Albert Einstein", "tags": ["change", "life"]},
        {"text": "Second quote", "author": "Author Two", "tags": ["simple"]},
    ]
    next_request = results[2]
    assert isinstance(next_request, Request)
    assert next_request.url == "https://quotes.toscrape.com/js/page/2/"
    assert next_request.meta["lightpanda"] is True


def test_parse_without_next_link_stops_after_emitting_quotes(quotes_spider):
    html = """
    <div class="quote">
      <span class="text">Only quote</span>
      <small class="author">Only author</small>
    </div>
    """
    response = HtmlResponse(
        "https://quotes.toscrape.com/js/page/10/",
        body=html.encode("utf-8"),
        encoding="utf-8",
    )

    results = list(quotes_spider.parse(response))

    assert results == [{"text": "Only quote", "author": "Only author", "tags": []}]
