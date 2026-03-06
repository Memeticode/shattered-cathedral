import math
import time

from pyo import *

from shattered_audio.log import get_logger

log = get_logger("engine")


def _mtof(note):
    """MIDI note number to frequency in Hz."""
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


class ShatteredEngine:
    def __init__(self, config: dict, play_audio: bool = False):
        self.config = config
        g = config.get("global", {})

        # BPM / measures timing system
        self.bpm = float(g.get("bpm", 120))
        self.time_sig = g.get("time_sig", [4, 4])
        self.beat_dur = 60.0 / self.bpm
        beats_per_measure = self.time_sig[0]

        if "measures" in g:
            self.duration = float(g["measures"]) * beats_per_measure * self.beat_dur
        else:
            self.duration = float(g.get("duration", 45))

        self.play_audio = bool(play_audio)
        if self.play_audio:
            self.server = Server(audio="pa").boot()
        else:
            self.server = Server(audio="offline").boot()
        self.registry: list = []

    def keep(self, obj):
        """Prevents pyo objects from being garbage collected."""
        self.registry.append(obj)
        return obj

    def _build_expressive_melody(self, layer: dict):
        """Build an expressive melody layer with per-note params and pitch slides.

        Each note in layer["notes"] is a dict:
            pitch       - MIDI note (required)
            beats       - hold duration in beats (required)
            velocity    - amplitude 0-1 (default 1.0)
            decay       - ring-out in beats (default from layer)
            brightness  - filter cutoff scalar 0-1 (default from layer)
            vibrato     - vibrato depth in semitones (default 0)
            slide_to    - target MIDI note for glissando (optional)
            slide_beats - glide duration in beats (optional, requires slide_to)
        """
        notes = layer.get("notes", [])
        if not notes:
            log.warning("expressive_melody layer has no notes")
            return 0

        vol = float(layer.get("vol", 0.5))
        fade_in = float(layer.get("fade_in", 5))
        fade_out = float(layer.get("fade_out", 5))
        default_decay = float(layer.get("default_decay", 1.0))
        default_brightness = float(layer.get("default_brightness", 0.5))
        loop = layer.get("loop", True)
        timbre = layer.get("timbre", "glass")

        env = self.keep(
            Fader(fadein=fade_in, fadeout=fade_out, dur=self.duration, mul=vol).play()
        )

        # --- Compute timeline ---
        # Each note contributes: hold_time + slide_time (if any)
        beat = self.beat_dur
        total_beats = 0.0
        for n in notes:
            total_beats += float(n.get("beats", 1))
            total_beats += float(n.get("slide_beats", 0))
        seq_dur = total_beats * beat

        if seq_dur <= 0:
            log.warning("expressive_melody: sequence duration is 0")
            return 0

        # Control-rate resolution: samples in our data tables
        sr = self.server.getSamplingRate()
        ctrl_rate = 500  # control points per second
        n_points = max(2, int(seq_dur * ctrl_rate))

        # Build frequency, amplitude, and brightness trajectories
        freq_data = [0.0] * n_points
        amp_data = [0.0] * n_points
        bright_data = [0.0] * n_points
        vib_data = [0.0] * n_points

        cursor = 0.0  # current time in seconds
        for ni, n in enumerate(notes):
            pitch = float(n.get("pitch", 60))
            beats = float(n.get("beats", 1))
            velocity = float(n.get("velocity", 1.0))
            decay_beats = float(n.get("decay", default_decay))
            brightness = float(n.get("brightness", default_brightness))
            vibrato = float(n.get("vibrato", 0))
            slide_to = n.get("slide_to")
            slide_beats = float(n.get("slide_beats", 0)) if slide_to is not None else 0

            hold_dur = beats * beat
            slide_dur = slide_beats * beat

            freq_hold = _mtof(pitch)
            freq_target = _mtof(slide_to) if slide_to is not None else freq_hold

            # Note envelope: attack at start, sustain for hold+slide, then decay
            note_total = hold_dur + slide_dur
            decay_dur = decay_beats * beat

            # Fill hold segment
            hold_start_idx = int(cursor * ctrl_rate)
            hold_end_idx = int((cursor + hold_dur) * ctrl_rate)
            for i in range(max(0, hold_start_idx), min(n_points, hold_end_idx)):
                t_in_note = (i / ctrl_rate) - cursor
                freq_data[i] = freq_hold
                # Amplitude envelope: quick attack, sustain, decay at end
                amp_data[i] = velocity * _note_env(t_in_note, note_total, decay_dur)
                bright_data[i] = brightness
                vib_data[i] = vibrato

            # Fill slide segment (linear freq interpolation)
            if slide_dur > 0 and slide_to is not None:
                slide_start_idx = hold_end_idx
                slide_end_idx = int((cursor + hold_dur + slide_dur) * ctrl_rate)
                for i in range(max(0, slide_start_idx), min(n_points, slide_end_idx)):
                    t_in_slide = ((i / ctrl_rate) - cursor - hold_dur) / slide_dur
                    t_in_slide = max(0.0, min(1.0, t_in_slide))
                    freq_data[i] = freq_hold + (freq_target - freq_hold) * t_in_slide
                    t_in_note = (i / ctrl_rate) - cursor
                    amp_data[i] = velocity * _note_env(t_in_note, note_total, decay_dur)
                    bright_data[i] = brightness
                    vib_data[i] = vibrato

            cursor += hold_dur + slide_dur

        # --- Build pyo tables from trajectories ---
        freq_table = self.keep(DataTable(size=n_points, init=freq_data))
        amp_table = self.keep(DataTable(size=n_points, init=amp_data))
        bright_table = self.keep(DataTable(size=n_points, init=bright_data))
        vib_table = self.keep(DataTable(size=n_points, init=vib_data))

        read_freq_hz = 1.0 / seq_dur
        freq_sig = self.keep(
            TableRead(freq_table, freq=read_freq_hz, loop=loop)
        )
        amp_sig = self.keep(
            TableRead(amp_table, freq=read_freq_hz, loop=loop)
        )
        bright_sig = self.keep(
            TableRead(bright_table, freq=read_freq_hz, loop=loop)
        )
        vib_sig = self.keep(
            TableRead(vib_table, freq=read_freq_hz, loop=loop)
        )

        # Vibrato: LFO modulating frequency
        vib_lfo = self.keep(
            Sine(freq=5.5, mul=vib_sig * freq_sig * 0.0577)  # semitone ≈ 5.77% freq
        )
        final_freq = freq_sig + vib_lfo

        # Oscillator based on timbre
        if timbre == "sine":
            osc = self.keep(Sine(freq=final_freq, mul=amp_sig * env))
        elif timbre == "saw":
            osc = self.keep(SuperSaw(freq=final_freq, detune=0.5, mul=amp_sig * env))
        elif timbre == "fm":
            osc = self.keep(FM(carrier=final_freq, ratio=[1.0, 1.001], index=5, mul=amp_sig * env))
        else:  # "glass" default
            osc = self.keep(LFO(freq=final_freq, type=3, mul=amp_sig * env))

        # Brightness filter: scale 0-1 to 200-8000 Hz cutoff
        cutoff = bright_sig * 7800 + 200
        filtered = self.keep(MoogLP(osc, freq=cutoff, res=0.3))

        # Stereo delay for depth
        delay = self.keep(Delay(filtered, delay=seq_dur * 0.1, feedback=0.4))
        return filtered + delay * 0.3

    def build_layer(self, layer: dict):
        """Dynamically routes and builds a generative audio module."""
        l_type = layer.get("type")
        vol = float(layer.get("vol", 0.5))
        fade_in = float(layer.get("fade_in", 5))
        fade_out = float(layer.get("fade_out", 5))

        if l_type == "expressive_melody":
            return self._build_expressive_melody(layer)

        env = self.keep(Fader(fadein=fade_in, fadeout=fade_out, dur=self.duration, mul=vol).play())

        if l_type == "void_bass":
            osc = self.keep(Sine(freq=[layer.get("freq", 40), layer.get("freq", 40) + 0.5], mul=env))
            dist = self.keep(Disto(osc, drive=layer.get("drive", 0.5), slope=0.9))
            return self.keep(Degrade(dist, bitdepth=layer.get("bitdepth", 24), srscale=layer.get("srscale", 1.0)))

        elif l_type == "phantom_choir":
            mod = self.keep(BrownNoise(mul=layer.get("mod_depth", 50), add=layer.get("pitch", 1000)))
            metro = self.keep(Cloud(density=layer.get("glitch_density", 5), poly=1).play())
            glitch_env = self.keep(TrigEnv(metro, table=SquareTable(), dur=layer.get("glitch_duration", 0.1), mul=env))
            return self.keep(FM(carrier=mod, ratio=layer.get("fm_ratio", [0.5, 0.49]), index=layer.get("fm_index", 10), mul=glitch_env))

        elif l_type == "cathedral_pad":
            lfo = self.keep(Sine(freq=layer.get("rot_speed", 0.05), mul=layer.get("rot_depth", 0.1), add=0.1))
            osc = self.keep(SuperSaw(freq=layer.get("chord", [200, 300, 400]), detune=lfo, mul=env))
            return self.keep(MoogLP(osc, freq=env * layer.get("filter_peak", 4000) + 100, res=layer.get("resonance", 0.5)))

        elif l_type == "tape_decay":
            hiss = self.keep(PinkNoise(mul=env * 0.2))
            density = max(0.001, float(layer.get("crackle_density", 5)))
            crackle_metro = self.keep(Metro(time=1.0 / density).play())
            trig_env = self.keep(TrigEnv(crackle_metro, table=CosTable(), dur=0.01, mul=env * 0.8))
            crackle = self.keep(PinkNoise(mul=trig_env))
            filtered_noise = self.keep(ButLP(hiss + crackle, freq=3000))
            return filtered_noise

        log.warning("Unknown layer type %r, returning silence", l_type)
        return 0

    def render(self, output_filename: str = "artifact.wav") -> None:
        log.info("Synthesizing %.1fs of audio -> '%s'", self.duration, output_filename)

        mix = 0
        for layer_config in self.config.get("layers", []):
            layer_audio = self.build_layer(layer_config)
            if layer_audio:
                mix += layer_audio

        master = self.config.get("master", {})
        delay = self.keep(Delay(mix, delay=master.get("delay_time", [0.4, 0.6]), feedback=master.get("delay_fb", 0.7)))
        reverb = self.keep(Freeverb(mix + delay, size=master.get("reverb_size", 0.95), bal=master.get("reverb_mix", 0.8)))

        if self.play_audio:
            reverb.out()

        try:
            self.server.recordOptions(filename=output_filename, fileformat=0, sampletype=1, dur=self.duration)
        except Exception as e:
            log.debug("recordOptions failed (pyo quirk): %s", e)

        self.keep(Record(reverb, filename=output_filename, fileformat=0, sampletype=1))

        self.server.start()
        if self.play_audio:
            time.sleep(self.duration + 1)
        self.server.stop()

        try:
            self.server.shutdown()
        except Exception as e:
            log.debug("server.shutdown failed (pyo quirk): %s", e)

        log.info("Artifact saved: %s", output_filename)


def _note_env(t: float, total_dur: float, decay_dur: float) -> float:
    """Simple note envelope: quick attack, sustain, then decay to 0."""
    attack = 0.01
    if t < 0:
        return 0.0
    if t < attack:
        return t / attack
    sustain_end = total_dur
    if t < sustain_end:
        return 1.0
    if t < sustain_end + decay_dur:
        return 1.0 - (t - sustain_end) / decay_dur
    return 0.0
