"""Run with: scrapy runspider examples/spider.py -a url=https://example.com."""

import scrapy
from scrapy import Request


class LightpandaExampleSpider(scrapy.Spider):
    name = "lightpanda_example"

    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_lightpanda.middleware.LightpandaMiddleware": 800,
        },
    }

    def __init__(self, url: str = "https://example.com", **kwargs):
        super().__init__(**kwargs)
        self.url = url

    def start_requests(self):
        yield Request(self.url, callback=self.parse, cb_kwargs={"rendered": False})
        yield Request(
            self.url,
            callback=self.parse,
            cb_kwargs={"rendered": True},
            dont_filter=True,
            meta={"lightpanda": True, "lightpanda_wait_until": "networkidle"},
        )

    def parse(self, response, rendered: bool):
        yield {
            "url": response.url,
            "rendered_with_lightpanda": rendered,
            "title": response.css("title::text").get(),
        }
