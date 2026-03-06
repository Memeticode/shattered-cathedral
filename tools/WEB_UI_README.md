Static Web UI for Shattered Cathedral
=====================================

This file explains how to view the auto-audio-exploration history as a static site.

Generated output
- `artifacts/iter/index.html` — the static gallery page.
- `artifacts/iter/renders/` — directory with WAV and PNG files referenced by the page.

How to generate

Run this from the repository root (activate your virtualenv first if needed):

```bash
python -m tools.web_ui --outdir artifacts/iter --static
```

How to view

- Open `artifacts/iter/index.html` in your browser (double-click or use `start` on Windows).
- The page contains thumbnails, preview links, and download buttons for each iteration's audio and images.

Notes
- Links are relative to the `artifacts/iter` directory and assume `renders/` is present with audio/image files.
- If you want a live server with auto-open, run without `--static`.
