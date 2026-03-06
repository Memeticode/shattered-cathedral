"""JSON Schema validator for generator configs."""
from __future__ import annotations

import jsonschema

_NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "pitch": {"type": "number"},
        "beats": {"type": "number"},
        "velocity": {"type": "number", "minimum": 0, "maximum": 1},
        "decay": {"type": "number"},
        "brightness": {"type": "number", "minimum": 0, "maximum": 1},
        "vibrato": {"type": "number", "minimum": 0},
        "slide_to": {"type": "number"},
        "slide_beats": {"type": "number"},
    },
    "required": ["pitch", "beats"],
    "additionalProperties": False,
}

SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "global": {
            "type": "object",
            "properties": {
                "bpm": {"type": "number"},
                "measures": {"type": "number"},
                "time_sig": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "duration": {"type": "number"},
                "samprate": {"type": "integer"},
            },
            "additionalProperties": True,
        },
        "master": {
            "type": "object",
            "properties": {
                "reverb_size": {"type": "number"},
                "reverb_mix": {"type": "number"},
                "delay_time": {"oneOf": [{"type": "array"}, {"type": "number"}]},
                "delay_fb": {"type": "number"},
            },
            "additionalProperties": True,
        },
        "layers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "vol": {"type": "number"},
                    "fade_in": {"type": "number"},
                    "fade_out": {"type": "number"},
                    "notes": {
                        "type": "array",
                        "items": _NOTE_SCHEMA,
                    },
                },
                "required": ["type"],
                "additionalProperties": True,
            },
        },
        "post": {
            "type": "object",
            "properties": {
                "normalize": {"type": "boolean"},
                "target_lufs": {"type": "number"},
                "normalize_mode": {"type": "string", "enum": ["integrated", "true_peak"]},
            },
            "additionalProperties": True,
        },
        "workflow": {
            "type": "object",
            "properties": {
                "recompose": {"type": "boolean"},
                "recompose_prompt": {"type": "string"},
                "jump_to": {"type": "string"},
            },
            "additionalProperties": True,
        },
    },
    "required": ["layers"],
    "additionalProperties": True,
}


def validate_config(cfg: dict) -> None:
    """Validate cfg against the SCHEMA. Raises jsonschema.ValidationError on failure."""
    jsonschema.validate(instance=cfg, schema=SCHEMA)


if __name__ == "__main__":
    import json, sys

    if len(sys.argv) < 2:
        print("Usage: schema_validator.py config.json")
        sys.exit(2)
    with open(sys.argv[1], "r", encoding="utf8") as fh:
        cfg = json.load(fh)
    try:
        validate_config(cfg)
        print("OK")
    except Exception as e:
        print("INVALID:", e)
        raise
