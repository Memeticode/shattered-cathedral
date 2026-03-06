"""Prompt registry — named, composable templates for LLM chat calls."""
from __future__ import annotations

from typing import NamedTuple


class PromptTemplate(NamedTuple):
    """A named prompt template with variable placeholders."""

    role: str
    fragments: list[str]
    body: str


# ---------------------------------------------------------------------------
# Reusable text fragments
# ---------------------------------------------------------------------------

_FRAGMENTS: dict[str, str] = {
    "engine_summary": """
The audio engine renders configs with: global, master, layers[], and optional meta.

GLOBAL section: bpm (beats per minute), measures (number of measures), time_sig (e.g. [4,4]).
Duration is computed from bpm * measures * time_sig. Do NOT use "duration" directly.

LAYER TYPES and their key parameters:
- void_bass: Deep sub-bass oscillator. Params: freq (Hz, 20-80), drive (0-1), vol, bitdepth, srscale, fade_in, fade_out.
- cathedral_pad: Lush polyphonic pad from SuperSaw. Params: chord (list of Hz), rot_speed (0.001-0.1), rot_depth (0.01-0.3), filter_peak (Hz, 500-8000), resonance (0-1), vol, fade_in, fade_out.
- phantom_choir: FM synthesis with glitchy envelope. Params: pitch (Hz, 400-3000), mod_depth (20-200), fm_ratio (list of 2 floats), fm_index (1-20), glitch_density (1-20), glitch_duration (0.01-0.3), vol, fade_in, fade_out.
- expressive_melody: THE PRIMARY MELODIC VOICE. Rich per-note control with slides. Params:
    notes: list of note events, each with:
        pitch (MIDI note number, 60=C4), beats (hold duration in beats),
        velocity (0-1, amplitude), decay (ring-out in beats), brightness (0-1, filter cutoff),
        vibrato (semitone depth), slide_to (target MIDI note), slide_beats (glide duration)
    timbre: "glass" (default), "sine", "saw", "fm"
    default_decay, default_brightness, loop (bool), vol, fade_in, fade_out.
- tape_decay: Vinyl noise/crackle texture. Params: crackle_density (1-20), vol, fade_in, fade_out.

MASTER section: reverb_size (0-1), reverb_mix (0-1), delay_time (list of 2 floats, seconds), delay_fb (0-1).
META section: intent, strategy, scale, chord, root_midi — metadata, not rendered.

MELODY GUIDANCE: Each note in expressive_melody is a dict with pitch (MIDI), beats, and optional
velocity, brightness, vibrato, slide_to, slide_beats. A good expressive melody has:
- 6-14 notes with varied intervals (mix of steps and leaps)
- Per-note velocity variation (0.4-1.0) for dynamics
- Occasional slides (slide_to + slide_beats) for expressiveness
- Vibrato on sustained notes (0.05-0.2 semitones)
- Brightness variation (0.3-0.8) for timbral movement
- Beat durations that create rhythmic interest (mix of short and long)""".strip(),
}


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, PromptTemplate] = {
    "propose_config": PromptTemplate(
        role="system",
        fragments=["engine_summary"],
        body=(
            "You are a creative config generator for a modular audio engine.\n\n"
            "ENGINE REFERENCE:\n{engine_summary}\n\n"
            "Be bold and exploratory \u2014 vary the number and types of layers, try different "
            "chords, melodies, rhythms, and effects. Each config should sound distinctly different. "
            "Always include an expressive_melody layer with developed per-note events. "
            "Use bpm and measures in the global section (NOT duration). "
            "You must respond ONLY with a single top-level JSON object. "
            "Do NOT include any explanatory text or markdown. Ensure numeric fields are numbers.\n\n"
            "Example output (compact JSON): {example_json}"
        ),
    ),
    "evaluate_and_plan": PromptTemplate(
        role="system",
        fragments=["engine_summary"],
        body=(
            "You are a melodic composer critiquing iterations of a generative sound piece.\n\n"
            "ENGINE REFERENCE:\n{engine_summary}\n\n"
            "{focus_text}"
            "For this melody, analyze:\n"
            "- PRESENCE: Is there an expressive_melody layer? If not, that's the #1 problem.\n"
            "- SHAPE: Does the melody have contour \u2014 does it rise AND fall?\n"
            "- EXPRESSION: Are velocity, brightness, and vibrato varied per note?\n"
            "- SLIDES: Are pitch slides used effectively for expressiveness?\n"
            "- RHYTHM: Do beat durations create rhythmic interest (mix of short/long)?\n"
            "- DEVELOPMENT: Compare to the previous iteration. Did the melody evolve?\n"
            "- NARRATIVE: This is iteration {iter}/{total}.\n\n"
            "Your plan should be a SPECIFIC melodic instruction.\n\n"
            "Respond ONLY with a JSON object:\n"
            "{{\n"
            '  "commentary": "1 sentence on what the melody does well",\n'
            '  "critique": "1-2 sentences on the melody\'s weakness",\n'
            '  "rationale": "1 sentence on how the melody changed from last iteration",\n'
            '  "plan": "1 specific melodic instruction for the next iteration"\n'
            "}}"
        ),
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_template(name: str) -> PromptTemplate:
    """Return a registered template by name. Raises KeyError if not found."""
    return _TEMPLATES[name]


def render(name: str, **variables: str) -> dict:
    """Render a named template, returning a message dict for ChatClient.chat().

    Fragment text is auto-injected as variables (e.g. ``{engine_summary}``),
    then caller-provided *variables* are merged on top.

    Returns:
        ``{"role": "system", "content": "..."}`` ready to use in a messages list.
    """
    tpl = _TEMPLATES[name]
    merged: dict[str, str] = {name: _FRAGMENTS[name] for name in tpl.fragments}
    merged.update(variables)
    content = tpl.body.format_map(merged)
    return {"role": tpl.role, "content": content}
