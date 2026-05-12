from data_modules.query_router import QueryRouter


def test_query_router_routes_relationship_and_extracts_names():
    router = QueryRouter()
    payload = router.route_intent("秦思妍对陈默的态度和关系线应该怎么延续")

    assert payload["intent"] == "relationship"
    assert payload["needs_graph"] is True
    assert "秦思妍" in payload["entities"]
    assert "陈默" in payload["entities"]


def test_query_router_routes_setting_for_wechat_group():
    router = QueryRouter()
    payload = router.route_intent("地府微信群红包规则是什么")

    assert payload["intent"] == "setting"
    assert payload["needs_graph"] is False


def test_query_router_extracts_chapter_range():
    router = QueryRouter()
    payload = router.route_intent("第6到9章秦思妍和陈默关系")

    assert payload["time_scope"] == {"from_chapter": 6, "to_chapter": 9}
