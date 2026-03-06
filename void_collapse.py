from pyo import *

# Booting the void
s = Server().boot()

# ==========================================
# I. THE PROFANE OVERDRIVE (The 808)
# ==========================================
# A deep pulse that gets aggressively clipped and bitcrushed.
bass_env = Fader(fadein=2, fadeout=8, dur=30, mul=0.7).play()
bass_osc = Sine(freq=[38, 39.5], mul=bass_env)

# Extreme distortion
distorted_bass = Disto(bass_osc, drive=0.95, slope=0.99, mul=0.9)
# The heartbeat starts to fail: we crush the bit depth down to 4-bit
crushed_bass = Degrade(distorted_bass, bitdepth=4, srscale=0.2).out()


# ==========================================
# II. THE DIGITAL ASPHYXIATION (The Vocal)
# ==========================================
# Brownian noise creates unpredictable, wandering pitch shifts (the raw emotion)
erratic_mod = BrownNoise(mul=300, add=1500) 

# The stuttering becomes completely randomized and chaotic
chaos_metro = Cloud(density=15, poly=1).play()
chaos_env = TrigEnv(chaos_metro, table=SquareTable(), dur=0.04, mul=0.4)

# The glassy voice, now being torn apart by erratic modulation
shattered_vocal = FM(carrier=erratic_mod, ratio=[0.25, 0.24], index=20, mul=chaos_env)

# Drowning it in a delay that feeds back into itself (the echoing cry)
vocal_delay = Delay(shattered_vocal, delay=[0.1, 0.4], feedback=0.95)
vocal_reverb = Freeverb(vocal_delay + shattered_vocal, size=1.0, damp=0.0, bal=0.9).out()


# ==========================================
# III. THE SYMPHONIC ROT (The Wall of Sound)
# ==========================================
# The pad enters slowly, but an LFO actively pulls it out of tune over time.
pad_env = Fader(fadein=10, fadeout=10, dur=30, mul=0.3).play()

# A slow sine wave that increases the detuning effect as the song progresses
rot_lfo = Sine(freq=0.05, mul=0.5, add=0.1)
pad_osc = SuperSaw(freq=[200, 300, 450, 600, 605], detune=rot_lfo, mul=pad_env)

# The filter resonance is pushed to the brink, making it scream
pad_filter = MoogLP(pad_osc, freq=pad_env * 8000 + 100, res=0.95)
pad_reverb = WGVerb(pad_filter, feedback=0.99, cutoff=4000, bal=0.8).out()

print("The void is open. Generating absolute chaos for 30 seconds...")

# Start the audio engine and open the GUI
s.gui(locals())