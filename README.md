# Shattered Cathedral — Batch Rendering

This project uses `pyo` to synthesize audio artifacts.

Quick setup (Windows PowerShell):

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt
```

Render examples (offline, no audio playback):

```powershell
# Render specific artifacts (space-separated keys)
.\.venv311\Scripts\python.exe -m shattered_audio.cli 005_the_swarm 006_abyssal_trench --outdir artifacts --parallel 2

# Render all configs
.\.venv311\Scripts\python.exe -m shattered_audio.cli ALL --outdir artifacts --parallel 4

Advanced CLI flags

- `--outfmt`: Output file format (currently only `wav`).
- `--samprate`: Sample rate override (Hz).
- `--duration`: Override artifact duration in seconds.
- `--bitdepth`: Override output bitdepth/sample type.
- `--parallel`: Number of helper processes to run in parallel.
- `--play`: Play audio during rendering (opens audio device; not recommended for batch).
- `--verbose`: Show more helper output.

Example: render one artifact with overriden duration and sample rate:
```powershell
.\.venv311\Scripts\python.exe -m shattered_audio.cli 005_the_swarm --outdir artifacts --duration 10 --samprate 44100
```
```

Notes
- Use `--play` if you want the helper to open your audio device and play the render (not recommended for batch jobs).
- If you encounter occasional non-zero helper exits but the WAV file exists, the main runner treats the artifact as successful as long as the file is present and non-empty. This is a known pyo native-cleanup quirk on some Windows setups.
- `requirements.txt` contains the pinned packages used during development: `pyo==1.0.5`, `wxpython==4.2.1`, `numpy==2.4.2`.
