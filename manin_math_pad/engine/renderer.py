"""
Manim Scene Renderer.

Renders Manim scene code to video using the `manim` CLI.
Runs as a subprocess to isolate rendering failures.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    """Result of a Manim rendering job."""
    success: bool
    video_path: Path | None = None
    thumbnail_path: Path | None = None
    duration_seconds: float | None = None
    error_message: str = ''
    metadata: dict | None = None


class ManimRenderer:
    """Render Manim scenes to video.

    Uses the Manim Community CLI (`manim`) to render scene Python files
    to MP4 video. Rendering is done in a temporary directory and the
    output is moved to the media storage location.
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        quality: str = 'medium_quality',
        format: str = 'mp4',
        fps: int = 30,
        manim_cmd: str = 'manim',
    ):
        """
        Args:
            output_dir: Directory for rendered output. Defaults to MEDIA_ROOT/manin/
            quality: Manim quality preset.
            format: Output format (mp4, gif)
            fps: Frames per second
            manim_cmd: Path to manim executable
        """
        self.output_dir = Path(output_dir) if output_dir else None
        self.quality = quality
        self.format = format
        self.fps = fps
        self.manim_cmd = manim_cmd

    def render(
        self,
        scene_code: str,
        scene_name: str,
        job_uid: str | None = None,
        timeout: int = 120,
    ) -> RenderResult:
        """Render a Manim scene to video.

        Args:
            scene_code: Python source code containing the Manim scene class.
            scene_name: Name of the scene class to render.
            job_uid: Unique identifier for this rendering job (used for output naming).
            timeout: Maximum seconds to wait for rendering.

        Returns:
            RenderResult with video path and metadata, or error details.
        """
        job_uid = job_uid or str(uuid.uuid4())

        with tempfile.TemporaryDirectory(prefix=f'manim_{job_uid}_') as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Write scene to temp file
            scene_file = tmpdir_path / f'scene_{job_uid}.py'
            scene_file.write_text(scene_code, encoding='utf-8')

            # Build manim command
            cmd = [
                self.manim_cmd,
                str(scene_file),
                scene_name,
                f'-{self.quality[0]}',  # -l, -m, -h, -p
                '--format', self.format,
                '--fps', str(self.fps),
                '--media_dir', str(tmpdir_path / 'media'),
                '--verbose', 'WARNING',
            ]

            logger.info(f'Rendering Manim scene {scene_name} (job {job_uid})')
            logger.debug(f'Command: {" ".join(cmd)}')

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(tmpdir_path),
                )
            except subprocess.TimeoutExpired:
                return RenderResult(
                    success=False,
                    error_message=f'Rendering timed out after {timeout}s',
                )
            except FileNotFoundError:
                return RenderResult(
                    success=False,
                    error_message=f'manim not found at {self.manim_cmd}. Is Manim installed?',
                )

            if result.returncode != 0:
                error = result.stderr or result.stdout or f'Exit code {result.returncode}'
                logger.error(f'Manim render failed: {error}')
                return RenderResult(
                    success=False,
                    error_message=error[:2000],
                )

            # Find the rendered video
            media_dir = tmpdir_path / 'media' / 'videos' / scene_file.stem / self.quality
            video_files = list(media_dir.glob(f'*.{self.format}')) if media_dir.exists() else []

            if not video_files:
                # Try broader search
                root_media_dir = tmpdir_path / 'media'
                video_files = (
                    list(root_media_dir.rglob(f'*.{self.format}'))
                    if root_media_dir.exists()
                    else []
                )

            if not video_files:
                return RenderResult(
                    success=False,
                    error_message='Rendering completed but no output video found',
                )

            source_video = video_files[0]

            # Move to output directory if specified
            thumbnail_path = None
            if self.output_dir:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                dest_video = self.output_dir / f'{job_uid}.{self.format}'
                dest_video.write_bytes(source_video.read_bytes())
                final_path = dest_video

                thumbnail_path = self._create_thumbnail(
                    final_path,
                    self.output_dir / f'{job_uid}.jpg',
                )
            else:
                final_path = source_video

            logger.info(f'Rendered {scene_name} → {final_path}')

            return RenderResult(
                success=True,
                video_path=final_path,
                thumbnail_path=thumbnail_path,
                duration_seconds=None,  # TODO: probe with ffprobe
                metadata={
                    'scene_name': scene_name,
                    'quality': self.quality,
                    'format': self.format,
                    'fps': self.fps,
                    'file_size_bytes': final_path.stat().st_size if final_path.exists() else 0,
                },
            )

    def _create_thumbnail(self, video_path: Path, thumbnail_path: Path) -> Path | None:
        """Extract a still frame with ffmpeg when available."""
        cmd = [
            'ffmpeg',
            '-y',
            '-loglevel',
            'error',
            '-ss',
            '00:00:01',
            '-i',
            str(video_path),
            '-frames:v',
            '1',
            str(thumbnail_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning('Could not create thumbnail for %s: %s', video_path, exc)
            return None

        if result.returncode != 0 or not thumbnail_path.exists():
            logger.warning(
                'Could not create thumbnail for %s: %s',
                video_path,
                (result.stderr or result.stdout or f'exit code {result.returncode}')[:500],
            )
            return None

        return thumbnail_path
