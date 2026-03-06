# Shattered Cathedral

Generative ambient audio synthesis with AI-directed iterative refinement.

## Quick Start

**Prerequisites:** Python 3.11 (for audio rendering) and Python 3.14 (for orchestration).

```powershell
# 1. Set up both environments
py -3.11 -m venv .venv311
.\.venv311\Scripts\python.exe -m pip install -r requirements-render.txt

py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Launch the live dashboard
.\.venv\Scripts\python.exe -m tools.web_ui --live --outdir artifacts/demo
```

Click **Start Session** in the browser to begin generating. Each iteration renders audio, analyzes it, critiques the melodic content, and evolves the composition.

Works out of the box without an API key. Set `OPENAI_API_KEY` in `.env` for AI-directed generation.

## Other Ways to Run

```powershell
# Render a single artifact
.\.venv311\Scripts\python.exe -m shattered_audio.cli 008_binaural_temple --outdir artifacts

# Automated iteration loop (CLI)
.\.venv\Scripts\python.exe -m tools.iterative_loop --seed 008_binaural_temple --iterations 6 --outdir artifacts/iter --auto --visualize
```

## Project Structure

```
shattered_audio/    Audio engine (Python 3.11, pyo)
tools/              Orchestration, web UI, AI adapter (Python 3.14)
artifacts/          Generated audio and visualizations
```

See [.docs/architecture.md](.docs/architecture.md) for full details.

## License

MIT - see [LICENSE](LICENSE).
