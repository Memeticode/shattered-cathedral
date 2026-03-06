from pyo import *
import time
import gc

class ShatteredEngine:
    def __init__(self, config, play_audio=True):
        """Initializes the audio server and reads the artifact blueprint.

        play_audio: when False, boot the pyo Server in offline mode so no audio
        device is opened (useful for batch rendering to files).
        """
        self.config = config
        self.duration = config.get("global", {}).get("duration", 30)
        self.play_audio = play_audio
        if play_audio:
            self.server = Server().boot()
        else:
            # Boot server in offline mode to avoid opening audio devices.
            # This uses pyo's 'audio' parameter which accepts 'offline'.
            self.server = Server(audio="offline").boot()
        
        # Registry to prevent Python from garbage collecting our pyo objects
        self.registry = [] 

    def keep(self, obj):
        self.registry.append(obj)
        return obj

    def build_bass(self):
        c = self.config.get("bass", {})
        if not c.get("enabled", False): return None
        env = self.keep(Fader(fadein=c.get("fade_in", 2), fadeout=c.get("fade_out", 5), dur=self.duration, mul=c.get("volume", 0.7)).play())
        osc = self.keep(Sine(freq=c.get("frequencies", [40, 40.5]), mul=env))
        dist = self.keep(Disto(osc, drive=c.get("drive", 0.9), slope=0.95))
        crush = self.keep(Degrade(dist, bitdepth=c.get("bitdepth", 16), srscale=c.get("srscale", 1.0)))
        return crush

    def build_vocals(self):
        c = self.config.get("vocals", {})
        if not c.get("enabled", False): return None
        mod = self.keep(BrownNoise(mul=c.get("mod_depth", 300), add=c.get("base_pitch", 1500)))
        metro = self.keep(Cloud(density=c.get("glitch_density", 15), poly=1).play())
        env = self.keep(TrigEnv(metro, table=SquareTable(), dur=c.get("glitch_duration", 0.04), mul=c.get("volume", 0.4)))
        vocal = self.keep(FM(carrier=mod, ratio=c.get("fm_ratio", [0.25, 0.24]), index=c.get("fm_index", 20), mul=env))
        return vocal

    def build_pad(self):
        c = self.config.get("pad", {})
        if not c.get("enabled", False): return None
        env = self.keep(Fader(fadein=c.get("fade_in", 10), fadeout=c.get("fade_out", 5), dur=self.duration, mul=c.get("volume", 0.3)).play())
        lfo = self.keep(Sine(freq=c.get("rot_speed", 0.05), mul=c.get("rot_depth", 0.5), add=0.1))
        osc = self.keep(SuperSaw(freq=c.get("chord", [200, 300, 450, 600]), detune=lfo, mul=env))
        filt = self.keep(MoogLP(osc, freq=env * c.get("filter_peak", 8000) + 100, res=c.get("resonance", 0.9)))
        return filt

    def build_plucks(self):
        c = self.config.get("plucks", {})
        if not c.get("enabled", False): return None
        metro = self.keep(Metro(time=c.get("speed", 0.15)).play())
        seq = self.keep(Iter(metro, choice=c.get("sequence", [60, 63, 67, 72, 75, 79])))
        freqs = self.keep(MToF(seq))
        # PercTable may not be available in all pyo builds; use CosTable for a
        # percussive-ish envelope that is widely supported.
        env = self.keep(TrigEnv(metro, table=CosTable(), dur=c.get("decay", 0.4), mul=c.get("volume", 0.5)))
        osc = self.keep(LFO(freq=freqs, type=3, mul=env))
        delay = self.keep(Delay(osc, delay=c.get("speed", 0.15) * 1.5, feedback=0.6))
        return osc + delay

    def render(self, output_filename="artifact.wav"):
        print(f"Synthesizing {self.duration} seconds of audio into '{output_filename}'...")
        bass, vocals, pad, plucks = self.build_bass(), self.build_vocals(), self.build_pad(), self.build_plucks()

        mix = 0
        if bass: mix += bass
        if vocals: mix += vocals
        if pad: mix += pad
        if plucks: mix += plucks

        master_config = self.config.get("master_effects", {})
        delay = self.keep(Delay(mix, delay=master_config.get("delay_time", [0.15, 0.25]), feedback=master_config.get("delay_feedback", 0.8)))
        reverb = self.keep(Freeverb(mix + delay, size=master_config.get("reverb_size", 0.95), bal=master_config.get("reverb_mix", 0.8)).out())

        # If running in offline mode, pyo requires recording options including
        # duration to be specified via Server.recordOptions before starting.
        if not getattr(self, "play_audio", True):
            try:
                self.server.recordOptions(filename=output_filename, fileformat=0, sampletype=1, dur=self.duration)
            except Exception:
                pass

        self.keep(Record(reverb, filename=output_filename, fileformat=0, sampletype=1))
        self.server.start()
        time.sleep(self.duration + 1)
        self.server.stop()
        try:
            # Ensure the server is properly shutdown to avoid destructor handle errors on exit
            self.server.shutdown()
        except Exception:
            pass
        try:
            # Remove server reference and force GC to help native resource cleanup
            del self.server
        except Exception:
            pass
        try:
            gc.collect()
        except Exception:
            pass
        print(f"Artifact saved: {output_filename}")
