"""Model adapter: LLM-driven and local-evolution config generation.

Usage:
    from chat import create_client
    client = create_client("openai")
    adapter = ModelAdapter(chat_client=client)
    new_cfg = adapter.propose_config(seed_key='008_binaural_temple')

    # Or without an LLM (local evolution only):
    adapter = ModelAdapter()
    new_cfg = adapter.propose_config(seed_key='008_binaural_temple')
"""
from __future__ import annotations

import json
import math
import random
import re
from datetime import datetime, timezone

from shattered_audio.log import get_logger
from tools.schema_validator import validate_config, SCHEMA

log = get_logger("gen_from_model")

try:
    from shattered_audio.shattered_configs import CONFIGS
except Exception:
    CONFIGS: dict = {}


# ---------------------------------------------------------------------------
# Engine capability summary (for LLM prompts)
# ---------------------------------------------------------------------------

_ENGINE_SUMMARY = """
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
- Beat durations that create rhythmic interest (mix of short and long)
""".strip()


# ---------------------------------------------------------------------------
# Musical constants
# ---------------------------------------------------------------------------

def _mtof(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


_SCALES = {
    "minor":      [0, 2, 3, 5, 7, 8, 10],
    "major":      [0, 2, 4, 5, 7, 9, 11],
    "dorian":     [0, 2, 3, 5, 7, 9, 10],
    "phrygian":   [0, 1, 3, 5, 7, 8, 10],
    "lydian":     [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "whole_tone": [0, 2, 4, 6, 8, 10],
    "pentatonic": [0, 2, 4, 7, 9],
    "blues":      [0, 3, 5, 6, 7, 10],
    "chromatic":  list(range(12)),
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
}

_CHORDS = {
    "minor_triad":  [0, 3, 7],
    "major_triad":  [0, 4, 7],
    "minor_7th":    [0, 3, 7, 10],
    "major_7th":    [0, 4, 7, 11],
    "dom_7th":      [0, 4, 7, 10],
    "sus2":         [0, 2, 7],
    "sus4":         [0, 5, 7],
    "dim":          [0, 3, 6],
    "aug":          [0, 4, 8],
    "min9":         [0, 3, 7, 10, 14],
    "add9":         [0, 4, 7, 14],
    "power":        [0, 7],
    "power_oct":    [0, 7, 12],
    "cluster":      [0, 1, 2],
    "quartal":      [0, 5, 10],
    "quintal":      [0, 7, 14],
}


def _chord_freqs(root_midi: int, chord_name: str) -> list[float]:
    intervals = _CHORDS.get(chord_name, [0, 4, 7])
    return [round(_mtof(root_midi + i), 2) for i in intervals]


def _scale_notes(root_midi: int, scale_name: str, octaves: int = 2) -> list[int]:
    intervals = _SCALES.get(scale_name, _SCALES["minor"])
    notes = []
    for oct in range(octaves):
        for i in intervals:
            notes.append(root_midi + i + 12 * oct)
    return notes


def _snap_to_scale(note: int, scale_notes: list[int]) -> int:
    """Snap a MIDI note to the nearest note in the scale pool."""
    return min(scale_notes, key=lambda n: abs(n - note))


def _pick_expressive_melody(root_midi: int, scale_name: str, length: int = 8) -> list[dict]:
    """Generate a list of expressive note events using a random walk within a scale."""
    pool = _scale_notes(root_midi, scale_name, octaves=2)
    notes = []
    pos = random.randint(0, len(pool) // 2)

    for i in range(length):
        pitch = pool[pos]
        beats = random.choice([0.5, 1, 1, 1.5, 2, 2, 3, 4])
        velocity = round(random.uniform(0.4, 1.0), 2)
        brightness = round(random.uniform(0.3, 0.8), 2)

        note = {"pitch": pitch, "beats": beats, "velocity": velocity, "brightness": brightness}

        # Occasional vibrato on longer notes
        if beats >= 2 and random.random() > 0.5:
            note["vibrato"] = round(random.uniform(0.05, 0.2), 2)

        # Occasional slide to next note
        if i < length - 1 and random.random() > 0.7:
            step = random.choice([-2, -1, 1, 1, 2, 3])
            next_pos = max(0, min(len(pool) - 1, pos + step))
            note["slide_to"] = pool[next_pos]
            note["slide_beats"] = random.choice([0.5, 1, 1.5, 2])
            pos = next_pos
        else:
            step = random.choice([-2, -1, -1, 0, 1, 1, 2, 3])
            pos = max(0, min(len(pool) - 1, pos + step))

        notes.append(note)

    return notes


# ---------------------------------------------------------------------------
# Layer generators
# ---------------------------------------------------------------------------

def _make_cathedral_pad(root_midi: int, chord_name: str, **overrides) -> dict:
    layer = {
        "type": "cathedral_pad",
        "chord": _chord_freqs(root_midi, chord_name),
        "rot_speed": random.choice([0.003, 0.005, 0.01, 0.02, 0.04, 0.08]),
        "rot_depth": round(random.uniform(0.05, 0.3), 3),
        "filter_peak": random.choice([400, 800, 1200, 2000, 3000, 4000, 6000]),
        "resonance": round(random.uniform(0.1, 0.7), 2),
        "vol": round(random.uniform(0.2, 0.5), 2),
        "fade_in": random.choice([3, 5, 8, 10, 15]),
        "fade_out": random.choice([5, 8, 10, 15]),
    }
    layer.update(overrides)
    return layer


def _make_void_bass(root_midi: int = 31, **overrides) -> dict:
    layer = {
        "type": "void_bass",
        "freq": round(_mtof(root_midi), 2),
        "drive": round(random.uniform(0.05, 0.8), 2),
        "vol": round(random.uniform(0.3, 0.7), 2),
        "fade_in": random.choice([3, 5, 8, 10]),
        "fade_out": random.choice([5, 8, 12, 15]),
    }
    layer.update(overrides)
    return layer


def _make_phantom_choir(**overrides) -> dict:
    layer = {
        "type": "phantom_choir",
        "pitch": round(random.choice([
            _mtof(n) for n in range(55, 80)
        ]), 2),
        "mod_depth": round(random.uniform(3, 40), 1),
        "glitch_density": round(random.uniform(0.5, 8), 1),
        "glitch_duration": round(random.uniform(0.05, 2.0), 2),
        "fm_ratio": [round(random.uniform(0.3, 2.0), 2), round(random.uniform(0.3, 2.0), 2)],
        "fm_index": round(random.uniform(2, 20), 1),
        "vol": round(random.uniform(0.15, 0.4), 2),
        "fade_in": random.choice([5, 10, 15, 20]),
        "fade_out": random.choice([5, 10, 15]),
    }
    layer.update(overrides)
    return layer


def _make_expressive_melody(root_midi: int, scale_name: str, **overrides) -> dict:
    melody = _pick_expressive_melody(root_midi, scale_name, length=random.randint(6, 12))
    layer = {
        "type": "expressive_melody",
        "notes": melody,
        "timbre": random.choice(["glass", "glass", "sine", "saw", "fm"]),
        "default_decay": round(random.uniform(0.5, 2.0), 1),
        "default_brightness": round(random.uniform(0.3, 0.6), 2),
        "loop": True,
        "vol": round(random.uniform(0.2, 0.45), 2),
        "fade_in": random.choice([2, 3, 5, 8]),
        "fade_out": random.choice([3, 5, 8]),
    }
    layer.update(overrides)
    return layer


def _make_tape_decay(**overrides) -> dict:
    layer = {
        "type": "tape_decay",
        "crackle_density": round(random.uniform(1, 12), 1),
        "vol": round(random.uniform(0.15, 0.5), 2),
        "fade_in": random.choice([1, 2, 3, 5]),
        "fade_out": random.choice([3, 5, 8]),
    }
    layer.update(overrides)
    return layer


# ---------------------------------------------------------------------------
# Melody mutation (expressive notes)
# ---------------------------------------------------------------------------

def _mutate_expressive_notes(notes: list[dict], scale_name: str = "minor", root: int = 60) -> list[dict]:
    """Apply small, musical mutations to expressive note events."""
    if not notes:
        return _pick_expressive_melody(root, scale_name)

    pool = _scale_notes(root, scale_name, octaves=3)
    notes = [dict(n) for n in notes]

    ops = random.sample([
        "shift_pitches", "vary_velocity", "add_slide", "remove_slide",
        "vary_beats", "extend", "trim", "vary_brightness",
        "reverse_section", "octave_shift_note",
    ], k=random.randint(1, 3))

    for op in ops:
        if op == "shift_pitches" and len(notes) > 1:
            n_shift = min(len(notes), random.randint(1, 3))
            indices = random.sample(range(len(notes)), n_shift)
            for idx in indices:
                shift = random.choice([-2, -1, 1, 2])
                new_pitch = notes[idx]["pitch"] + shift
                notes[idx]["pitch"] = _snap_to_scale(new_pitch, pool)

        elif op == "vary_velocity":
            for n in notes:
                if random.random() > 0.6:
                    n["velocity"] = round(max(0.2, min(1.0, n.get("velocity", 0.8) + random.uniform(-0.2, 0.2))), 2)

        elif op == "add_slide" and len(notes) > 2:
            idx = random.randint(0, len(notes) - 2)
            if "slide_to" not in notes[idx]:
                next_pitch = notes[idx + 1]["pitch"]
                notes[idx]["slide_to"] = next_pitch
                notes[idx]["slide_beats"] = random.choice([0.5, 1, 1.5])

        elif op == "remove_slide":
            slide_indices = [i for i, n in enumerate(notes) if "slide_to" in n]
            if slide_indices:
                idx = random.choice(slide_indices)
                notes[idx].pop("slide_to", None)
                notes[idx].pop("slide_beats", None)

        elif op == "vary_beats":
            for n in notes:
                if random.random() > 0.7:
                    n["beats"] = random.choice([0.5, 1, 1, 1.5, 2, 2, 3, 4])

        elif op == "extend" and len(notes) < 16:
            for _ in range(random.randint(1, 2)):
                last_pitch = notes[-1]["pitch"]
                step = random.choice([-2, -1, 0, 1, 1, 2])
                new_pitch = _snap_to_scale(last_pitch + step, pool)
                notes.append({
                    "pitch": new_pitch,
                    "beats": random.choice([1, 1.5, 2]),
                    "velocity": round(random.uniform(0.4, 0.9), 2),
                    "brightness": round(random.uniform(0.3, 0.7), 2),
                })

        elif op == "trim" and len(notes) > 4:
            notes = notes[:-(random.randint(1, 2))]

        elif op == "vary_brightness":
            for n in notes:
                if random.random() > 0.6:
                    n["brightness"] = round(max(0.1, min(1.0, n.get("brightness", 0.5) + random.uniform(-0.2, 0.2))), 2)

        elif op == "reverse_section" and len(notes) > 4:
            section_len = min(len(notes) - 1, random.randint(3, 5))
            start = random.randint(0, len(notes) - section_len)
            notes[start:start + section_len] = reversed(notes[start:start + section_len])

        elif op == "octave_shift_note" and len(notes) > 1:
            idx = random.randint(0, len(notes) - 1)
            notes[idx]["pitch"] += random.choice([-12, 12])
            notes[idx]["pitch"] = _snap_to_scale(notes[idx]["pitch"], pool)

    return notes


def _mutate_expressive_melody(layer: dict, scale_name: str = "minor", root: int = 60) -> dict:
    """Mutate an expressive_melody layer's notes and optionally its settings."""
    layer = dict(layer)
    if "notes" in layer:
        layer["notes"] = _mutate_expressive_notes(layer["notes"], scale_name, root)

    if random.random() > 0.7:
        layer["default_decay"] = round(max(0.3, min(3.0, layer.get("default_decay", 1.0) + random.uniform(-0.3, 0.3))), 1)

    if random.random() > 0.8:
        layer["timbre"] = random.choice(["glass", "sine", "saw", "fm"])

    return layer


# ---------------------------------------------------------------------------
# Evolution strategies
# ---------------------------------------------------------------------------

_STRATEGIES = [
    "new_harmonic_foundation",
    "add_melodic_layer",
    "melodic_development",
    "tempo_shift",
    "add_texture_layer",
    "strip_to_essentials",
    "transpose_and_reshape",
    "rhythmic_exploration",
    "noise_and_glitch",
    "lush_and_wide",
    "dark_minimal",
    "bright_cascade",
]

_STRATEGY_INTENTS = {
    "new_harmonic_foundation": "Rebuilding the harmonic core with a new chord and voicing",
    "add_melodic_layer": "Introducing an expressive melodic line to weave through the texture",
    "melodic_development": "Developing the melodic line \u2014 small variations on the theme",
    "tempo_shift": "Shifting BPM and rhythmic feel",
    "add_texture_layer": "Adding textural elements for depth and movement",
    "strip_to_essentials": "Stripping back to the essential voices \u2014 less is more",
    "transpose_and_reshape": "Transposing the piece and reshaping the spatial effects",
    "rhythmic_exploration": "Exploring rhythmic patterns and note durations",
    "noise_and_glitch": "Pushing into noisier, glitchier territory",
    "lush_and_wide": "Going for lush, reverb-soaked expansiveness",
    "dark_minimal": "Dark, sparse, and brooding \u2014 subsonic weight",
    "bright_cascade": "Bright cascading tones, shimmering upper harmonics",
}


def _random_master() -> dict:
    return {
        "reverb_size": round(random.uniform(0.4, 0.99), 2),
        "reverb_mix": round(random.uniform(0.3, 0.9), 2),
        "delay_time": [
            round(random.uniform(0.1, 1.2), 2),
            round(random.uniform(0.1, 1.2), 2),
        ],
        "delay_fb": round(random.uniform(0.2, 0.75), 2),
    }


def _random_global() -> dict:
    return {
        "bpm": random.choice([60, 72, 80, 90, 100, 110, 120]),
        "measures": random.choice([4, 8, 8, 12, 16]),
        "time_sig": [4, 4],
    }


def _evolve_config(base_cfg: dict) -> dict:
    """Apply a random evolution strategy to produce a significantly different config."""
    cfg = json.loads(json.dumps(base_cfg))
    layers = cfg.get("layers", [])

    has_melody = any(l.get("type") == "expressive_melody" for l in layers)

    # Weight melodic strategies higher when melody exists
    if has_melody:
        weights = []
        for s in _STRATEGIES:
            if s in ("melodic_development", "tempo_shift"):
                weights.append(3.0)
            elif s in ("rhythmic_exploration",):
                weights.append(0.5)
            else:
                weights.append(1.0)
        strategy = random.choices(_STRATEGIES, weights=weights, k=1)[0]
    else:
        strategy = random.choice(_STRATEGIES)

    intent = _STRATEGY_INTENTS[strategy]
    log.info("Evolution strategy: %s", strategy)

    meta = cfg.get("meta", {})
    root = meta.get("root_midi") or random.choice([36, 38, 40, 41, 43, 45, 47, 48, 50, 52, 53, 55, 57, 59, 60])
    scale = meta.get("scale") or random.choice(list(_SCALES.keys()))
    chord = meta.get("chord") or random.choice(list(_CHORDS.keys()))

    if strategy == "new_harmonic_foundation":
        layers = [l for l in layers if l.get("type") not in ("cathedral_pad",)]
        for octave_offset in random.sample([0, 12, -12, 24], k=random.randint(1, 3)):
            layers.append(_make_cathedral_pad(root + octave_offset, chord))
        has_bass = any(l.get("type") == "void_bass" for l in layers)
        if has_bass:
            for l in layers:
                if l["type"] == "void_bass":
                    l["freq"] = round(_mtof(root - 12), 2)
        cfg["master"] = _random_master()

    elif strategy == "add_melodic_layer":
        layers.append(_make_expressive_melody(root + 12, scale))
        master = cfg.get("master", _random_master())
        master["reverb_mix"] = round(min(0.6, master.get("reverb_mix", 0.5)), 2)
        master["delay_fb"] = round(random.uniform(0.3, 0.6), 2)
        cfg["master"] = master

    elif strategy == "melodic_development":
        melody_layers = [l for l in layers if l.get("type") == "expressive_melody"]
        if melody_layers:
            for l in melody_layers:
                mutated = _mutate_expressive_melody(l, scale, root)
                l.update(mutated)
        else:
            layers.append(_make_expressive_melody(root + 12, scale))

    elif strategy == "tempo_shift":
        g = cfg.get("global", {})
        old_bpm = g.get("bpm", 120)
        direction = random.choice(["faster", "slower", "double", "half"])
        if direction == "faster":
            new_bpm = min(180, int(old_bpm * random.uniform(1.15, 1.4)))
        elif direction == "slower":
            new_bpm = max(40, int(old_bpm * random.uniform(0.65, 0.85)))
        elif direction == "double":
            new_bpm = min(180, old_bpm * 2)
        else:
            new_bpm = max(40, old_bpm // 2)
        g["bpm"] = new_bpm
        cfg["global"] = g
        master = cfg.get("master", _random_master())
        beat_dur = 60.0 / new_bpm
        master["delay_time"] = [
            round(beat_dur * random.uniform(1.0, 3.0), 2),
            round(beat_dur * random.uniform(1.0, 3.0), 2),
        ]
        cfg["master"] = master

    elif strategy == "add_texture_layer":
        choice = random.choice(["tape_decay", "phantom_choir"])
        if choice == "tape_decay":
            layers.append(_make_tape_decay())
        else:
            layers.append(_make_phantom_choir())

    elif strategy == "strip_to_essentials":
        if len(layers) > 2:
            melodic = [l for l in layers if l.get("type") == "expressive_melody"]
            harmonic = [l for l in layers if l.get("type") in ("cathedral_pad", "void_bass")]
            textural = [l for l in layers if l.get("type") in ("tape_decay", "phantom_choir")]
            kept = []
            if melodic:
                kept.append(melodic[0])
            if harmonic:
                kept.append(random.choice(harmonic))
            if not kept and textural:
                kept.append(random.choice(textural))
            if not kept:
                kept = [random.choice(layers)]
            layers = kept
        for l in layers:
            l["vol"] = round(min(0.7, l.get("vol", 0.3) + 0.15), 2)
        cfg["master"] = _random_master()
        cfg["master"]["reverb_size"] = round(random.uniform(0.8, 0.99), 2)

    elif strategy == "transpose_and_reshape":
        semitones = random.choice([-7, -5, -3, -2, 2, 3, 5, 7])
        ratio = 2.0 ** (semitones / 12.0)
        for l in layers:
            if "freq" in l:
                l["freq"] = round(l["freq"] * ratio, 2)
            if "chord" in l:
                l["chord"] = [round(f * ratio, 2) for f in l["chord"]]
            if "pitch" in l:
                l["pitch"] = round(l["pitch"] * ratio, 2)
            if "notes" in l:
                for n in l["notes"]:
                    n["pitch"] = n["pitch"] + semitones
                    if "slide_to" in n:
                        n["slide_to"] = n["slide_to"] + semitones
        cfg["master"] = _random_master()

    elif strategy == "rhythmic_exploration":
        layers = [l for l in layers if l.get("type") != "expressive_melody"]
        for _ in range(random.randint(1, 2)):
            layers.append(_make_expressive_melody(
                root + random.choice([0, 12, 24]), scale,
            ))
        if not any(l.get("type") == "tape_decay" for l in layers):
            layers.append(_make_tape_decay(crackle_density=round(random.uniform(4, 12), 1)))

    elif strategy == "noise_and_glitch":
        layers = [l for l in layers if l.get("type") != "phantom_choir"]
        for _ in range(random.randint(1, 2)):
            layers.append(_make_phantom_choir(
                glitch_density=round(random.uniform(5, 15), 1),
                fm_index=round(random.uniform(10, 25), 1),
                mod_depth=round(random.uniform(20, 60), 1),
            ))
        if not any(l.get("type") == "tape_decay" for l in layers):
            layers.append(_make_tape_decay(crackle_density=round(random.uniform(6, 15), 1)))
        master = cfg.get("master", _random_master())
        master["delay_fb"] = round(random.uniform(0.5, 0.75), 2)
        cfg["master"] = master

    elif strategy == "lush_and_wide":
        layers = [l for l in layers if l.get("type") not in ("cathedral_pad", "void_bass", "tape_decay", "phantom_choir")]
        for octave in random.sample([0, 12, -12], k=random.randint(2, 3)):
            layers.append(_make_cathedral_pad(
                root + octave, chord,
                rot_speed=round(random.uniform(0.002, 0.01), 3),
                filter_peak=random.choice([2000, 3000, 4000, 6000]),
                resonance=round(random.uniform(0.1, 0.3), 2),
            ))
        cfg["master"] = {
            "reverb_size": round(random.uniform(0.92, 0.99), 2),
            "reverb_mix": round(random.uniform(0.7, 0.95), 2),
            "delay_time": [round(random.uniform(0.3, 0.9), 2), round(random.uniform(0.3, 0.9), 2)],
            "delay_fb": round(random.uniform(0.4, 0.65), 2),
        }

    elif strategy == "dark_minimal":
        layers = [l for l in layers if l.get("type") in ("void_bass", "tape_decay", "expressive_melody")]
        if not any(l.get("type") == "void_bass" for l in layers):
            layers.append(_make_void_bass(root - 12, drive=round(random.uniform(0.3, 0.8), 2)))
        else:
            for l in layers:
                if l["type"] == "void_bass":
                    l["drive"] = round(random.uniform(0.3, 0.8), 2)
                    l["vol"] = round(random.uniform(0.5, 0.8), 2)
        if random.random() > 0.4:
            layers.append(_make_cathedral_pad(
                root, random.choice(["minor_triad", "dim", "sus2", "power"]),
                filter_peak=random.choice([300, 500, 800]),
                vol=round(random.uniform(0.15, 0.3), 2),
            ))
        if not any(l.get("type") == "tape_decay" for l in layers):
            layers.append(_make_tape_decay(vol=round(random.uniform(0.1, 0.25), 2)))
        cfg["master"] = {
            "reverb_size": round(random.uniform(0.85, 0.99), 2),
            "reverb_mix": round(random.uniform(0.5, 0.8), 2),
            "delay_time": [round(random.uniform(0.5, 1.5), 2), round(random.uniform(0.5, 1.5), 2)],
            "delay_fb": round(random.uniform(0.3, 0.55), 2),
        }

    elif strategy == "bright_cascade":
        layers = [l for l in layers if l.get("type") not in ("expressive_melody", "cathedral_pad")]
        layers.append(_make_expressive_melody(
            root + 24, scale,
            timbre="glass",
            default_decay=round(random.uniform(1.0, 2.5), 1),
        ))
        layers.append(_make_cathedral_pad(
            root + 12, chord,
            filter_peak=random.choice([4000, 5000, 6000, 8000]),
            rot_speed=round(random.uniform(0.02, 0.08), 3),
        ))
        cfg["master"] = {
            "reverb_size": round(random.uniform(0.7, 0.95), 2),
            "reverb_mix": round(random.uniform(0.4, 0.7), 2),
            "delay_time": [round(random.uniform(0.15, 0.4), 2), round(random.uniform(0.15, 0.4), 2)],
            "delay_fb": round(random.uniform(0.4, 0.65), 2),
        }

    # Cap layers at 6
    if len(layers) > 6:
        layers = random.sample(layers, 6)

    cfg["layers"] = layers

    # Preserve or generate global timing
    if "global" not in cfg:
        cfg["global"] = _random_global()
    else:
        g = cfg["global"]
        g.setdefault("bpm", 120)
        g.setdefault("measures", 8)
        g.setdefault("time_sig", [4, 4])

    cfg.setdefault("meta", {})["generated_at"] = datetime.now(timezone.utc).isoformat()
    cfg["meta"]["strategy"] = strategy
    cfg["meta"]["intent"] = intent
    cfg["meta"]["scale"] = scale
    cfg["meta"]["chord"] = chord
    cfg["meta"]["root_midi"] = root
    return cfg


# ---------------------------------------------------------------------------
# ModelAdapter
# ---------------------------------------------------------------------------

class ModelAdapter:
    def __init__(self, chat_client: "ChatClient | None" = None) -> None:
        from chat.base import ChatClient as _ChatClient  # noqa: F811
        if chat_client is not None and not isinstance(chat_client, _ChatClient):
            raise TypeError(f"Expected ChatClient instance, got {type(chat_client).__name__}")
        self._chat_client = chat_client
        self._iteration = 0
        self._last_eval: dict | None = None

    def _try_parse_json(self, text: str) -> dict | None:
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{(?:.|\n)*\}", text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
            return None

    def propose_config(
        self,
        seed_key: str | None = None,
        seed_cfg: dict | None = None,
        prompt: str | None = None,
        temperature: float = 0.7,
    ) -> dict:
        """Return a new config dict, via API or creative evolution."""
        self._iteration += 1
        seed = None
        if seed_cfg is not None:
            seed = seed_cfg
        elif seed_key and seed_key in CONFIGS:
            seed = CONFIGS[seed_key]
        elif CONFIGS:
            seed = random.choice(list(CONFIGS.values()))

        if self._chat_client is not None:
            example = {
                "global": {"bpm": 90, "measures": 8, "time_sig": [4, 4]},
                "master": {"reverb_size": 0.9, "reverb_mix": 0.6, "delay_time": [0.4, 0.5], "delay_fb": 0.5},
                "layers": [
                    {"type": "cathedral_pad", "chord": [261.63, 329.63], "vol": 0.4, "fade_in": 5, "fade_out": 8},
                    {"type": "expressive_melody", "timbre": "glass", "vol": 0.35, "notes": [
                        {"pitch": 60, "beats": 2, "velocity": 0.7, "brightness": 0.5},
                        {"pitch": 64, "beats": 1, "velocity": 0.8, "slide_to": 67, "slide_beats": 1},
                        {"pitch": 67, "beats": 3, "velocity": 0.9, "vibrato": 0.1},
                    ]},
                ],
            }
            system = (
                "You are a creative config generator for a modular audio engine.\n\n"
                "ENGINE REFERENCE:\n" + _ENGINE_SUMMARY + "\n\n"
                "Be bold and exploratory — vary the number and types of layers, try different "
                "chords, melodies, rhythms, and effects. Each config should sound distinctly different. "
                "Always include an expressive_melody layer with developed per-note events. "
                "Use bpm and measures in the global section (NOT duration). "
                "You must respond ONLY with a single top-level JSON object. "
                "Do NOT include any explanatory text or markdown. Ensure numeric fields are numbers.\n\n"
                "Example output (compact JSON): " + json.dumps(example)
            )
            user_parts = [f"Create a variation for iteration {self._iteration}. Seed config: {str(seed)[:1200]}"]
            if self._last_eval:
                if self._last_eval.get("critique"):
                    user_parts.append(f"\nPrevious critique: {self._last_eval['critique']}")
                if self._last_eval.get("plan"):
                    user_parts.append(f"Direction for this iteration: {self._last_eval['plan']}")
                user_parts.append("Respond to this critique in your config.")
            user_msg = "\n".join(user_parts)
            if prompt:
                user_msg += f"\n\nUser creative direction: {prompt}"

            text = self._chat_client.chat(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                temperature=temperature,
                max_tokens=2000,
            )
            cfg = self._try_parse_json(text)
            if cfg is None:
                raise ValueError("Model returned invalid JSON: %s" % text[:200])
            validate_config(cfg)
            cfg.setdefault("meta", {})["model_generated"] = True
            return cfg

        if seed:
            return _evolve_config(seed)

        # No seed — generate from scratch
        root = random.choice([36, 40, 43, 45, 48, 52, 55, 57, 60])
        scale = random.choice(list(_SCALES.keys()))
        chord = random.choice(list(_CHORDS.keys()))
        layers = [_make_cathedral_pad(root, chord)]
        if random.random() > 0.3:
            layers.append(_make_void_bass(root - 12))
        layers.append(_make_expressive_melody(root + 12, scale))
        if random.random() > 0.6:
            layers.append(_make_phantom_choir())
        if random.random() > 0.5:
            layers.append(_make_tape_decay())
        return {
            "global": _random_global(),
            "master": _random_master(),
            "layers": layers,
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "intent": "Fresh composition from scratch",
                "scale": scale, "chord": chord, "root_midi": root,
            },
        }

    def evaluate_and_plan(
        self,
        cfg: dict | None,
        metrics: dict | None,
        intent: str | None = None,
        config_diff: list[dict] | None = None,
        iteration: int = 1,
        total_iterations: int = 5,
        temperature: float = 0.7,
        user_prompt: str | None = None,
    ) -> dict:
        """Evaluate the latest render and propose next steps."""
        if self._chat_client is not None:
            if user_prompt:
                focus_text = (
                    f'The user has provided this creative direction for the session:\n'
                    f'"{user_prompt}"\n\n'
                    'Evaluate how well the current config achieves this vision. '
                    'Your critique and plan should steer toward this goal while still '
                    'considering melodic quality, expression, and technical execution.\n\n'
                )
            else:
                focus_text = (
                    "Your SOLE FOCUS is the melodic content — the expressive_melody layer's notes. "
                    "Everything else (pads, bass, textures, reverb) exists only to support the melody.\n\n"
                )
            system = (
                "You are a melodic composer critiquing iterations of a generative sound piece.\n\n"
                "ENGINE REFERENCE:\n" + _ENGINE_SUMMARY + "\n\n"
                + focus_text +
                "For this melody, analyze:\n"
                "- PRESENCE: Is there an expressive_melody layer? If not, that's the #1 problem.\n"
                "- SHAPE: Does the melody have contour — does it rise AND fall?\n"
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
            ).format(iter=iteration, total=total_iterations)
            payload = {
                "metrics": metrics or {},
                "intent": intent or "",
                "config": cfg or {},
                "config_changes": config_diff or [],
                "iteration": iteration,
                "total_iterations": total_iterations,
            }
            text = self._chat_client.chat(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(payload)}],
                temperature=temperature,
                max_tokens=800,
            )
            parsed = self._try_parse_json(text)
            if isinstance(parsed, dict):
                result = {
                    "commentary": parsed.get("commentary", ""),
                    "critique": parsed.get("critique", ""),
                    "rationale": parsed.get("rationale", ""),
                    "plan": parsed.get("plan", ""),
                }
                self._last_eval = result
                return result
            raise ValueError("Model produced non-dict JSON: %s" % text[:200])

        result = self._mock_evaluate(cfg, metrics, intent, config_diff, iteration, user_prompt=user_prompt)
        self._last_eval = result
        return result

    @staticmethod
    def _describe_midi(note: int) -> str:
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return f"{names[note % 12]}{note // 12 - 1}"

    def _mock_evaluate(
        self,
        cfg: dict | None,
        metrics: dict | None,
        intent: str | None,
        config_diff: list[dict] | None,
        iteration: int,
        user_prompt: str | None = None,
    ) -> dict:
        """Melody-focused algorithmic critique for expressive_melody layers."""
        commentary = ""
        critique = ""
        rationale = ""
        plan = ""

        layers = cfg.get("layers", []) if cfg and isinstance(cfg, dict) else []
        melody_layers = [l for l in layers if l.get("type") == "expressive_melody"]

        if not melody_layers:
            critique = "No expressive_melody layer — there is no melody. This is ambient texture without narrative direction."
            plan = "Add an expressive_melody layer with varied notes, slides, and per-note dynamics."
            rationale = "First iteration — baseline." if iteration == 1 else "The melody was lost or never existed."
            commentary = "The harmonic and textural layers provide a canvas, but it's blank without a melody."
            return {"commentary": commentary, "critique": critique, "rationale": rationale, "plan": plan}

        ml = melody_layers[0]
        notes = ml.get("notes", [])

        if len(notes) < 3:
            critique = f"Only {len(notes)} notes. This isn't a melody yet — it's a gesture."
            plan = "Extend to 6-8 notes with varied velocities, beat durations, and at least one slide."
            rationale = "Melody too short to analyze."
            commentary = "The seed is there. It just needs to grow."
            return {"commentary": commentary, "critique": critique, "rationale": rationale, "plan": plan}

        # Full melodic analysis
        pitches = [n["pitch"] for n in notes]
        midi_range = max(pitches) - min(pitches)
        intervals = [pitches[i+1] - pitches[i] for i in range(len(pitches) - 1)]
        unique_intervals = len(set(intervals))
        ascending = sum(1 for iv in intervals if iv > 0)
        descending = sum(1 for iv in intervals if iv < 0)
        has_leap = any(abs(iv) >= 5 for iv in intervals)
        has_step = any(1 <= abs(iv) <= 2 for iv in intervals)
        peak_note = self._describe_midi(max(pitches))
        low_note = self._describe_midi(min(pitches))
        note_names = [self._describe_midi(p) for p in pitches]

        # Expression analysis
        velocities = [n.get("velocity", 1.0) for n in notes]
        vel_range = max(velocities) - min(velocities)
        has_slides = any("slide_to" in n for n in notes)
        has_vibrato = any(n.get("vibrato", 0) > 0 for n in notes)
        beat_values = [n.get("beats", 1) for n in notes]
        unique_beats = len(set(beat_values))

        good = []
        if midi_range >= 7:
            good.append(f"range spans {midi_range} semitones ({low_note} to {peak_note})")
        if has_leap and has_step:
            good.append("mixes steps with leaps")
        if ascending > 0 and descending > 0:
            good.append("has contour (rises and falls)")
        if len(notes) >= 6:
            good.append(f"{len(notes)}-note phrase has substance")
        if vel_range >= 0.3:
            good.append("dynamic velocity range adds expression")
        if has_slides:
            good.append("pitch slides add fluidity")
        if has_vibrato:
            good.append("vibrato on sustained notes is expressive")
        if unique_beats >= 3:
            good.append("varied beat durations create rhythmic interest")

        if good:
            commentary = f"Melody [{', '.join(note_names[:6])}{'...' if len(notes) > 6 else ''}]: {'; '.join(good)}."
        else:
            commentary = f"Melody exists: [{', '.join(note_names[:6])}], but nothing stands out as strong yet."

        issues = []
        if midi_range <= 4:
            issues.append((3, f"Range is only {midi_range} semitones ({low_note}-{peak_note}) — claustrophobic."))
        if not has_leap and len(intervals) > 3:
            issues.append((2, "All stepwise motion, no leaps. The melody needs a moment of surprise."))
        if ascending > 0 and descending == 0 and len(intervals) > 3:
            issues.append((3, "Melody only ascends — needs to come back down."))
        if descending > 0 and ascending == 0 and len(intervals) > 3:
            issues.append((3, "Melody only descends — needs upward energy."))
        if vel_range < 0.15:
            issues.append((2, f"Velocity range is only {vel_range:.2f} — all notes sound the same volume. Vary velocity 0.4-1.0."))
        if not has_slides and len(notes) >= 5:
            issues.append((2, "No pitch slides. Add slide_to/slide_beats on 1-2 notes for expressiveness."))
        if unique_beats <= 1:
            issues.append((2, "All notes have the same beat duration — vary between 0.5, 1, 2, 3 for rhythmic interest."))
        if len(notes) < 5:
            issues.append((2, f"Only {len(notes)} notes — extend this into a real phrase."))

        if config_diff and iteration > 1:
            note_changes = [d for d in config_diff if "notes" in d.get("path", "")]
            if not note_changes:
                issues.append((3, "The melody is identical to last iteration — it MUST evolve."))

        issues.sort(key=lambda x: -x[0])
        if issues:
            critique = issues[0][1]
        else:
            critique = "The melody is solid. Refine: try inverting a motif, adding a contrasting B section, or new slides."

        if issues:
            top = issues[0]
            if "range" in top[1].lower() or "claustrophobic" in top[1].lower():
                target = max(pitches) + 7
                plan = f"Add a leap to {self._describe_midi(target)} (MIDI {target}), then step back down."
            elif "ascend" in top[1].lower():
                plan = f"After the peak at {peak_note}, add a descending slide back toward {low_note}."
            elif "descend" in top[1].lower():
                plan = f"Start with an upward gesture. Leap up to {self._describe_midi(min(pitches)+7)} then descend."
            elif "velocity" in top[1].lower():
                plan = "Create a dynamic arc: start soft (0.4-0.5), build to forte (0.9-1.0) at the peak, then fade."
            elif "slide" in top[1].lower():
                plan = "Add a slide between the 2nd and 3rd notes, and another approaching the final note."
            elif "beat duration" in top[1].lower():
                plan = "Vary durations: short pickup notes (0.5 beats), held peak (3-4 beats), medium transitions (1-2 beats)."
            elif "stagnat" in top[1].lower() or "identical" in top[1].lower():
                plan = f"Shift notes 2-4 up by 2 semitones, add a slide to the peak at {peak_note}, vary velocities."
            else:
                plan = f"Extend the phrase by 2-3 notes past {note_names[-1]}, adding a slide and velocity change."
        else:
            plan = (f"The melody is working. Try creating a B section: take the first 3 notes "
                   f"[{', '.join(note_names[:3])}], transpose up a fourth, add slides, and append.")

        if config_diff:
            note_changes = [d for d in config_diff if "notes" in d.get("path", "")]
            if note_changes:
                rationale = f"Melody notes were modified ({len(note_changes)} changes)."
            else:
                rationale = "Non-melodic changes — melody was untouched."
        else:
            rationale = "First iteration — melodic baseline established." if iteration == 1 else "No diff available."

        if user_prompt:
            plan = f"[User direction: {user_prompt}] {plan}"

        return {"commentary": commentary, "critique": critique, "rationale": rationale, "plan": plan}


if __name__ == "__main__":
    adapter = ModelAdapter()
    cfg = adapter.propose_config()
    print(json.dumps(cfg, indent=2))
