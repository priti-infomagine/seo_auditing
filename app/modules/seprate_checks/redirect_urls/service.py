from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from .crawler import (
    PublicHostGuard,
    canonicalize_url,
    check_redirect_chain,
    discover_site_urls,
)
from .graph import build_redirect_graph
from .repository import RedirectUrlAuditRepository
from .schema import (
    RedirectGraph,
    RedirectGraphEdge,
    RedirectGraphNode,
    RedirectCheckResultResponse,
    RedirectFinding,
    RedirectHop,
    RedirectRecommendation,
    RedirectSummary,
    RedirectUrlResult,
)
from .model import RedirectUrlAudit, RedirectUrlEdge

MAX_CONCURRENCY = 10
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_ERROR_INFO_LENGTH = 1000
AUDIT_TIMEOUT_SECONDS = 1500.0
MAX_REQUESTED_URLS = 500
MAX_REQUESTED_DEPTH = 8
MAX_REQUESTED_HOPS = 20


def _status_text(status_code: int | None) -> str | None:
    if status_code is None:
        return None
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return None


def _analyze(
    results: list[RedirectUrlResult],
) -> tuple[RedirectSummary, list[RedirectFinding], str, str]:
    summary = RedirectSummary(total_urls=len(results))
    findings: list[RedirectFinding] = []
    status_counts = summary.by_status_class

    for result in results:
        summary.total_redirect_hops += result.redirect_count
        if result.error_type == "redirect_loop":
            summary.loops += 1
        if result.error_type == "max_hops_exceeded":
            summary.hop_limit_exceeded += 1
        if result.is_redirect:
            summary.redirects_found += 1
            summary.redirect_chains += int(result.redirect_count > 0)
            summary.internal_redirects += int(result.is_internal_redirect)
            summary.external_redirects += int(result.is_external_redirect)
            if result.redirect_count > 2:
                findings.append(
                    RedirectFinding(
                        code="long_redirect_chain",
                        severity="medium",
                        status="warning",
                        message=f"Redirect chain has {result.redirect_count} hops",
                        evidence=" -> ".join(
                            hop["url"] for hop in result.chain if hop.get("url")
                        ),
                        target_url=result.url,
                        redirect_count=result.redirect_count,
                        final_status=result.final_status,
                    )
                )

        if result.error or result.final_status is None:
            summary.broken += 1
            status_counts["unverified"] += 1
            finding_code = {
                "redirect_loop": "redirect_loop",
                "max_hops_exceeded": "redirect_hop_limit",
                "malformed_location": "malformed_redirect",
            }.get(result.error_type, "redirect_check_failed")
            findings.append(
                RedirectFinding(
                    code=finding_code,
                    severity="high",
                    status="fail",
                    message=f"Could not verify {result.url}",
                    evidence=result.error or "No HTTP response was received",
                    target_url=result.url,
                    redirect_count=result.redirect_count,
                    final_status=result.final_status,
                )
            )
            continue

        if 200 <= result.final_status < 300:
            status_counts["ok"] += 1
        elif 300 <= result.final_status < 400:
            status_counts["redirect"] += 1
        elif result.final_status >= 400:
            status_counts["broken"] += 1
            summary.broken += 1
            findings.append(
                RedirectFinding(
                    code="broken_destination",
                    severity="high",
                    status="fail",
                    message=f"Final destination returned HTTP {result.final_status}",
                    evidence=f"{result.url} -> {result.final_url}",
                    target_url=result.url,
                    redirect_count=result.redirect_count,
                    final_status=result.final_status,
                )
            )
        else:
            status_counts["unverified"] += 1

    if not results:
        return summary, findings, "unverified", "none"
    if any(finding.status == "fail" for finding in findings):
        return summary, findings, "fail", "high"
    if findings:
        return summary, findings, "warning", "medium"
    return summary, findings, "pass", "none"


