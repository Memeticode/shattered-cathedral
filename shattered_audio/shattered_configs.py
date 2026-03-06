# A library of configurations for the ShatteredEngine

CONFIGS = {
    "001_void_collapse": {
        "global": {"duration": 30},
        "bass": {"enabled": True, "volume": 0.8, "frequencies": [38, 39.5], "drive": 0.95, "bitdepth": 4, "srscale": 0.2, "fade_in": 2, "fade_out": 8},
        "vocals": {"enabled": True, "volume": 0.4, "base_pitch": 1500, "mod_depth": 300, "glitch_density": 15, "glitch_duration": 0.04, "fm_ratio": [0.25, 0.24], "fm_index": 20},
        "pad": {"enabled": True, "volume": 0.35, "chord": [200, 300, 450, 600, 605], "rot_speed": 0.05, "rot_depth": 0.8, "filter_peak": 8000, "resonance": 0.95, "fade_in": 10, "fade_out": 5},
        "plucks": {"enabled": False},
        "master_effects": {"delay_time": [0.15, 0.25], "delay_feedback": 0.9, "reverb_size": 1.0, "reverb_mix": 0.9}
    },
    
    "002_ghost_cathedral": {
        "global": {"duration": 30},
        "bass": {"enabled": True, "volume": 0.85, "frequencies": [38, 39.5], "drive": 0.6, "bitdepth": 12, "srscale": 0.85, "fade_in": 4, "fade_out": 6},
        "vocals": {"enabled": True, "volume": 0.5, "base_pitch": 1200, "mod_depth": 50, "glitch_density": 6, "glitch_duration": 0.08, "fm_ratio": [0.5, 0.49], "fm_index": 12},
        "pad": {"enabled": True, "volume": 0.45, "chord": [200, 300, 350, 400, 600], "rot_speed": 0.02, "rot_depth": 0.3, "filter_peak": 4000, "resonance": 0.8, "fade_in": 8, "fade_out": 8},
        "plucks": {"enabled": False},
        "master_effects": {"delay_time": [0.15, 0.25], "delay_feedback": 0.75, "reverb_size": 0.98, "reverb_mix": 0.85}
    },

    "003_clockwork_seraph": {
        "global": {"duration": 30},
        "bass": {"enabled": True, "volume": 0.75, "frequencies": [38, 39.5], "drive": 0.5, "bitdepth": 14, "srscale": 0.9, "fade_in": 5, "fade_out": 8},
        "vocals": {"enabled": True, "volume": 0.35, "base_pitch": 2000, "mod_depth": 20, "glitch_density": 25, "glitch_duration": 0.02, "fm_ratio": [1.0, 1.01], "fm_index": 5},
        "pad": {"enabled": True, "volume": 0.3, "chord": [300, 450, 600, 900, 1200], "rot_speed": 0.01, "rot_depth": 0.1, "filter_peak": 10000, "resonance": 0.4, "fade_in": 12, "fade_out": 5},
        "plucks": {"enabled": True, "volume": 0.6, "speed": 0.125, "decay": 0.3, "sequence": [60, 63, 67, 72, 74, 79, 84]},
        "master_effects": {"delay_time": [0.15, 0.25], "delay_feedback": 0.8, "reverb_size": 0.99, "reverb_mix": 0.85}
    },

    "004_glass_ocean": {
        "global": {"duration": 40}, # Let's make this one longer
        "bass": {"enabled": False}, # No bass. Just floating.
        "vocals": {"enabled": False}, # No vocals.
        "pad": {"enabled": True, "volume": 0.6, "chord": [150, 250, 400, 600, 850], "rot_speed": 0.005, "rot_depth": 0.05, "filter_peak": 3000, "resonance": 0.6, "fade_in": 15, "fade_out": 15},
        "plucks": {"enabled": True, "volume": 0.4, "speed": 0.3, "decay": 1.5, "sequence": [72, 79, 84, 91]}, # Slow, long, bell-like plucks
        "master_effects": {"delay_time": [0.4, 0.6], "delay_feedback": 0.85, "reverb_size": 1.0, "reverb_mix": 0.95}
    },

    "005_the_swarm": {
        "global": {"duration": 20}, # Short and terrifying
        "bass": {"enabled": False},
        "vocals": {
            "enabled": True, 
            "volume": 0.6, 
            "base_pitch": 3000,   # Piercingly high
            "mod_depth": 800,     # Wild pitch swings
            "glitch_density": 50, # Extreme stutter speed
            "glitch_duration": 0.01, 
            "fm_ratio": [0.1, 0.15], 
            "fm_index": 50
        },
        "pad": {"enabled": False}, # No harmonic comfort
        "plucks": {
            "enabled": True, 
            "volume": 0.5, 
            "speed": 0.05,        # Absurdly fast arpeggios
            "decay": 0.05,        # Very sharp and percussive
            "sequence": [72, 73, 72, 71, 74, 75] # Dissonant, chromatic cluster
        },
        "master_effects": {
            "delay_time": [0.05, 0.08], # Slapback delay makes it sound metallic
            "delay_feedback": 0.5, 
            "reverb_size": 0.4,   # Small, claustrophobic space
            "reverb_mix": 0.5
        }
    },

    "006_abyssal_trench": {
        "global": {"duration": 30},
        "bass": {
            "enabled": True, 
            "volume": 0.9, 
            "frequencies": [30, 31.5], # Bone-rattling sub frequencies
            "drive": 0.8, 
            "bitdepth": 6,       # Heavy crushing, but not total static
            "srscale": 0.5, 
            "fade_in": 10, 
            "fade_out": 10
        },
        "vocals": {"enabled": False},
        "pad": {
            "enabled": True, 
            "volume": 0.5, 
            "chord": [100, 150, 200, 250], # Deep, muddy low-mids
            "rot_speed": 0.1,    # Fast, seasick detuning
            "rot_depth": 1.0,    
            "filter_peak": 400,  # Filtered heavily so it sounds muffled
            "resonance": 0.8, 
            "fade_in": 5, 
            "fade_out": 15
        },
        "plucks": {"enabled": False},
        "master_effects": {
            "delay_time": [0.5, 0.6], 
            "delay_feedback": 0.6, 
            "reverb_size": 0.9, 
            "reverb_mix": 0.9
        }
    },

    "007_the_sanctuary": {
        "global": {"duration": 45}, # Giving you more time to exist in the space
        "bass": {
            "enabled": True, 
            "volume": 0.8, 
            "frequencies": [42, 43],   # A warm, grounding hum (around F)
            "drive": 0.1,              # Almost no distortion, just pure sine warmth
            "bitdepth": 24,            # Pristine, high-fidelity audio (no crushing)
            "srscale": 1.0,            # Full sample rate
            "fade_in": 8, 
            "fade_out": 12
        },
        "vocals": {
            "enabled": True, 
            "volume": 0.3, 
            "base_pitch": 800,         # A soft, mid-range choral frequency
            "mod_depth": 10,           # A very gentle, natural-sounding vibrato
            "glitch_density": 2,       # Extremely slow, like distant, solitary breaths
            "glitch_duration": 0.8,    # Long, sustained sighs instead of stutters
            "fm_ratio": [0.5, 0.505],  # Tuned for a warm, glassy harmonic
            "fm_index": 2
        },
        "pad": {
            "enabled": True, 
            "volume": 0.5, 
            "chord": [200, 300, 400, 600, 900], # Open, bright, resolving chord (Fmaj9 voicing)
            "rot_speed": 0.005,        # Incredibly slow detuning, like breathing
            "rot_depth": 0.05,         # Just enough movement to feel alive
            "filter_peak": 2500,       # Warm and rounded, cutting out the harsh highs
            "resonance": 0.2,          # Smooth, not piercing
            "fade_in": 15,             # Rises up very gently
            "fade_out": 15
        },
        "plucks": {
            "enabled": True, 
            "volume": 0.3, 
            "speed": 0.4,              # Slow, drifting pace
            "decay": 2.0,              # Very long, bell-like rings
            "sequence": [65, 69, 72, 77] # F major pentatonic (soothing, floating)
        },
        "master_effects": {
            "delay_time": [0.6, 0.8],  # Long, canyon-like delays
            "delay_feedback": 0.6, 
            "reverb_size": 1.0,        # The walls are infinitely far away
            "reverb_mix": 0.85
        }
    }
}