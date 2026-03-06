from pyo import *

# Initialize the audio server
# We boot the machine to begin the desecration
s = Server().boot()

# ==========================================
# I. THE ALTAR OF THE 808
# ==========================================
# A deep, 40Hz sine wave pulse. Not a drum, but a sustained, 
# distorted vibration that shakes the foundation.
bass_env = Fader(fadein=5, fadeout=5, dur=30, mul=0.6).play()
bass_osc = Sine(freq=[40, 40.5], mul=bass_env)
# Pushing the sine wave through heavy overdrive to make it guttural
distorted_bass = Disto(bass_osc, drive=0.85, slope=0.9, mul=0.8).out()


# ==========================================
# II. THE BOY AND THE MACHINE (The Vocal)
# ==========================================
# We simulate the boy soprano using an FM synthesizer pushed to extreme
# high frequencies (1000Hz+), representing the heavily autotuned voice.
vocal_pitch_mod = Sine(freq=0.5, mul=200, add=1200) # Unstable, wavering pitch

# The Glitch: We trigger random micro-stutters to represent the "failure" 
# of the autotune algorithm.
glitch_metro = Metro(time=0.08).play() 
glitch_env = TrigEnv(glitch_metro, table=HannTable(), dur=0.05, mul=0.3)

# The glassy, fragile voice shattering into pieces
shattered_vocal = FM(carrier=vocal_pitch_mod, ratio=[0.5, 0.49], index=15, mul=glitch_env)


# ==========================================
# III. GRAFFITI ON THE INFINITE (The Void)
# ==========================================
# We drench the shattered vocal in massive stereo delay and endless reverb.
# This makes the tiny, intimate glitches echo across a vast cathedral.
vocal_delay = Delay(shattered_vocal, delay=[0.25, 0.35], feedback=0.8)
vocal_reverb = Freeverb(vocal_delay + shattered_vocal, size=0.99, damp=0.1, bal=0.85).out()


# ==========================================
# IV. THE SYMPHONIC WALL OF SOUND
# ==========================================
# A dense cluster of sawtooth waves that slowly swells over 20 seconds,
# acting as our "orchestral strings" and "brass," swallowing the mix.
pad_env = Fader(fadein=15, fadeout=5, dur=30, mul=0.2).play()
# Multi-layered, slightly detuned frequencies for a massive choral effect
pad_osc = SuperSaw(freq=[200, 300, 450, 600, 605], detune=0.06, mul=pad_env)

# A Low-Pass filter that slowly opens up, letting the harsh, bright 
# frequencies flood the audio space at the climax
pad_filter = MoogLP(pad_osc, freq=pad_env * 6000 + 200, res=0.7)
pad_reverb = WGVerb(pad_filter, feedback=0.9, cutoff=5000, bal=0.6).out()

print("The Cathedral is shattering. Listening for 30 seconds...")

# Start the audio engine and open the GUI
s.gui(locals())