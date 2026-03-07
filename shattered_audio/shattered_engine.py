import math
import time

from pyo import *

from shattered_audio.log import get_logger

log = get_logger("engine")


def _mtof(note):
    """MIDI note number to frequency in Hz."""
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _db_to_amp(db: float) -> float:
    """Convert decibels to linear amplitude."""
    return 10.0 ** (db / 20.0)


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
        """Build an expressive melody layer with per-note synthesis.

        Uses individual Fader envelopes per note (pyo's DataTable/TableRead
        amplitude modulation doesn't work correctly in offline mode).

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
        timbre = layer.get("timbre", "glass")

        # Overall layer envelope
        layer_env = self.keep(
            Fader(fadein=fade_in, fadeout=fade_out, dur=self.duration, mul=vol).play()
        )

        beat = self.beat_dur
        has_start_beat = any("start_beat" in n for n in notes)

        # Build each note as an individual oscillator + envelope
        mix = 0
        cursor = 0.0
        for ni, n in enumerate(notes):
            if has_start_beat:
                cursor = float(n.get("start_beat", 0)) * beat

            pitch = float(n.get("pitch", 60))
            beats_n = float(n.get("beats", 1))
            velocity = float(n.get("velocity", 1.0))
            decay_beats = float(n.get("decay", default_decay))
            brightness = float(n.get("brightness", default_brightness))
            vibrato_depth = float(n.get("vibrato", 0))
            slide_to = n.get("slide_to")
            slide_beats = float(n.get("slide_beats", 0)) if slide_to is not None else 0

            hold_dur = beats_n * beat
            slide_dur = slide_beats * beat
            note_total = hold_dur + slide_dur
            decay_dur = decay_beats * beat
            start_time = cursor

            # Per-note amplitude envelope: plays immediately, delayed in output
            note_env = self.keep(
                Fader(fadein=0.01, fadeout=decay_dur,
                      dur=note_total + decay_dur, mul=velocity).play()
            )

            # Frequency with optional slide
            freq_hold = _mtof(pitch)
            if slide_to is not None and slide_dur > 0:
                freq_target = _mtof(slide_to)
                # Use SigTo for smooth glide starting after hold_dur
                freq_sig = self.keep(Sig(freq_hold))
                # Schedule frequency change (approximate: ramp over slide_dur)
                freq_sig_smooth = self.keep(
                    SigTo(freq_sig, time=slide_dur, init=freq_hold)
                )
                # Use CallAfter to trigger the slide at the right time
                def _set_freq(sig=freq_sig, target=freq_target):
                    sig.value = target
                self.keep(CallAfter(_set_freq, hold_dur))
                final_freq = freq_sig_smooth
            else:
                final_freq = freq_hold

            # Vibrato
            if vibrato_depth > 0:
                vib_lfo = self.keep(
                    Sine(freq=5.5, mul=freq_hold * vibrato_depth * 0.0577)
                )
                final_freq = final_freq + vib_lfo

            # Oscillator based on timbre
            if timbre == "sine":
                osc = self.keep(Sine(freq=final_freq, mul=note_env))
            elif timbre == "saw":
                osc = self.keep(SuperSaw(freq=final_freq, detune=0.5, mul=note_env))
            elif timbre == "fm":
                osc = self.keep(FM(carrier=final_freq, ratio=[1.0, 1.001],
                                   index=5, mul=note_env))
            else:  # "glass" default
                osc = self.keep(LFO(freq=final_freq, type=3, mul=note_env))

            # Brightness filter
            cutoff = 200 + brightness * 7800
            filtered = self.keep(MoogLP(osc, freq=cutoff, res=0.3))

            # Time-shift the note to its start position
            if start_time > 0.001:
                note_out = self.keep(Delay(filtered, delay=start_time,
                                           maxdelay=start_time + 0.1))
            else:
                note_out = filtered

            mix = mix + note_out

            if not has_start_beat:
                cursor += hold_dur + slide_dur

        # Apply overall layer envelope
        if mix:
            return mix * layer_env
        return 0

    def _apply_effects(self, signal, effects: list):
        """Apply a chain of effects to a signal.

        Each effect dict has a 'type' key and type-specific parameters.
        Wet/dry mixing is handled per effect via the 'mix' parameter.
        """
        out = signal
        for fx in effects:
            fx_type = fx.get("type")
            mix_amt = float(fx.get("mix", 0.3))

            if fx_type == "reverb":
                wet = self.keep(Freeverb(out, size=fx.get("size", 0.8), bal=1.0))
                out = out * (1 - mix_amt) + wet * mix_amt

            elif fx_type == "delay":
                delay_time = fx.get("time", 0.4)
                feedback = min(0.95, float(fx.get("feedback", 0.5)))
                wet = self.keep(Delay(out, delay=delay_time, feedback=feedback))
                out = out * (1 - mix_amt) + wet * mix_amt

            elif fx_type == "chorus":
                depth = float(fx.get("depth", 1.0))
                feedback = float(fx.get("rate", 0.25))
                wet = self.keep(Chorus(out, depth=depth, feedback=feedback))
                out = out * (1 - mix_amt) + wet * mix_amt

            elif fx_type == "eq":
                low_db = float(fx.get("low", 0))
                mid_db = float(fx.get("mid", 0))
                high_db = float(fx.get("high", 0))
                if low_db != 0:
                    out = self.keep(EQ(out, freq=200, q=0.7, boost=low_db, type=2))
                if mid_db != 0:
                    out = self.keep(EQ(out, freq=1000, q=0.7, boost=mid_db, type=0))
                if high_db != 0:
                    out = self.keep(EQ(out, freq=5000, q=0.7, boost=high_db, type=1))

            elif fx_type == "distortion":
                drive = float(fx.get("drive", 0.3))
                wet = self.keep(Disto(out, drive=drive, slope=0.9))
                out = out * (1 - mix_amt) + wet * mix_amt

            elif fx_type == "compressor":
                thresh = float(fx.get("thresh", -20))
                ratio = float(fx.get("ratio", 4))
                out = self.keep(Compress(out, thresh=thresh, ratio=ratio))

            else:
                log.warning("Unknown effect type %r, skipping", fx_type)

        return out

    def build_layer(self, layer: dict):
        """Dynamically routes and builds a generative audio module."""
        l_type = layer.get("type")
        vol = float(layer.get("vol", 0.5))
        fade_in = float(layer.get("fade_in", 5))
        fade_out = float(layer.get("fade_out", 5))

        if l_type in ("expressive_melody", "synth"):
            audio = self._build_expressive_melody(layer)
            effects = layer.get("effects", [])
            if effects and audio:
                audio = self._apply_effects(audio, effects)
            return audio

        env = self.keep(Fader(fadein=fade_in, fadeout=fade_out, dur=self.duration, mul=vol).play())

        effects = layer.get("effects", [])

        if l_type == "void_bass":
            osc = self.keep(Sine(freq=[layer.get("freq", 40), layer.get("freq", 40) + 0.5], mul=env))
            dist = self.keep(Disto(osc, drive=layer.get("drive", 0.5), slope=0.9))
            audio = self.keep(Degrade(dist, bitdepth=layer.get("bitdepth", 24), srscale=layer.get("srscale", 1.0)))

        elif l_type == "phantom_choir":
            mod = self.keep(BrownNoise(mul=layer.get("mod_depth", 50), add=layer.get("pitch", 1000)))
            metro = self.keep(Cloud(density=layer.get("glitch_density", 5), poly=1).play())
            glitch_env = self.keep(TrigEnv(metro, table=SquareTable(), dur=layer.get("glitch_duration", 0.1), mul=env))
            audio = self.keep(FM(carrier=mod, ratio=layer.get("fm_ratio", [0.5, 0.49]), index=layer.get("fm_index", 10), mul=glitch_env))

        elif l_type == "cathedral_pad":
            lfo = self.keep(Sine(freq=layer.get("rot_speed", 0.05), mul=layer.get("rot_depth", 0.1), add=0.1))
            osc = self.keep(SuperSaw(freq=layer.get("chord", [200, 300, 400]), detune=lfo, mul=env))
            audio = self.keep(MoogLP(osc, freq=env * layer.get("filter_peak", 4000) + 100, res=layer.get("resonance", 0.5)))

        elif l_type == "tape_decay":
            hiss = self.keep(PinkNoise(mul=env * 0.2))
            density = max(0.001, float(layer.get("crackle_density", 5)))
            crackle_metro = self.keep(Metro(time=1.0 / density).play())
            trig_env = self.keep(TrigEnv(crackle_metro, table=CosTable(), dur=0.01, mul=env * 0.8))
            crackle = self.keep(PinkNoise(mul=trig_env))
            audio = self.keep(ButLP(hiss + crackle, freq=3000))

        else:
            log.warning("Unknown layer type %r, returning silence", l_type)
            return 0

        if effects:
            audio = self._apply_effects(audio, effects)
        return audio

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

        reverb.out()

        try:
            self.server.recordOptions(filename=output_filename, fileformat=0, sampletype=0, dur=self.duration)
        except Exception as e:
            log.debug("recordOptions failed (pyo quirk): %s", e)

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
