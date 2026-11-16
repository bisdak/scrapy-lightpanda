"""Scrape quotes from the JavaScript-rendered Quotes to Scrape demo."""

import scrapy
from scrapy import Request
from scrapy.http import Response


def _clean_text(value: str) -> str:
    return " ".join(value.split())


class QuotesSpider(scrapy.Spider):
    name = "quotes_js"
    start_url = "https://quotes.toscrape.com/js/"

    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_lightpanda.middleware.LightpandaMiddleware": 800,
        },
    }

    async def start(self):
        yield self._start_request()

    def start_requests(self):
        yield self._start_request()

    def _start_request(self) -> Request:
        return Request(self.start_url, callback=self.parse, meta={"lightpanda": True})

    def parse(self, response: Response):
        for quote in response.css(".quote"):
            yield {
                "text": _clean_text(" ".join(quote.css(".text::text").getall())),
                "author": _clean_text(" ".join(quote.css(".author::text").getall())),
                "tags": [_clean_text(tag) for tag in quote.css(".tag::text").getall()],
            }

        next_page = response.css("li.next > a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse, meta={"lightpanda": True})
