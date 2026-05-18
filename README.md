# Manim Math Pad

> _"The product of mathematical thinking is mathematical understanding, not theorems."_ — Yuri Manin

A chat-driven math concept animator using [Manim](https://www.manim.community/), with Obsidian zettel cluster export.

Named for Yuri Manin (1937–2023), the algebraic geometer and mathematician.

## What It Does

1. **Chat** — Describe a math concept in natural language
2. **Animate** — Generates Manim Python scenes and renders them to video
3. **Connect** — Creates structured Obsidian zettel clusters linking concepts together

## Architecture

```
User → Chat API → Scene Generator → Manim Renderer → MP4/GIF
                  ↓
                  Zettel Generator → Obsidian Markdown cluster
```

The app is moving toward a CLI-first artifact engine. The Django UI remains a
viewer and demo surface, while `manim-pad` provides the stable contract that can
be wrapped by CLI Anything or an MCP server.

```
Conversation JSON → manim-pad plan-lesson → lesson artifact folder
Lesson JSON       → manim-pad render-lesson → clips + assembled MP4
Lesson JSON       → manim-pad export-zettel → Obsidian-ready notes
```

### Components

| Component | Purpose |
|---|---|
| `cli.py` | Conversation/lesson artifact commands for bot and MCP use |
| `engine/scene_generator.py` | Concept → Manim Python code (template + LLM) |
| `engine/renderer.py` | Manim Python code → MP4/GIF video |
| `engine/zettel_generator.py` | Concept → Obsidian zettel cluster |
| `views.py` | Django REST API endpoints |
| `models.py` | Session, Message, Animation, ZettelCluster |

### API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/manim/session/` | Create chat session |
| `GET` | `/api/manim/session/<uid>/export/` | Download transcript, scene code, videos, and zettel notes |
| `POST` | `/api/manim/chat/` | Send message, get response |
| `POST` | `/api/manim/animate/` | Generate animation for concept |
| `GET` | `/api/manim/animate/<uid>/` | Check status / download video |
| `POST` | `/api/manim/zettel/` | Generate zettel cluster |
| `GET` | `/api/manim/zettel/<uid>/` | Get cluster details |
| `POST` | `/api/manim/zettel/<uid>/export/` | Export one completed cluster to the vault |
| `POST` | `/api/manim/zettel/export-all/` | Export all completed clusters for a session |

### Built-in Scene Templates

- **Euler's Identity** — Visual proof on the unit circle
- **Derivative Definition** — Animated limit definition
- **Matrix Multiplication** — Element highlighting
- **Fourier Series** — Square wave approximation

Novel concepts fall back to deterministic starter scenes unless LLM generation is enabled.

## Setup

### Prerequisites

```bash
# System dependencies (Ubuntu/Debian)
sudo apt install libcairo2-dev libpango1.0-dev ffmpeg

# Or on macOS
brew install cairo pango ffmpeg

# Python package
pip install manim
```

### Install

```bash
cd manim-math-pad
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/test_engine.py -v
```

### CLI Artifact Workflow

Install the package, then create a lesson artifact folder directly from a
concept or conversation JSON:

```bash
manim-pad plan-lesson \
  --concept "Explain Euler identity visually" \
  --out /tmp/euler-lesson
```

The output folder contains:

```text
lesson.json
lesson.md
storyboard.json
captions.vtt
artifact_manifest.json
clips/
assets/
```

Export zettel markdown from the planned lesson:

```bash
manim-pad export-zettel \
  --lesson /tmp/euler-lesson/lesson.json
```

Preview the render plan without invoking Manim:

```bash
manim-pad render-lesson \
  --lesson /tmp/euler-lesson/lesson.json \
  --dry-run
```

Render for real when Manim and ffmpeg are available:

```bash
manim-pad render-lesson \
  --lesson /tmp/euler-lesson/lesson.json \
  --quality low_quality \
  --fps 15
```

### Django Integration

Add to your site's `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    'manim_math_pad',
]
```

Add to your site's `urls.py`:

```python
urlpatterns = [
    ...
    path('api/manim/', include('manim_math_pad.urls')),
]
```

Run migrations:

```bash
python manage.py migrate
```

The app ships with `manim_math_pad/migrations/0001_initial.py`; downstream sites should not
need to run `makemigrations` for the package models.

### Rendering

Animation requests are queued by default. Run a worker in a second process to complete queued
jobs:

```bash
python manage.py process_render_queue --once --quality low_quality
python manage.py run_render_daemon --poll-interval 5 --quality low_quality
```

For local demos, render inline by setting an environment variable or request field:

```bash
MANIM_RENDER_MODE=inline python manage.py runserver
```

```json
{
  "session_uid": "...",
  "concept": "euler identity",
  "render_mode": "inline",
  "quality": "low_quality"
}
```

Useful render settings:

| Setting | Default | Purpose |
|---|---|---|
| `MANIM_RENDER_MODE` | `queue` | Use `inline` for local synchronous rendering |
| `MANIM_RENDER_QUALITY` | `low_quality` in inline mode | Manim quality preset |
| `MANIM_RENDER_FPS` | `15` in inline mode | Frames per second |
| `MANIM_RENDER_TIMEOUT` | `120` | Render timeout in seconds |
| `MANIM_CMD` | `manim` | Manim executable path |

### LLM Scene Generation

The chat answer layer is deterministic and works without external services. Scene generation
uses built-in templates or deterministic placeholders unless LLM support is explicitly enabled:

```bash
MANIM_ENABLE_LLM=1 MANIM_SCENE_MODEL=gpt-4o-mini python manage.py runserver
```

Set `OPENAI_API_KEY` for OpenAI-compatible chat completions, or `OLLAMA_HOST` for an Ollama
server.

### Zettel Vault Export

Completed zettel clusters can be exported to an Obsidian vault. Configure the target path with:

```bash
MANIM_VAULT_PATH=/home/cole/vscode_projects/cant_know/Pure\ Zettel
```

### As Git Submodule

```bash
cd your-site-repo
git submodule add https://github.com/jtcole/manim-math-pad.git manim_math_pad
git submodule update --init --recursive
```

## Development

### Adding Scene Templates

Edit `manim_math_pad/engine/scene_generator.py` and add to `SCENE_TEMPLATES`:

```python
SCENE_TEMPLATES['your-concept'] = {
    'name': 'YourConceptScene',
    'base_class': 'Scene',
    'description': 'What this animation shows',
    'template': '''
from manim import *

class YourConceptScene(Scene):
    def construct(self):
        # Your Manim code here
        pass
''',
}
```

### Adding Domain Mappings

Edit `CONCEPT_DOMAINS` in `scene_generator.py` or `ZETTEL_TEMPLATES` in `zettel_generator.py`.

## License

MIT
