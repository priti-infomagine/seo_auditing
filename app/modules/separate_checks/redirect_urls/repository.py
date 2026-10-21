from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .model import RedirectUrlAudit, RedirectUrlEdge, RedirectUrlNode

WRITE_BATCH_SIZE = 250


class RedirectUrlAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        audit_id: UUID,
        domain: str,
        max_urls: int,
        max_depth: int = 5,
        max_hops: int = 10,
    ) -> RedirectUrlAudit:
        audit = RedirectUrlAudit(
            id=audit_id,
            domain=domain,
            max_urls=max_urls,
            max_depth=max_depth,
            max_hops=max_hops,
            status="queued",
            progress={"phase": "queued", "processed": 0},
        )
        self.session.add(audit)
        await self.session.commit()
        await self.session.refresh(audit)
        return audit

    async def replace_graph(
        self,
        audit_id: UUID,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        node_ids: dict[str, UUID] = {}
        node_rows: list[dict[str, Any]] = []
        for node in nodes:
            node_id = uuid4()
            normalized_url = node["normalized_url"]
            if normalized_url in node_ids:
                continue
            node_ids[normalized_url] = node_id
            node_rows.append(
                {
                    "id": node_id,
                    "audit_id": audit_id,
                    **node,
                }
            )

        edge_rows: list[dict[str, Any]] = []
        for edge in edges:
            source_id = node_ids[edge.pop("source_normalized_url")]
            target_id = node_ids[edge.pop("target_normalized_url")]
            edge_rows.append(
                {
                    "id": uuid4(),
                    "audit_id": audit_id,
                    "source_node_id": source_id,
                    "target_node_id": target_id,
                    **edge,
                }
            )

        try:
            await self.session.execute(
                delete(RedirectUrlEdge).where(RedirectUrlEdge.audit_id == audit_id)
            )
            await self.session.execute(
                delete(RedirectUrlNode).where(RedirectUrlNode.audit_id == audit_id)
            )
            await self.session.flush()
            for start in range(0, len(node_rows), WRITE_BATCH_SIZE):
                await self.session.execute(
                    insert(RedirectUrlNode), node_rows[start:start + WRITE_BATCH_SIZE]
                )
            await self.session.flush()
            for start in range(0, len(edge_rows), WRITE_BATCH_SIZE):
                await self.session.execute(
                    insert(RedirectUrlEdge), edge_rows[start:start + WRITE_BATCH_SIZE]
                )
        except Exception:
            await self.session.rollback()
            raise

    async def get_graph(
        self,
        audit_id: UUID,
    ) -> tuple[list[RedirectUrlNode], list[RedirectUrlEdge]]:
        node_result = await self.session.execute(
            select(RedirectUrlNode)
            .where(RedirectUrlNode.audit_id == audit_id)
            .order_by(
                RedirectUrlNode.discovery_order.asc().nulls_last(),
                RedirectUrlNode.normalized_url,
            )
        )
        source_node = aliased(RedirectUrlNode)
        target_node = aliased(RedirectUrlNode)
        edge_result = await self.session.execute(
            select(RedirectUrlEdge)
            .join(source_node, RedirectUrlEdge.source_node_id == source_node.id)
            .join(target_node, RedirectUrlEdge.target_node_id == target_node.id)
            .where(RedirectUrlEdge.audit_id == audit_id)
            .order_by(
                source_node.normalized_url,
                RedirectUrlEdge.edge_type,
                RedirectUrlEdge.position,
                target_node.normalized_url,
            )
        )
        return list(node_result.scalars()), list(edge_result.scalars())

    async def get(self, audit_id: UUID) -> RedirectUrlAudit | None:
        result = await self.session.execute(
            select(RedirectUrlAudit).where(RedirectUrlAudit.id == audit_id)
        )
        return result.scalar_one_or_none()

    async def update(self, audit_id: UUID, **values: Any) -> RedirectUrlAudit | None:
        audit = await self.get(audit_id)
        if audit is None:
            return None
        for name, value in values.items():
            if hasattr(audit, name):
                setattr(audit, name, value)
        audit.updated_at = datetime.now(timezone.utc)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(audit)
        return audit
