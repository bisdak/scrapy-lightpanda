def test_package_imports():
    import scrapy_lightpanda

    assert isinstance(scrapy_lightpanda.__version__, str)
