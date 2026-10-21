from .schema import (
    RedirectGraph,
    RedirectGraphEdge,
    RedirectGraphNode,
    RedirectUrlResult,
)


def build_redirect_graph(
    discovered_urls: list[str],
    results: list[RedirectUrlResult],
    page_edges: list[tuple[str, str]],
) -> RedirectGraph:
    nodes: dict[str, RedirectGraphNode] = {}
    edges: dict[tuple[str, str, str], RedirectGraphEdge] = {}

    for url in discovered_urls:
        nodes[url] = RedirectGraphNode(id=url, url=url, kind="page")

    for source, target in page_edges:
        if source in nodes:
            nodes.setdefault(
                target,
                RedirectGraphNode(id=target, url=target, kind="page"),
            )
            edge = RedirectGraphEdge(source=source, target=target, kind="link")
            edges[(source, target, "link")] = edge

    for result in results:
        nodes[result.url] = RedirectGraphNode(
            id=result.url,
            url=result.url,
            kind="page",
            status=result.final_status,
            error=result.error,
        )
        for hop_number, hop in enumerate(result.hops, start=1):
            target = hop.resolved
            if not target:
                continue
            nodes.setdefault(
                target,
                RedirectGraphNode(
                    id=target,
                    url=target,
                    kind="redirect_target",
                ),
            )
            edges.setdefault(
                (hop.url, target, "redirect"),
                RedirectGraphEdge(
                    source=hop.url,
                    target=target,
                    kind="redirect",
                    status=hop.status,
                    hop=hop_number,
                ),
            )

    return RedirectGraph(nodes=list(nodes.values()), edges=list(edges.values()))
