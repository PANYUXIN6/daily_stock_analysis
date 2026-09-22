"""Exercise the supported news-provider chain without external requests."""
from datetime import datetime
from unittest.mock import patch

import pytest

from src.search_service import (
    BochaSearchProvider,
    SearchResponse,
    SearchResult,
    SearchService,
    TavilySearchProvider,
)


def news_response(provider):
    return SearchResponse(
        query="贵州茅台 最新消息",
        provider=provider,
        success=True,
        results=[SearchResult(
            title="贵州茅台发布最新经营公告",
            snippet="贵州茅台公布经营数据及业绩情况。",
            url="https://example.com/moutai-news",
            source="财经新闻",
            published_date=datetime.now().isoformat(),
        )],
    )


def test_bocha_news_is_used_before_tavily():
    service = SearchService(bocha_keys=["bocha-test"], tavily_keys=["tavily-test"])
    with patch.object(BochaSearchProvider, "_do_search", return_value=news_response("Bocha")), \
         patch.object(TavilySearchProvider, "_do_search") as tavily:
        response = service.search_stock_news("600519", "贵州茅台")
    assert response.success
    assert response.provider == "Bocha"
    assert response.results[0].title == "贵州茅台发布最新经营公告"
    tavily.assert_not_called()


@pytest.mark.parametrize("bocha_success", [False, True], ids=["failed", "empty"])
def test_tavily_supplies_news_when_bocha_has_no_usable_results(bocha_success):
    service = SearchService(bocha_keys=["bocha-test"], tavily_keys=["tavily-test"])
    empty = SearchResponse(query="news", provider="Bocha", success=bocha_success, results=[])
    with patch.object(BochaSearchProvider, "_do_search", return_value=empty), \
         patch.object(TavilySearchProvider, "_do_search", return_value=news_response("Tavily")):
        response = service.search_stock_news("600519", "贵州茅台")
    assert response.success
    assert response.provider == "Tavily"
    assert response.results[0].url == "https://example.com/moutai-news"