def _recommendations(
    findings: list[RedirectFinding],
) -> list[RedirectRecommendation]:
    templates = {
        "redirect_check_failed": (
            "high",
            "Verify unreachable URLs",
            "Some URLs could not be checked successfully.",
            "Check that the URL is reachable and update or remove invalid links.",
            "source_pages",
        ),
        "broken_destination": (
            "high",
            "Fix broken destinations",
            "A redirect chain ends at a broken destination.",
            "Restore the destination or update the redirect target.",
            "server_config",
        ),
        "long_redirect_chain": (
            "medium",
            "Shorten redirect chains",
            "Some URLs require more than two redirects.",
            "Update source links to point directly to the final destination.",
            "source_pages",
        ),
        "redirect_loop": (
            "high",
            "Resolve redirect loops",
            "A redirect chain returns to a URL already visited.",
            "Update the redirect rules so the chain terminates at a final URL.",
            "server_config",
        ),
        "redirect_hop_limit": (
            "high",
            "Shorten redirect chains",
            "A redirect chain exceeded the configured hop limit.",
            "Remove intermediate redirects or point directly to the final URL.",
            "server_config",
        ),
        "malformed_redirect": (
            "high",
            "Repair redirect responses",
            "A redirect response is missing a valid Location target.",
            "Return a valid absolute or relative Location header.",
            "server_config",
        ),
    }
    recommendations: list[RedirectRecommendation] = []
    seen: set[str] = set()
    for finding in findings:
        template = templates.get(finding.code)
        if not template or finding.code in seen:
            continue
        seen.add(finding.code)
        priority, title, message, fix, where_to_fix = template
        recommendations.append(
            RedirectRecommendation(
                code=finding.code,
                priority=priority,
                title=title,
                message=message,
                fix=fix,
                where_to_fix=where_to_fix,
                evidence=finding.evidence,
            )
        )
    return recommendations


