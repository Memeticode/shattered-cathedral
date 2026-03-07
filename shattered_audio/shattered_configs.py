# shattered_configs.py
# The Library of Artifacts - Version 4.0 (Expressive Melody Engine)

CONFIGS: dict[str, dict[str, object]] = {
    "008_binaural_temple": {
        "global": {
            "bpm": 72,
            "measures": 8,
            "time_sig": [4, 4],
        },
        "master": {
            "reverb_size": 0.99,
            "reverb_mix": 0.9,
            "delay_time": [0.75, 0.85],
            "delay_fb": 0.7,
        },
        "layers": [
            {
                "type": "tape_decay",
                "vol": 0.4,
                "crackle_density": 3,
                "fade_in": 2,
                "fade_out": 10,
            },
            {
                "type": "void_bass",
                "freq": 43.65,
                "drive": 0.1,
                "bitdepth": 24,
                "vol": 0.7,
                "fade_in": 10,
                "fade_out": 15,
            },
            {
                "type": "cathedral_pad",
                "chord": [87.31, 130.81, 174.61],
                "rot_speed": 0.01,
                "filter_peak": 800,
                "vol": 0.4,
                "fade_in": 15,
                "fade_out": 15,
            },
            {
                "type": "cathedral_pad",
                "chord": [261.63, 329.63, 440.0, 523.25],
                "rot_speed": 0.005,
                "filter_peak": 4000,
                "resonance": 0.2,
                "vol": 0.35,
                "fade_in": 20,
                "fade_out": 20,
            },
            {
                "type": "phantom_choir",
                "pitch": 698.46,
                "mod_depth": 5,
                "glitch_density": 1,
                "glitch_duration": 1.5,
                "fm_ratio": [0.5, 0.501],
                "vol": 0.25,
                "fade_in": 25,
                "fade_out": 20,
            },
            {
                "type": "expressive_melody",
                "timbre": "glass",
                "default_decay": 1.5,
                "default_brightness": 0.5,
                "loop": True,
                "vol": 0.35,
                "fade_in": 4,
                "fade_out": 8,
                "notes": [
                    # Phrase 1: gentle opening, ascending
                    {"pitch": 60, "start_beat": 0, "beats": 2, "velocity": 0.6, "brightness": 0.4},
                    {"pitch": 64, "start_beat": 2, "beats": 1.5, "velocity": 0.7, "brightness": 0.5},
                    {"pitch": 67, "start_beat": 3.5, "beats": 1, "velocity": 0.8, "brightness": 0.6,
                     "slide_to": 69, "slide_beats": 0.5},
                    # Phrase 2: arrive at A4, hold and descend
                    {"pitch": 69, "start_beat": 5, "beats": 3, "velocity": 0.9, "brightness": 0.7,
                     "vibrato": 0.15},
                    {"pitch": 67, "start_beat": 8, "beats": 1, "velocity": 0.6, "brightness": 0.5},
                    {"pitch": 64, "start_beat": 9, "beats": 2, "velocity": 0.5, "brightness": 0.4,
                     "slide_to": 62, "slide_beats": 1},
                    # Phrase 3: resolve low, breathe
                    {"pitch": 62, "start_beat": 12, "beats": 1.5, "velocity": 0.7, "brightness": 0.45},
                    {"pitch": 60, "start_beat": 13.5, "beats": 2, "velocity": 0.55, "brightness": 0.35,
                     "vibrato": 0.1},
                    # Phrase 4: leap up with slide
                    {"pitch": 60, "start_beat": 15.5, "beats": 1, "velocity": 0.65, "brightness": 0.4,
                     "slide_to": 72, "slide_beats": 2},
                    {"pitch": 72, "start_beat": 18.5, "beats": 3, "velocity": 0.95, "brightness": 0.8,
                     "vibrato": 0.2},
                    # Phrase 5: descend back home
                    {"pitch": 72, "start_beat": 21.5, "beats": 0.5, "velocity": 0.7,
                     "slide_to": 67, "slide_beats": 1.5},
                    {"pitch": 67, "start_beat": 23.5, "beats": 2, "velocity": 0.6, "brightness": 0.5},
                    {"pitch": 64, "start_beat": 25.5, "beats": 1.5, "velocity": 0.5, "brightness": 0.4,
                     "slide_to": 60, "slide_beats": 1},
                    {"pitch": 60, "start_beat": 28, "beats": 4, "velocity": 0.4, "brightness": 0.3,
                     "vibrato": 0.08, "decay": 3.0},
                ],
            },
        ],
    },
}


# Preset metadata for the web UI — titles, descriptions, and tags for each seed config.
PRESETS: dict[str, dict] = {
    "008_binaural_temple": {
        "title": "Binaural Temple",
        "description": (
            "A slow-building ritual soundscape at 72 BPM. Deep void bass anchors cathedral "
            "pad chords while an expressive glass melody weaves through with slides and "
            "vibrato. Phantom choir voices emerge from the upper register. "
            "Heavy reverb and tape decay create a sense of vast, sacred space."
        ),
        "tags": ["ambient", "binaural", "slow-build", "expressive"],
        "config": CONFIGS["008_binaural_temple"],
    },
}
