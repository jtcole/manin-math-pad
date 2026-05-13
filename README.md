# Manin Math Pad

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

### Components

| Component | Purpose |
|---|---|
| `engine/scene_generator.py` | Concept → Manim Python code (template + LLM) |
| `engine/renderer.py` | Manim Python code → MP4/GIF video |
| `engine/zettel_generator.py` | Concept → Obsidian zettel cluster |
| `views.py` | Django REST API endpoints |
| `models.py` | Session, Message, Animation, ZettelCluster |

### API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/manin/session/` | Create chat session |
| `POST` | `/api/manin/chat/` | Send message, get response |
| `POST` | `/api/manin/animate/` | Generate animation for concept |
| `GET` | `/api/manin/animate/<uid>/` | Check status / download video |
| `POST` | `/api/manin/zettel/` | Generate zettel cluster |
| `GET` | `/api/manin/zettel/<uid>/` | Get cluster details |

### Built-in Scene Templates

- **Euler's Identity** — Visual proof on the unit circle
- **Derivative Definition** — Animated limit definition
- **Matrix Multiplication** — Element highlighting
- **Fourier Series** — Square wave approximation

More templates and LLM-driven generation coming in Phase 2.

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
cd manin-math-pad
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/test_engine.py -v
```

### Django Integration

Add to your site's `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    'manin_math_pad',
]
```

Add to your site's `urls.py`:

```python
urlpatterns = [
    ...
    path('api/manin/', include('manin_math_pad.urls')),
]
```

Run migrations:

```bash
python manage.py makemigrations manin_math_pad
python manage.py migrate
```

### As Git Submodule

```bash
cd your-site-repo
git submodule add https://github.com/jtcole/manin-math-pad.git manin_math_pad
git submodule update --init --recursive
```

## Development

### Adding Scene Templates

Edit `manin_math_pad/engine/scene_generator.py` and add to `SCENE_TEMPLATES`:

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