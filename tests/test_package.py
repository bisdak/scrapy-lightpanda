from importlib.metadata import metadata


def test_package_imports():
    import scrapy_lightpanda

    assert isinstance(scrapy_lightpanda.__version__, str)


def test_distribution_metadata_uses_new_name_and_license():
    import scrapy_lightpanda

    package_metadata = metadata("scrapy-lightpanda-middleware")

    assert package_metadata["Name"] == "scrapy-lightpanda-middleware"
    assert package_metadata["Version"] == scrapy_lightpanda.__version__
    assert package_metadata["License-Expression"] == "BSD-3-Clause"
