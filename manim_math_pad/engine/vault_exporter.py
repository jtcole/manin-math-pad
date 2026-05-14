"""Export generated zettel clusters to an Obsidian vault."""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar


@dataclass(slots=True)
class VaultExportResult:
    """Filesystem result for one zettel cluster export."""

    cluster_uid: str
    cluster_path: Path
    created_paths: list[Path] = field(default_factory=list)
    skipped_paths: list[Path] = field(default_factory=list)
    note_count: int = 0

    def as_json(self) -> dict:
        return {
            'cluster_uid': self.cluster_uid,
            'cluster_path': str(self.cluster_path),
            'created_paths': [str(path) for path in self.created_paths],
            'skipped_paths': [str(path) for path in self.skipped_paths],
            'note_count': self.note_count,
        }


class VaultZettelExporter:
    """Write completed zettel clusters as Markdown files in an Obsidian vault."""

    DEFAULT_VAULT_PATH: ClassVar[Path] = Path('/home/cole/vscode_projects/cant_know/Pure Zettel/')

    def __init__(self, vault_path: str | Path | None = None):
        configured_path = vault_path or self._configured_vault_path()
        self.vault_path = Path(configured_path).expanduser()

    def export_cluster(self, cluster) -> VaultExportResult:
        """Export one completed ZettelCluster model instance."""
        if cluster.status != 'completed':
            raise ValueError('Only completed zettel clusters can be exported')

        notes = cluster.zettel_data.get('notes', [])
        domain = cluster.zettel_data.get('domain', 'general')
        cluster_path = self.vault_path / self._cluster_dir_name(cluster)
        cluster_path.mkdir(parents=True, exist_ok=True)

        result = VaultExportResult(
            cluster_uid=str(cluster.uid),
            cluster_path=cluster_path,
            note_count=len(notes),
        )

        for note in notes:
            target_path = cluster_path / self._note_filename(note)
            if target_path.exists():
                result.skipped_paths.append(target_path)
                continue

            target_path.write_text(
                self._render_note(cluster=cluster, note=note, domain=domain),
                encoding='utf-8',
            )
            result.created_paths.append(target_path)

        return result

    def _configured_vault_path(self) -> str | Path:
        value = os.environ.get('MANIM_VAULT_PATH')
        if value:
            return value

        try:
            from django.conf import settings

            if settings.configured:
                return getattr(settings, 'MANIM_VAULT_PATH', self.DEFAULT_VAULT_PATH)
        except Exception:
            return self.DEFAULT_VAULT_PATH

        return self.DEFAULT_VAULT_PATH

    def _cluster_dir_name(self, cluster) -> str:
        created = getattr(cluster, 'created_at', None)
        timestamp = created.strftime('%Y%m%d%H%M%S') if hasattr(created, 'strftime') else 'cluster'
        slug = self._slugify(cluster.topic or 'zettel-cluster')
        return f'{timestamp}_{slug}_{str(cluster.uid)[:8]}'

    def _note_filename(self, note: dict) -> str:
        raw_name = note.get('filename') or note.get('title') or str(uuid.uuid4())
        safe_stem = self._slugify(Path(str(raw_name)).stem)
        if not safe_stem:
            safe_stem = str(uuid.uuid4())
        return f'{safe_stem}.md'

    def _render_note(self, cluster, note: dict, domain: str) -> str:
        body = self._strip_frontmatter(str(note.get('content') or ''))
        frontmatter = self._frontmatter(cluster=cluster, note=note, domain=domain)
        return f'{frontmatter}\n\n{body.lstrip()}'.rstrip() + '\n'

    def _frontmatter(self, cluster, note: dict, domain: str) -> str:
        identity = note.get('filename') or note.get('title') or note.get('content') or str(note)
        note_id = uuid.uuid5(uuid.NAMESPACE_URL, f'manim-math-pad:{cluster.uid}:{identity}')
        created = self._created_iso(cluster)
        safe_domain = self._tag_value(domain or 'general')
        return '\n'.join(
            [
                '---',
                f'id: {note_id}',
                f'created: {created}',
                f'tags: [math, {safe_domain}, zettel]',
                'type: zettel',
                '---',
            ]
        )

    def _created_iso(self, cluster) -> str:
        created = getattr(cluster, 'created_at', None)
        if hasattr(created, 'isoformat'):
            return created.isoformat()
        return datetime.now(timezone.utc).isoformat()

    def _strip_frontmatter(self, content: str) -> str:
        return re.sub(r'\A---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL)

    def _slugify(self, value: str) -> str:
        slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', value.lower()).strip('-')
        return slug[:80]

    def _tag_value(self, value: str) -> str:
        tag = re.sub(r'[^a-zA-Z0-9_-]+', '-', value.lower()).strip('-')
        return tag or 'general'
