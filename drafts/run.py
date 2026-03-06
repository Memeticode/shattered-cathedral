from shattered_engine import ShatteredEngine
from os import path

# The Configuration Object
config_001 = {
    "global": {
        "duration": 30
    },
    "bass": {
        "enabled": True,
        "volume": 0.8,
        "frequencies": [38, 39.5],
        "drive": 0.95,       # Heavy distortion
        "bitdepth": 4,       # Extreme digital degradation
        "srscale": 0.2,      # Sample rate crushing
        "fade_in": 2,
        "fade_out": 8
    },
    "vocals": {
        "enabled": True,
        "volume": 0.4,
        "base_pitch": 1500,  # High frequency
        "mod_depth": 300,    # Erratic pitch bending
        "glitch_density": 15,# Speed of the stutters
        "glitch_duration": 0.04,
        "fm_ratio": [0.25, 0.24],
        "fm_index": 20
    },
    "pad": {
        "enabled": True,
        "volume": 0.35,
        "chord": [200, 300, 450, 600, 605],
        "rot_speed": 0.05,   # How fast the chord goes out of tune
        "rot_depth": 0.8,    # How severely it detunes
        "filter_peak": 8000,
        "resonance": 0.95,
        "fade_in": 10,
        "fade_out": 5
    },
    "master_effects": {
        "delay_feedback": 0.9,
        "reverb_size": 1.0,  # Infinite space
        "reverb_mix": 0.9
    }
}

# # Run the laboratory
# engine = ShatteredEngine(config_001)
# engine.render(path.join("output", "void_collapse_001.wav"))


# The Configuration Object: 002 "Ghost in the Cathedral"
config_002 = {
    "global": {
        "duration": 30
    },
    "bass": {
        "enabled": True,
        "volume": 0.85,
        "frequencies": [38, 39.5],
        "drive": 0.6,        # Backed off the overdrive for a warmer tone
        "bitdepth": 12,      # 12-bit gives it a vintage sampler warmth, not total destruction
        "srscale": 0.85,     # Very slight sample rate reduction for texture
        "fade_in": 4,
        "fade_out": 6
    },
    "vocals": {
        "enabled": True,
        "volume": 0.5,
        "base_pitch": 1200,  # Slightly lower, more human/choral register
        "mod_depth": 50,     # A gentle flutter instead of erratic screaming
        "glitch_density": 6, # Slower, more rhythmic stutters (like a heartbeat)
        "glitch_duration": 0.08, # Longer grains to hear the "voice"
        "fm_ratio": [0.5, 0.49], # Tuned to harmonic octaves for a glassy chime
        "fm_index": 12
    },
    "pad": {
        "enabled": True,
        "volume": 0.45,
        "chord": [200, 300, 350, 400, 600], # Switched to a moodier, minor-leaning cluster
        "rot_speed": 0.02,   # Very slow, oceanic detuning
        "rot_depth": 0.3,    # Less severe pitch bending, more like old tape warble
        "filter_peak": 4000, # A darker, less blindingly bright swell
        "resonance": 0.8,    # Still singing, but not piercing
        "fade_in": 8,
        "fade_out": 8
    },
    "master_effects": {
        "delay_feedback": 0.75,
        "reverb_size": 0.98, # The cathedral remains vast
        "reverb_mix": 0.85
    }
}

# # Run the laboratory
# engine = ShatteredEngine(config_002)
# engine.render(path.join("output", "ghost_in_the_cathedral_002.wav"))


from shattered_engine import ShatteredEngine

# The Configuration Object: 003 "The Clockwork Seraph"
config_003 = {
    "global": {
        "duration": 30
    },
    "bass": {
        "enabled": True,
        "volume": 0.75,
        "frequencies": [38, 39.5],
        "drive": 0.5,        
        "bitdepth": 14,      # Slightly cleaner to leave room for the plucks
        "srscale": 0.9,     
        "fade_in": 5,
        "fade_out": 8
    },
    "vocals": {
        "enabled": True,
        "volume": 0.35,
        "base_pitch": 2000,  # Pushed even higher into the stratosphere
        "mod_depth": 20,     # Very stable
        "glitch_density": 25,# Extremely fast, like data streams or insects
        "glitch_duration": 0.02, 
        "fm_ratio": [1.0, 1.01], 
        "fm_index": 5
    },
    "pad": {
        "enabled": True,
        "volume": 0.3,
        "chord": [300, 450, 600, 900, 1200], # Open, bright, "holy" voicing
        "rot_speed": 0.01,   # Barely detuning at all
        "rot_depth": 0.1,    
        "filter_peak": 10000,# Let all the light in
        "resonance": 0.4,    
        "fade_in": 12,       # Swells in very slowly
        "fade_out": 5
    },
    "plucks": {
        "enabled": True,
        "volume": 0.6,
        "speed": 0.125,      # Fast, rigid 1/16th note feel
        "decay": 0.3,        # Short and percussive
        "sequence": [60, 63, 67, 72, 74, 79, 84] # C minor 9 ascending arpeggio (MIDI notes)
    },
    "master_effects": {
        "delay_feedback": 0.8,
        "reverb_size": 0.99, # The biggest space possible
        "reverb_mix": 0.85
    }
}

# Run the laboratory
engine = ShatteredEngine(config_003)
engine.render("clockwork_seraph_003.wav")

