import subprocess
import sys
import textwrap
from pathlib import Path


def test_scrapy_crawler_delivers_lightpanda_response_to_spider():
    script = textwrap.dedent(
        """
        from types import SimpleNamespace

        import lightpanda
        from scrapy import Request, Spider
        from scrapy.crawler import CrawlerProcess

        lightpanda.fetch = lambda *args, **kwargs: SimpleNamespace(
            json=lambda: {
                "http_status": 200,
                "url": "https://example.com/",
                "content": "<html><h1>Rendered by Lightpanda</h1></html>",
                "headers": {"Content-Type": "text/html; charset=utf-8"},
            }
        )

        class IntegrationSpider(Spider):
            name = "lightpanda_integration"
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {
                    "scrapy_lightpanda.middleware.LightpandaMiddleware": 800,
                },
                "LOG_ENABLED": False,
            }

            async def start(self):
                yield self.request()

            def start_requests(self):
                yield self.request()

            @staticmethod
            def request():
                return Request("https://example.com/", meta={"lightpanda": True})

            def parse(self, response):
                assert response.status == 200
                assert response.css("h1::text").get() == "Rendered by Lightpanda"
                self.crawler.stats.set_value("integration/rendered", True)

        process = CrawlerProcess(settings={"LOG_ENABLED": False})
        crawler = process.create_crawler(IntegrationSpider)
        process.crawl(crawler)
        process.start()
        assert crawler.stats.get_value("integration/rendered") is True
        print("Scrapy crawler delivered the rendered response")
        """
    )
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Scrapy crawler delivered the rendered response" in result.stdout
