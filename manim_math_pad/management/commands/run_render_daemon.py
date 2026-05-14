"""Run a long-lived Manim Math Pad render worker."""
from __future__ import annotations

import logging
import signal
import time
from collections.abc import Callable

from django.core.management.base import BaseCommand

from .process_render_queue import Command as ProcessRenderQueueCommand

logger = logging.getLogger(__name__)

SignalHandler = Callable[[int, object], None] | int | None


class Command(BaseCommand):
    """Poll the render queue continuously and process one animation at a time."""

    help = 'Run a Manim Math Pad render daemon.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_requested = False
        self._previous_handlers: dict[int, SignalHandler] = {}

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Process at most one pending animation and exit.',
        )
        parser.add_argument(
            '--poll-interval',
            type=float,
            default=5.0,
            help='Seconds to sleep between queue polls.',
        )
        parser.add_argument(
            '--quality',
            default='medium_quality',
            choices=['low_quality', 'medium_quality', 'high_quality', 'production_quality'],
            help='Manim quality preset.',
        )
        parser.add_argument('--fps', type=int, default=30, help='Rendered frames per second.')
        parser.add_argument(
            '--timeout',
            type=int,
            default=120,
            help='Maximum seconds allowed for each Manim render.',
        )
        parser.add_argument(
            '--manim-cmd',
            default='manim',
            help='Manim executable path.',
        )
        parser.add_argument(
            '--scene-model',
            default=None,
            help='LLM model to use if an animation is missing scene code.',
        )

    def handle(self, *args, **options):
        self._install_signal_handlers()
        self.stdout.write('Starting Manim render daemon')

        try:
            while not self._stop_requested:
                did_work = self._process_one(options)

                if options['once']:
                    if not did_work:
                        self.stdout.write('No pending animations.')
                    return

                if not did_work:
                    self.stdout.write(
                        f'No pending animations. Sleeping {options["poll_interval"]:g}s.'
                    )
                    self._sleep(options['poll_interval'])
        finally:
            self._restore_signal_handlers()

        self.stdout.write('Manim render daemon stopped gracefully.')

    def _process_one(self, options: dict) -> bool:
        processor = ProcessRenderQueueCommand()
        processor.stdout = self.stdout
        processor.stderr = self.stderr
        processor.style = self.style

        animation = processor._claim_next_animation()
        if not animation:
            return False

        logger.info('Render daemon claimed animation %s', animation.uid)
        processor._process_animation(animation, options)
        return True

    def _install_signal_handlers(self) -> None:
        for signum in (signal.SIGTERM, signal.SIGINT):
            self._previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handle_shutdown_signal)

    def _restore_signal_handlers(self) -> None:
        for signum, handler in self._previous_handlers.items():
            signal.signal(signum, handler)
        self._previous_handlers.clear()

    def _handle_shutdown_signal(self, signum: int, frame: object) -> None:
        logger.info('Received signal %s; render daemon will stop after current job', signum)
        self.stdout.write(
            self.style.WARNING(
                f'Received signal {signum}; stopping after the current render job.'
            )
        )
        self._stop_requested = True

    def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, seconds)
        while not self._stop_requested and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.25, remaining))
