from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.seprate_checks.redirect_urls import service as service_module
from app.modules.seprate_checks.redirect_urls.crawler import SiteDiscovery
from app.modules.seprate_checks.redirect_urls.schema import (
    RedirectHop,
    RedirectUrlResult,
)
from app.modules.seprate_checks.redirect_urls.service import (
    RedirectUrlAuditService,
    _analyze,
)


def test_empty_result_is_not_reported_as_a_pass():
    summary, findings, overall_status, severity = _analyze([])

    assert summary.total_urls == 0
    assert findings == []
    assert overall_status == "unverified"
    assert severity == "none"


def test_http_error_responses_are_broken_not_unverified():
    summary, findings, overall_status, severity = _analyze(
        [
            RedirectUrlResult(
                url="https://example.test/missing",
                final_url="https://example.test/missing",
                final_status=404,
                is_broken=True,
            )
        ]
    )

    assert summary.broken == 1
    assert summary.by_status_class["broken"] == 1
    assert summary.by_status_class["unverified"] == 0
    assert findings[0].code == "broken_destination"
    assert overall_status == "fail"
    assert severity == "high"


@pytest.mark.asyncio
async def test_empty_discovery_is_persisted_as_failed_and_unverified(monkeypatch):
    audit_id = uuid4()
    audit = SimpleNamespace(
        id=audit_id,
        domain="https://example.test/",
        status="queued",
        result=None,
        max_urls=50,
        max_depth=5,
        max_hops=10,
        discovered_count=0,
        discovery_errors=[],
        summary={},
        cost_seconds=None,
        checked_at=None,
        error_info=None,
    )
    updates: list[dict] = []
    persisted_graph: list[tuple[list[dict], list[dict]]] = []

    class FakeRepository:
        def __init__(self, session):
            assert session is None

        async def get(self, requested_id):
            assert requested_id == audit_id
            return audit

        async def update(self, requested_id, **values):
            updates.append(values)
            for name, value in values.items():
                setattr(audit, name, value)
            return audit

        async def replace_graph(self, requested_id, nodes, edges):
            assert requested_id == audit_id
            persisted_graph.append((nodes, edges))

        async def get_graph(self, requested_id):
            assert requested_id == audit_id
            return [], []

    async def empty_discovery(*args, **kwargs):
        return SiteDiscovery(
            host="example.test",
            urls=[],
            sitemap_urls=[],
            page_edges=[],
            errors=["robots.txt could not be read"],
            robots_reachable=False,
        )

    monkeypatch.setattr(service_module, "RedirectUrlAuditRepository", FakeRepository)
    monkeypatch.setattr(service_module, "discover_site_urls", empty_discovery)

    result = await RedirectUrlAuditService(session=None).run(
        audit_id,
        "https://example.test/",
        50,
    )

    assert result["status"] == "failed"
    assert result["total_checked"] == 0
    assert result["overall_status"] == "unverified"
    assert result["error"].startswith("No crawlable URLs")
    assert result["discovery_errors"] == ["robots.txt could not be read"]
    final_update = updates[-1]
    assert final_update["status"] == "failed"
    assert "result" not in final_update
    assert final_update["discovery_errors"] == ["robots.txt could not be read"]
    assert persisted_graph == [([], [])]


@pytest.mark.asyncio
async def test_audit_persists_normalized_graph_and_rebuilds_api_result(monkeypatch):
    audit_id = uuid4()
    home = "https://example.test/"
    old_url = "https://example.test/old"
    new_url = "https://example.test/new"
    audit = SimpleNamespace(
        id=audit_id,
        domain=home,
        status="queued",
        result=None,
        max_urls=10,
        max_depth=1,
        max_hops=2,
        discovered_count=0,
        discovery_errors=[],
        summary={},
        cost_seconds=None,
        checked_at=None,
        error_info=None,
    )
    stored_nodes: list[SimpleNamespace] = []
    stored_edges: list[SimpleNamespace] = []

    class FakeRepository:
        def __init__(self, session):
            assert session is None

        async def get(self, requested_id):
            assert requested_id == audit_id
            return audit

        async def update(self, requested_id, **values):
            for name, value in values.items():
                setattr(audit, name, value)
            return audit

        async def replace_graph(self, requested_id, nodes, edges):
            assert requested_id == audit_id
            node_ids = {}
            for values in nodes:
                node = SimpleNamespace(id=uuid4(), **values)
                node_ids[values["normalized_url"]] = node.id
                stored_nodes.append(node)
            for values in edges:
                edge = dict(values)
                stored_edges.append(
                    SimpleNamespace(
                        id=uuid4(),
                        audit_id=requested_id,
                        source_node_id=node_ids[edge.pop("source_normalized_url")],
                        target_node_id=node_ids[edge.pop("target_normalized_url")],
                        **edge,
                    )
                )

        async def get_graph(self, requested_id):
            assert requested_id == audit_id
            return stored_nodes, stored_edges

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    async def fake_discovery(*args, **kwargs):
        assert kwargs["max_depth"] == 1
        return SiteDiscovery(
            host="example.test",
            urls=[home, old_url],
            sitemap_urls=[],
            page_edges=[(home, old_url)],
            errors=[],
            robots_reachable=True,
            depths={home: 0, old_url: 1},
        )

    async def fake_check(url, *args, **kwargs):
        if url == old_url:
            return RedirectUrlResult(
                url=old_url,
                hops=[
                    RedirectHop(
                        url=old_url,
                        status=301,
                        location="/new",
                        resolved=new_url,
                        latency_ms=5,
                    )
                ],
                redirect_count=1,
                redirects=1,
                final_url=new_url,
                final_status=200,
                is_redirect=True,
                is_internal_redirect=True,
                latency_ms=15,
            )
        return RedirectUrlResult(
            url=home,
            final_url=home,
            final_status=200,
            latency_ms=10,
        )

    monkeypatch.setattr(service_module, "RedirectUrlAuditRepository", FakeRepository)
    monkeypatch.setattr(
        service_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeClient(),
    )
    monkeypatch.setattr(service_module, "discover_site_urls", fake_discovery)
    monkeypatch.setattr(service_module, "check_redirect_chain", fake_check)

    result = await RedirectUrlAuditService(session=None).run(
        audit_id,
        home,
        10,
        max_depth=1,
        max_hops=2,
    )

    assert result["status"] == "completed"
    assert result["total_checked"] == 2
    assert result["max_depth"] == 1
    assert result["max_hops"] == 2
    assert result["summary"]["redirects_found"] == 1
    assert len(stored_nodes) == 3
    assert any(edge.edge_type == "link" for edge in stored_edges)
    redirect_edge = next(edge for edge in stored_edges if edge.edge_type == "redirect")
    assert redirect_edge.hop_number == 1
    checked_redirect = next(item for item in result["results"] if item["url"] == old_url)
    assert checked_redirect["hops"][0]["resolved"] == new_url
    assert checked_redirect["source_pages"] == [home]
    assert result["graph"]["edges"][1]["kind"] == "redirect"