def _graph_records(
    graph: RedirectGraph,
    results: list[RedirectUrlResult],
    discovered_urls: list[str],
    depths: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result_by_url = {result.url: result for result in results}
    discovery_order = {url: index for index, url in enumerate(discovered_urls)}
    node_ids_by_url: dict[str, str] = {}
    node_rows: list[dict[str, Any]] = []
    for graph_node in graph.nodes:
        normalized_url = canonicalize_url(graph_node.url) or graph_node.url
        if normalized_url in node_ids_by_url:
            continue
        node_ids_by_url[graph_node.url] = normalized_url
        result = result_by_url.get(graph_node.url)
        if result is None:
            state = "unverified"
        elif result.error:
            state = "unverified"
        elif result.final_status is not None and result.final_status >= 400:
            state = "broken"
        elif result.is_redirect:
            state = "redirect"
        else:
            state = "ok"
        node_rows.append(
            {
                "url": graph_node.url,
                "normalized_url": normalized_url,
                "normalized_url_hash": hashlib.sha256(
                    normalized_url.encode("utf-8")
                ).hexdigest(),
                "kind": graph_node.kind,
                "discovery_order": discovery_order.get(graph_node.url),
                "crawl_depth": depths.get(graph_node.url),
                "status_code": (
                    result.final_status if result is not None else graph_node.status
                ),
                "final_url": result.final_url if result is not None else None,
                "redirect_hops": result.redirect_count if result is not None else 0,
                "state": state,
                "error_type": result.error_type if result is not None else None,
                "error_message": result.error if result is not None else None,
                "latency_ms": result.latency_ms if result is not None else None,
                "is_redirect": result.is_redirect if result is not None else False,
                "is_internal_redirect": (
                    result.is_internal_redirect if result is not None else False
                ),
                "is_external_redirect": (
                    result.is_external_redirect if result is not None else False
                ),
                "is_broken": (
                    result.is_broken or bool(result.error)
                    if result is not None
                    else False
                ),
                "in_sitemap": result.in_sitemap if result is not None else False,
            }
        )

    redirect_hops = {
        (hop.url, hop.resolved, hop.status): hop
        for result in results
        for hop in result.hops
        if hop.resolved
    }
    edge_positions: dict[tuple[str, str], int] = {}
    edge_rows: list[dict[str, Any]] = []
    for edge in graph.edges:
        source_normalized = node_ids_by_url[edge.source]
        target_normalized = node_ids_by_url[edge.target]
        edge_position_key = (source_normalized, edge.kind)
        position = edge_positions.get(edge_position_key, 0) + 1
        edge_positions[edge_position_key] = position
        if edge.kind == "redirect":
            hop = redirect_hops.get((edge.source, edge.target, edge.status))
        else:
            hop = None
        edge_rows.append(
            {
                "source_normalized_url": source_normalized,
                "target_normalized_url": target_normalized,
                "edge_type": edge.kind,
                "position": position,
                "hop_number": edge.hop,
                "status_code": edge.status,
                "location": hop.location if hop is not None else None,
                "latency_ms": hop.latency_ms if hop is not None else None,
            }
        )
    return node_rows, edge_rows


class RedirectUrlAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = RedirectUrlAuditRepository(session)

    async def build_result(self, audit: RedirectUrlAudit) -> dict[str, Any]:
        if audit.result is not None:
            return audit.result

        nodes, edges = await self.repository.get_graph(audit.id)
        node_by_id = {node.id: node for node in nodes}
        outgoing_redirects: dict[UUID, list[RedirectUrlEdge]] = {}
        incoming_sources: dict[UUID, list[str]] = {}
        graph_edges: list[RedirectGraphEdge] = []
        for edge in edges:
            source = node_by_id[edge.source_node_id]
            target = node_by_id[edge.target_node_id]
            if edge.edge_type == "link":
                incoming_sources.setdefault(edge.target_node_id, []).append(source.url)
            else:
                outgoing_redirects.setdefault(edge.source_node_id, []).append(edge)
            graph_edges.append(
                RedirectGraphEdge(
                    source=source.url,
                    target=target.url,
                    kind=edge.edge_type,
                    status=edge.status_code,
                    hop=edge.hop_number if edge.edge_type == "redirect" else None,
                )
            )

        for source_edges in outgoing_redirects.values():
            source_edges.sort(key=lambda edge: edge.position)

        checked_nodes = sorted(
            (node for node in nodes if node.crawl_depth is not None),
            key=lambda node: (
                node.discovery_order if node.discovery_order is not None else 0,
                node.normalized_url,
            ),
        )
        results: list[RedirectUrlResult] = []
        for node in checked_nodes:
            hops: list[RedirectHop] = []
            chain: list[dict[str, Any]] = [{"url": node.url, "status": None}]
            current_node = node
            visited = {node.id}
            while True:
                next_edges = outgoing_redirects.get(current_node.id, [])
                if not next_edges:
                    break
                edge = next_edges[0]
                target = node_by_id[edge.target_node_id]
                hops.append(
                    RedirectHop(
                        url=current_node.url,
                        status=edge.status_code,
                        status_text=_status_text(edge.status_code),
                        location=edge.location,
                        resolved=target.url,
                        latency_ms=edge.latency_ms,
                    )
                )
                chain.append({"url": target.url, "status": edge.status_code})
                if target.id in visited:
                    break
                visited.add(target.id)
                current_node = target

            if (
                node.error_type == "malformed_location"
                and len(hops) < node.redirect_hops
            ):
                hops.append(
                    RedirectHop(
                        url=current_node.url,
                        status=node.status_code,
                        status_text=_status_text(node.status_code),
                        latency_ms=node.latency_ms,
                    )
                )

            results.append(
                RedirectUrlResult(
                    url=node.url,
                    hops=hops,
                    redirects=node.redirect_hops,
                    final_url=node.final_url,
                    final_status=node.status_code,
                    error=node.error_message,
                    error_type=node.error_type,
                    latency_ms=node.latency_ms,
                    redirect_count=node.redirect_hops,
                    chain=chain,
                    is_redirect=node.is_redirect,
                    is_internal_redirect=node.is_internal_redirect,
                    is_external_redirect=node.is_external_redirect,
                    is_broken=node.is_broken,
                    in_sitemap=node.in_sitemap,
                    source_pages=list(
                        dict.fromkeys(incoming_sources.get(node.id, []))
                    ),
                    crawl_depth=node.crawl_depth,
                )
            )

        summary, findings, overall_status, severity = _analyze(results)
        if not results or (audit.discovery_errors and not findings):
            overall_status = "unverified"
            severity = "none"
        graph = RedirectGraph(
            nodes=[
                RedirectGraphNode(
                    id=node.url,
                    url=node.url,
                    kind=node.kind,
                    status=node.status_code,
                    error=node.error_message,
                )
                for node in nodes
            ],
            edges=graph_edges,
        )
        return RedirectCheckResultResponse(
            check_id=audit.id,
            domain=audit.domain,
            status=audit.status,
            total_checked=len(results),
            discovered_count=audit.discovered_count,
            max_depth=audit.max_depth,
            max_hops=audit.max_hops,
            results=results,
            graph=graph,
            findings=findings,
            recommendations=_recommendations(findings),
            summary=summary,
            overall_status=overall_status,
            severity=severity,
            error=audit.error_info,
            discovery_errors=audit.discovery_errors or [],
            cost_seconds=audit.cost_seconds,
            checked_at=(
                audit.checked_at.isoformat() if audit.checked_at is not None else None
            ),
        ).model_dump(mode="json", by_alias=True)

    async def run(
        self,
        audit_id: UUID,
        domain: str,
        max_urls: int,
        max_depth: int = 5,
        max_hops: int = 10,
        update_task_state: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not 1 <= max_urls <= MAX_REQUESTED_URLS:
            raise ValueError(
                f"max_urls must be between 1 and {MAX_REQUESTED_URLS}"
            )
        if not 0 <= max_depth <= MAX_REQUESTED_DEPTH:
            raise ValueError(
                f"max_depth must be between 0 and {MAX_REQUESTED_DEPTH}"
            )
        if not 0 <= max_hops <= MAX_REQUESTED_HOPS:
            raise ValueError(
                f"max_hops must be between 0 and {MAX_REQUESTED_HOPS}"
            )
        try:
            return await asyncio.wait_for(
                self._run_pipeline(
                    audit_id,
                    domain,
                    max_urls,
                    max_depth,
                    max_hops,
                    update_task_state,
                ),
                timeout=AUDIT_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            message = (
                f"Redirect URL audit exceeded its {AUDIT_TIMEOUT_SECONDS:g}-second time limit."
            )
            await self.repository.update(
                audit_id,
                status="failed",
                error_info=message,
                progress={"phase": "failed", "reason": "audit_timeout"},
                completed_at=datetime.now(timezone.utc),
            )
            raise TimeoutError(message) from exc

    async def _run_pipeline(
        self,
        audit_id: UUID,
        domain: str,
        max_urls: int,
        max_depth: int,
        max_hops: int,
        update_task_state: Callable[[str, dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        audit = await self.repository.get(audit_id)
        if audit is None:
            raise LookupError(f"Redirect URL audit {audit_id} was not found")
        if audit.status in {"completed", "partial", "failed"}:
            return await self.build_result(audit)

        await self.repository.update(
            audit_id,
            status="discovering",
            started_at=datetime.now(timezone.utc),
            progress={"phase": "discovery", "processed": 0},
            error_info=None,
        )
        guard = PublicHostGuard()
        limits = httpx.Limits(
            max_connections=MAX_CONCURRENCY,
            max_keepalive_connections=MAX_CONCURRENCY,
        )
        timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)

        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=timeout,
                limits=limits,
                headers={"User-Agent": "SEOAuditBot/1.0"},
            ) as client:
                async def discovery_progress(processed: int, pending: int) -> None:
                    progress = {
                        "phase": "crawling",
                        "processed": processed,
                        "pending": pending,
                        "total": max_urls,
                    }
                    await self.repository.update(
                        audit_id,
                        progress=progress,
                    )
                    if update_task_state:
                        update_task_state("PROGRESS", progress)

                discovery = await discover_site_urls(
                    domain,
                    max_urls,
                    client,
                    guard,
                    progress=discovery_progress,
                    max_depth=max_depth,
                )
                host = discovery.host
                discovered_urls = discovery.urls
                page_edges = discovery.page_edges
                sources_by_url: dict[str, list[str]] = {}
                for source, target in page_edges:
                    sources_by_url.setdefault(target, []).append(source)
                await self.repository.update(
                    audit_id,
                    discovered_count=len(discovered_urls),
                    status="checking" if discovered_urls else "failed",
                    progress={
                        "phase": "checking" if discovered_urls else "complete",
                        "processed": 0,
                        "total": len(discovered_urls),
                    },
                )

                results: list[RedirectUrlResult] = []
                completed_count = 0
                failed_count = 0

                async def check_one(url: str) -> RedirectUrlResult:
                    return await check_redirect_chain(
                        url,
                        host,
                        client,
                        guard,
                        max_hops=max_hops,
                    )

                for offset in range(0, len(discovered_urls), MAX_CONCURRENCY):
                    batch = discovered_urls[offset:offset + MAX_CONCURRENCY]
                    batch_results = await asyncio.gather(
                        *(check_one(url) for url in batch)
                    )
                    for result in batch_results:
                        results.append(result)
                        completed_count += int(not result.error)
                        failed_count += int(bool(result.error))
                    processed = completed_count + failed_count
                    if processed == len(discovered_urls) or processed % 20 == 0:
                        progress = {
                            "phase": "checking",
                            "processed": processed,
                            "total": len(discovered_urls),
                        }
                        await self.repository.update(
                            audit_id,
                            completed_count=completed_count,
                            failed_count=failed_count,
                            progress=progress,
                        )
                        if update_task_state:
                            update_task_state("PROGRESS", progress)

            sitemap_urls = set(discovery.sitemap_urls)
            for result in results:
                result.in_sitemap = result.url in sitemap_urls
                result.source_pages = list(dict.fromkeys(sources_by_url.get(result.url, [])))
            summary, _, _, _ = _analyze(results)
            elapsed = round(time.perf_counter() - started, 3)
            no_urls_error = (
                "No crawlable URLs were discovered. Check the site's reachability, "
                "robots.txt policy, sitemap, and requested URL limit."
                if not discovered_urls
                else None
            )
            error_message = no_urls_error
            if not error_message and discovery.errors:
                error_message = "Some URLs could not be discovered: " + "; ".join(
                    discovery.errors[:5]
                )
            has_successful_checks = any(
                result.final_status is not None and not result.error for result in results
            )
            final_status = (
                "failed"
                if not discovered_urls or not has_successful_checks
                else "partial"
                if failed_count or discovery.errors
                else "completed"
            )
            if results and not has_successful_checks:
                error_message = "No discovered URLs could be checked successfully."
            graph = build_redirect_graph(discovered_urls, results, page_edges)
            node_rows, edge_rows = _graph_records(
                graph,
                results,
                discovered_urls,
                discovery.depths,
            )
            await self.repository.replace_graph(audit_id, node_rows, edge_rows)
            checked_at = datetime.now(timezone.utc)
            await self.repository.update(
                audit_id,
                status=final_status,
                discovered_count=len(discovered_urls),
                completed_count=completed_count,
                failed_count=failed_count,
                max_depth=max_depth,
                max_hops=max_hops,
                discovery_errors=discovery.errors,
                summary=summary.model_dump(mode="json"),
                cost_seconds=elapsed,
                checked_at=checked_at,
                progress={
                    "phase": "complete",
                    "processed": len(results),
                    "total": len(discovered_urls),
                },
                error_info=error_message,
                completed_at=datetime.now(timezone.utc),
            )
            updated_audit = await self.repository.get(audit_id)
            if updated_audit is None:
                raise LookupError(f"Redirect URL audit {audit_id} disappeared")
            return await self.build_result(updated_audit)
        except Exception as exc:
            await self.repository.update(
                audit_id,
                status="failed",
                error_info=str(exc)[:MAX_ERROR_INFO_LENGTH],
                progress={"phase": "failed"},
                completed_at=datetime.now(timezone.utc),
            )
            raise
