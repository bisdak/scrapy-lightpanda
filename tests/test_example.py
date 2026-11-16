import pytest

from examples.quotes_spider import QuotesSpider
from examples.spider import LightpandaExampleSpider


def test_example_keeps_same_url_static_and_lightpanda_requests():
    requests = list(LightpandaExampleSpider(url="https://example.com").start_requests())

    assert requests[0].url == requests[1].url
    assert requests[0].dont_filter is False
    assert requests[1].dont_filter is True
    assert requests[1].meta["lightpanda"] is True


@pytest.mark.parametrize("spider_class", [LightpandaExampleSpider, QuotesSpider])
def test_example_middleware_runs_after_scrapy_request_preparation(spider_class):
    middlewares = spider_class.custom_settings["DOWNLOADER_MIDDLEWARES"]

    assert middlewares["scrapy_lightpanda.middleware.LightpandaMiddleware"] == 800
