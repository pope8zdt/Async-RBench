"""Render trusted public templates for the opt-in loopback preview servers."""
from functools import lru_cache
import importlib.util
from pathlib import Path
import re

SITE = Path(__file__).resolve().parents[3] / 'docs/site'


@lru_cache(maxsize=1)
def _views():
    spec = importlib.util.spec_from_file_location('local_public_views', SITE / 'publication_views.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_public_html(content):
    if b'<!-- MARGIN_BACKGROUND -->' not in content:
        return content
    return _views().render(content.decode('utf-8'), SITE / 'published').encode('utf-8')


def overlay_participation(content, fragment):
    """Replace the flat editorial placeholder; keep older snapshots compatible.

    Both inputs are repository-owned HTML, never submitted evidence. This only
    affects an HTTP response; the source snapshot is never changed.
    """
    pattern = rb'<section id="participate"[^>]*data-submission-status="closed"[^>]*>.*?</section>'
    replaced, count = re.subn(pattern, lambda _: fragment, content, count=1, flags=re.S)
    return replaced if count else content.replace(b'</main>', fragment + b'</main>', 1)
