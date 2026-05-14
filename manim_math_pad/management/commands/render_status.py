"""Report Manim Math Pad render queue status."""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db.models import Count

from ...models import Animation


class Command(BaseCommand):
    """Show queued, active, completed, and failed render counts."""

    help = 'Show Manim Math Pad animation render queue status.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Output machine-readable JSON.')
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Number of queued or active jobs to list.',
        )

    def handle(self, *args, **options):
        counts = {status: 0 for status, _label in Animation.STATUS_CHOICES}
        counts.update(
            {
                row['status']: row['count']
                for row in Animation.objects.values('status').annotate(count=Count('id'))
            }
        )

        active_jobs = list(
            Animation.objects.filter(status__in=['pending', 'generating', 'rendering'])
            .order_by('created_at')[: options['limit']]
            .values('uid', 'concept', 'status', 'created_at')
        )
        failed_jobs = list(
            Animation.objects.filter(status='failed')
            .order_by('-completed_at', '-created_at')[: options['limit']]
            .values('uid', 'concept', 'error_message', 'completed_at')
        )

        if options['json']:
            self.stdout.write(
                json.dumps(
                    {
                        'counts': counts,
                        'active_jobs': self._serialize_jobs(active_jobs),
                        'failed_jobs': self._serialize_jobs(failed_jobs),
                    },
                    indent=2,
                    default=str,
                )
            )
            return

        self.stdout.write('Render queue status')
        for status, count in counts.items():
            self.stdout.write(f'  {status}: {count}')

        if active_jobs:
            self.stdout.write('\nActive queue:')
            for job in active_jobs:
                self.stdout.write(f'  {job["uid"]}  {job["status"]}  {job["concept"]}')

        if failed_jobs:
            self.stdout.write('\nRecent failures:')
            for job in failed_jobs:
                error = (job.get('error_message') or '').splitlines()[0][:120]
                self.stdout.write(f'  {job["uid"]}  {job["concept"]}  {error}')

    def _serialize_jobs(self, jobs: list[dict]) -> list[dict]:
        serialized = []
        for job in jobs:
            serialized.append({key: str(value) for key, value in job.items()})
        return serialized
