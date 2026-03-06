from pyo import *
import time

class ShatteredEngine:
    def __init__(self, config):
        """Initializes the audio server and stores the config."""
        self.config = config
        self.duration = config.get("global", {}).get("duration", 30)
        self.server = Server().boot()
        
        # We must keep references to all pyo objects so they don't get garbage collected
        self.registry = [] 

    def keep(self, obj):
        """Stores a pyo object in the registry to keep it alive."""
        self.registry.append(obj)
        return obj

    def build_bass(self):
        """Constructs the deep, distorted low-end foundation."""
        c = self.config.get("bass", {})
        if not c.get("enabled", False): return None

        env = self.keep(Fader(fadein=c.get("fade_in", 2), fadeout=c.get("fade_out", 5), dur=self.duration, mul=c.get("volume", 0.7)).play())
        osc = self.keep(Sine(freq=c.get("frequencies", [40, 40.5]), mul=env))
        
        # Distortion and Degradation
        dist = self.keep(Disto(osc, drive=c.get("drive", 0.9), slope=0.95))
        crush = self.keep(Degrade(dist, bitdepth=c.get("bitdepth", 16), srscale=c.get("srscale", 1.0)))
        return crush

    def build_vocals(self):
        """Constructs the glitching, high-frequency FM vocal shards."""
        c = self.config.get("vocals", {})
        if not c.get("enabled", False): return None

        # Chaotic pitch modulation
        mod = self.keep(BrownNoise(mul=c.get("mod_depth", 300), add=c.get("base_pitch", 1500)))
        
        # Glitch triggers
        metro = self.keep(Cloud(density=c.get("glitch_density", 15), poly=1).play())
        env = self.keep(TrigEnv(metro, table=SquareTable(), dur=c.get("glitch_duration", 0.04), mul=c.get("volume", 0.4)))
        
        vocal = self.keep(FM(carrier=mod, ratio=c.get("fm_ratio", [0.25, 0.24]), index=c.get("fm_index", 20), mul=env))
        return vocal

    def build_pad(self):
        """Constructs the swelling, detuning symphonic wall."""
        c = self.config.get("pad", {})
        if not c.get("enabled", False): return None

        env = self.keep(Fader(fadein=c.get("fade_in", 10), fadeout=c.get("fade_out", 5), dur=self.duration, mul=c.get("volume", 0.3)).play())
        
        # Active detuning LFO
        lfo = self.keep(Sine(freq=c.get("rot_speed", 0.05), mul=c.get("rot_depth", 0.5), add=0.1))
        osc = self.keep(SuperSaw(freq=c.get("chord", [200, 300, 450, 600]), detune=lfo, mul=env))
        
        filt = self.keep(MoogLP(osc, freq=env * c.get("filter_peak", 8000) + 100, res=c.get("resonance", 0.9)))
        return filt

    def render(self, output_filename="artifact.wav"):
        """Assembles the mix, applies master effects, and records."""
        print(f"Synthesizing {self.duration} seconds of audio into '{output_filename}'...")
        
        bass = self.build_bass()
        vocals = self.build_vocals()
        pad = self.build_pad()

        # Combine active elements into a master mix
        mix = 0
        if bass: mix += bass
        if vocals: mix += vocals
        if pad: mix += pad

        # Master Void (Delay + Reverb)
        master_config = self.config.get("master_effects", {})
        delay = self.keep(Delay(mix, delay=[0.15, 0.25], feedback=master_config.get("delay_feedback", 0.8)))
        reverb = self.keep(Freeverb(mix + delay, size=master_config.get("reverb_size", 0.95), bal=master_config.get("reverb_mix", 0.8)).out())

        # Start recording
        self.keep(Record(reverb, filename=output_filename, fileformat=0, sampletype=1))
        
        # Play the audio locally while recording
        self.server.start()
        time.sleep(self.duration + 1) # Wait for the duration of the track
        self.server.stop()
        print(f"Artifact saved: {output_filename}")
    