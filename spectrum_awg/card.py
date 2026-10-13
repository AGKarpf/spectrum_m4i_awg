"""Configure and operate the Spectrum M4i.6631-x8 AWG.
Translate declarative configuration into SPCM registers for clocks, triggers,
channels, digital outputs and replay modes. Support single and sequence playback."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from . import _regs as spcm
from .config import (
    CardConfig,
    ChannelConfig,
    ClockConfig,
    DigitalOutput,
    Segment,
    SequenceStep,
    TriggerConfig,
)
from .driver import SpcmDriver
from .enums import (
    ClockMode,
    ReplayMode,
    StepEndCondition,
    TriggerEdge,
    TriggerSource,
)
from .exceptions import SpectrumConfigError

# --------------------------------------------------------------------------- #
# Enum-to-SPCM constant lookup tables
# --------------------------------------------------------------------------- #
_REPLAY_MODE = {
    ReplayMode.SINGLE: spcm.SPC_REP_STD_SINGLE,
    ReplayMode.SINGLE_RESTART: spcm.SPC_REP_STD_SINGLERESTART,
    ReplayMode.CONTINUOUS: spcm.SPC_REP_STD_CONTINUOUS,
    ReplayMode.SEQUENCE: spcm.SPC_REP_STD_SEQUENCE,
}

_CLOCK_MODE = {
    ClockMode.INTERNAL_PLL: spcm.SPC_CM_INTPLL,
    ClockMode.EXTERNAL_REFERENCE: spcm.SPC_CM_EXTREFCLOCK,
}

_TRIGGER_EDGE = {
    TriggerEdge.RISING: spcm.SPC_TM_POS,
    TriggerEdge.FALLING: spcm.SPC_TM_NEG,
    TriggerEdge.HIGH: spcm.SPC_TM_HIGH,
    TriggerEdge.LOW: spcm.SPC_TM_LOW,
}

_STOP_LEVEL = {
    "zero": spcm.SPCM_STOPLVL_ZERO,
    "low": spcm.SPCM_STOPLVL_LOW,
    "high": spcm.SPCM_STOPLVL_HIGH,
    "hold": spcm.SPCM_STOPLVL_HOLDLAST,
}

_STEP_FLAG = {
    StepEndCondition.ALWAYS: spcm.SPCSEQ_ENDLOOPALWAYS,
    StepEndCondition.ON_TRIGGER: spcm.SPCSEQ_ENDLOOPONTRIG,
    StepEndCondition.END: spcm.SPCSEQ_END,
}

# Source channel flags for multi-purpose digital outputs
_DIGOUT_SRC_CH = {
    0: spcm.SPCM_XMODE_DIGOUTSRC_CH0,
    1: spcm.SPCM_XMODE_DIGOUTSRC_CH1,
    2: spcm.SPCM_XMODE_DIGOUTSRC_CH2,
    3: spcm.SPCM_XMODE_DIGOUTSRC_CH3,
}
_DIGOUT_SRC_BIT = {
    15: spcm.SPCM_XMODE_DIGOUTSRC_BIT15,
    14: spcm.SPCM_XMODE_DIGOUTSRC_BIT14,
    13: spcm.SPCM_XMODE_DIGOUTSRC_BIT13,
}

# Register offsets between channels (Spectrum standard layout)
_AMP_STRIDE = spcm.SPC_AMP1 - spcm.SPC_AMP0
_OFFS_STRIDE = spcm.SPC_OFFS1 - spcm.SPC_OFFS0
_ENABLEOUT_STRIDE = spcm.SPC_ENABLEOUT1 - spcm.SPC_ENABLEOUT0
_FILTER_STRIDE = spcm.SPC_FILTER1 - spcm.SPC_FILTER0
_STOPLVL_STRIDE = spcm.SPC_CH1_STOPLEVEL - spcm.SPC_CH0_STOPLEVEL
_XMODE_STRIDE = spcm.SPCM_X1_MODE - spcm.SPCM_X0_MODE

# Sequence step masks and encoding
_SEQ_SEGMENTMASK = 0x0000FFFF
_SEQ_NEXTSTEPMASK = 0xFFFF0000
_SEQ_LOOPMASK = 0x000FFFFF


class SpectrumM4i6631:
    """Configure and operate a Spectrum M4i.6631-x8 with two 16-bit analog channels.
    Apply configuration, load a single waveform or sequence, then start output.
    The context manager stops and closes the card on exit."""

    #: Number of analog output channels on the M4i.6631-x8.
    NUM_ANALOG_CHANNELS = 2

    def __init__(self, device: str = "/dev/spcm0",
                 config: Optional[CardConfig] = None) -> None:
        """device: SPCM device string, e.g. /dev/spcm0; config: optional initial
        settings that can later be supplied to apply_config."""
        self.driver = SpcmDriver(device)
        self.config: CardConfig = config or CardConfig()
        self._segment_length_samples: dict[int, int] = {}

    # ------------------------------------------------------------------ #
    # Connection / lifecycle
    # ------------------------------------------------------------------ #
    def open(self) -> "SpectrumM4i6631":
        self.driver.open()
        return self

    def close(self) -> None:
        self.driver.close()

    def __enter__(self) -> "SpectrumM4i6631":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        # Stop output before closing
        try:
            if self.driver.is_open:
                self.stop()
        finally:
            self.close()

    def reset(self) -> None:
        """Reset the card using M2CMD_CARD_RESET."""
        self.driver.command(spcm.M2CMD_CARD_RESET)

    # ------------------------------------------------------------------ #
    # Card information
    # ------------------------------------------------------------------ #
    def identity(self) -> dict:
        """Read card type, serial number, channel count and maximum DAC value."""
        return {
            "card_type": self.driver.get32(spcm.SPC_PCITYP),
            "serial_number": self.driver.get32(spcm.SPC_PCISERIALNO),
            "num_channels": self.driver.get32(spcm.SPC_MIINST_CHPERMODULE)
            * self.driver.get32(spcm.SPC_MIINST_MODULES),
            "max_dac_value": self.driver.get32(spcm.SPC_MIINST_MAXADCVALUE),
            "max_sample_rate_hz": self.driver.get64(spcm.SPC_PCISAMPLERATE),
            "memory_bytes": self.driver.get64(spcm.SPC_PCIMEMSIZE),
        }

    @property
    def max_dac_value(self) -> int:
        """Maximum positive DAC code: 32767 for a 16-bit DAC."""
        return self.driver.get32(spcm.SPC_MIINST_MAXADCVALUE)

    def set_timeout_ms(self, timeout_ms: int) -> None:
        """Set the wait timeout in milliseconds (SPC_TIMEOUT)."""
        self.driver.set32(spcm.SPC_TIMEOUT, int(timeout_ms))

    # ------------------------------------------------------------------ #
    # Apply complete configuration
    # ------------------------------------------------------------------ #
    def apply_config(self, config: Optional[CardConfig] = None) -> None:
        """Write configuration without starting output.
        Order: replay mode, channels, clock, trigger, digital outputs, sequence settings.
        Sequence WRITESETUP is deferred until load_sequence has defined its segments."""
        if config is not None:
            self.config = config
        cfg = self.config
        cfg.validate()

        self._write_card_mode(cfg)
        self._write_channels(cfg.channels)
        self._write_clock(cfg.clock)
        self._write_trigger(cfg.trigger)
        self._write_digital_outputs(cfg.digital_outputs)

        if cfg.replay_mode is ReplayMode.SEQUENCE:
            # Set basic parameters only; load_sequence issues WRITESETUP because
            # sequence validation also checks segments that are not yet loaded.
            self._init_sequence_mode(cfg)
        else:
            # Send setup to the card to validate the register combination early.
            self.driver.command(spcm.M2CMD_CARD_WRITESETUP)

    # ------------------------------------------------------------------ #
    # Partial configurations
    # ------------------------------------------------------------------ #
    def _write_card_mode(self, cfg: CardConfig) -> None:
        self.driver.set32(spcm.SPC_CARDMODE, _REPLAY_MODE[cfg.replay_mode])

    def _enabled_channel_indices(self) -> list[int]:
        return [ch.index for ch in self.config.channels if ch.enabled]

    def _write_channels(self, channels: Sequence[ChannelConfig]) -> None:
        # Validate channel range and reject duplicate indices
        seen: set[int] = set()
        for ch in channels:
            if not (0 <= ch.index < self.NUM_ANALOG_CHANNELS):
                raise SpectrumConfigError(
                    f"Channel index {ch.index} invalid; the M4i.6631-x8 has "
                    f"{self.NUM_ANALOG_CHANNELS} channels (0..{self.NUM_ANALOG_CHANNELS - 1})."
                )
            if ch.index in seen:
                raise SpectrumConfigError(f"Channel index {ch.index} configured more than once.")
            seen.add(ch.index)

        # Build channel enable mask (CHANNEL0 = bit 0, CHANNEL1 = bit 1, ...)
        enable_mask = 0
        for ch in channels:
            if ch.enabled:
                enable_mask |= (1 << ch.index)
        if enable_mask == 0:
            raise SpectrumConfigError("No channel enabled.")
        self.driver.set32(spcm.SPC_CHENABLE, enable_mask)

        for ch in channels:
            i = ch.index
            # Output amplifier
            self.driver.set32(spcm.SPC_ENABLEOUT0 + i * _ENABLEOUT_STRIDE,
                              1 if ch.output_on else 0)
            # Output range / amplitude (mV)
            self.driver.set32(spcm.SPC_AMP0 + i * _AMP_STRIDE, int(ch.amplitude_mv))
            # Offset (mV)
            self.driver.set32(spcm.SPC_OFFS0 + i * _OFFS_STRIDE, int(ch.offset_mv))
            # Output filter
            self.driver.set32(spcm.SPC_FILTER0 + i * _FILTER_STRIDE,
                              1 if ch.filter_on else 0)
            # Stop level
            self.driver.set32(spcm.SPC_CH0_STOPLEVEL + i * _STOPLVL_STRIDE,
                              _STOP_LEVEL[ch.stop_level])

    def _write_clock(self, clock: ClockConfig) -> None:
        self.driver.set32(spcm.SPC_CLOCKMODE, _CLOCK_MODE[clock.mode])
        if clock.mode is ClockMode.EXTERNAL_REFERENCE:
            self.driver.set32(spcm.SPC_REFERENCECLOCK, int(clock.reference_clock_hz))
        # Sample rate (i64): internal PLL rate or derived external-reference rate
        self.driver.set64(spcm.SPC_SAMPLERATE, int(clock.sample_rate_hz))
        # Clock output
        self.driver.set32(spcm.SPC_CLOCKOUT, 1 if clock.clock_output else 0)

    def _write_trigger(self, trig: TriggerConfig) -> None:
        # Clear AND mask and derive OR mask from the trigger source
        self.driver.set32(spcm.SPC_TRIG_ANDMASK, 0)

        if trig.source is TriggerSource.SOFTWARE:
            self.driver.set32(spcm.SPC_TRIG_ORMASK, spcm.SPC_TMASK_SOFTWARE)
        elif trig.source is TriggerSource.EXTERNAL0:
            self.driver.set32(spcm.SPC_TRIG_ORMASK, spcm.SPC_TMASK_EXT0)
            self.driver.set32(spcm.SPC_TRIG_EXT0_MODE, _TRIGGER_EDGE[trig.edge])
            self.driver.set32(spcm.SPC_TRIG_EXT0_LEVEL0, int(trig.level_mv))
            self.driver.set32(spcm.SPC_TRIG_TERM, 1 if trig.ext_termination_50ohm else 0)
        elif trig.source is TriggerSource.EXTERNAL1:
            self.driver.set32(spcm.SPC_TRIG_ORMASK, spcm.SPC_TMASK_EXT1)
            self.driver.set32(spcm.SPC_TRIG_EXT1_MODE, _TRIGGER_EDGE[trig.edge])
            self.driver.set32(spcm.SPC_TRIG_EXT1_LEVEL0, int(trig.level_mv))
        else:  # pragma: no cover
            raise SpectrumConfigError(f"Unknown trigger source: {trig.source}")

        # Trigger output
        self.driver.set32(spcm.SPC_TRIGGEROUT, 1 if trig.trigger_out else 0)

    def _write_digital_outputs(self, digital_outputs: Iterable[DigitalOutput]) -> None:
        for do in digital_outputs:
            reg = spcm.SPCM_X0_MODE + do.x_line * _XMODE_STRIDE
            value = (spcm.SPCM_XMODE_DIGOUT
                     | _DIGOUT_SRC_CH[do.source_channel]
                     | _DIGOUT_SRC_BIT[do.source_bit.value])
            self.driver.set32(reg, value)

    # ------------------------------------------------------------------ #
    # Single / continuous mode
    # ------------------------------------------------------------------ #
    def load_single(self, data) -> None:
        """Load an int16 waveform for SINGLE, SINGLE_RESTART or CONTINUOUS modes.
        For multiple channels, interleave samples: ch0[0], ch1[0], ch0[1], ch1[1], ..."""
        if self.config.replay_mode is ReplayMode.SEQUENCE:
            raise SpectrumConfigError(
                "load_single() is unavailable in SEQUENCE mode; use load_sequence()."
            )

        num_channels = len(self._enabled_channel_indices())
        total = len(data)
        if total % num_channels != 0:
            raise SpectrumConfigError(
                f"Data length {total} is not divisible by the channel count {num_channels}."
            )
        samples_per_channel = total // num_channels

        # Set memory size in samples per channel
        self.driver.set64(spcm.SPC_MEMSIZE, samples_per_channel)
        # Repeats: force SINGLE = 1; otherwise configurable (0 = endless)
        loops = 1 if self.config.replay_mode is ReplayMode.SINGLE else self.config.loops
        self.driver.set64(spcm.SPC_LOOPS, loops)

        # Transfer data using DMA
        self.driver.transfer_to_card(data)

    # ------------------------------------------------------------------ #
    # Sequence mode
    # ------------------------------------------------------------------ #
    def _init_sequence_mode(self, cfg: CardConfig) -> None:
        """Set sequence segment count and starting step."""
        self.driver.set32(spcm.SPC_SEQMODE_MAXSEGMENTS, cfg.max_segments)
        self.driver.set32(spcm.SPC_SEQMODE_STARTSTEP, cfg.start_step)

    def load_sequence(self, segments: Sequence[Segment],
                      steps: Sequence[SequenceStep]) -> None:
        """Load sequence segments and the step table.
        Apply SEQUENCE configuration first. Segment indices must be below max_segments;
        every referenced segment must be loaded. Follow next_step until an END step."""
        if self.config.replay_mode is not ReplayMode.SEQUENCE:
            raise SpectrumConfigError(
                "load_sequence() requires replay_mode=ReplayMode.SEQUENCE."
            )
        if not segments:
            raise SpectrumConfigError("No segments supplied.")
        if not steps:
            raise SpectrumConfigError("No step table supplied.")

        num_channels = len(self._enabled_channel_indices())

        # 1) Write segments
        self._segment_length_samples.clear()
        for seg in segments:
            seg.validate()
            if seg.index >= self.config.max_segments:
                raise SpectrumConfigError(
                    f"Segment index {seg.index} >= max_segments "
                    f"({self.config.max_segments})."
                )
            total = len(seg.data)
            if total % num_channels != 0:
                raise SpectrumConfigError(
                    f"Segment {seg.index}: Data length {total} nicht durch "
                    f"channel count {num_channels}."
                )
            samples_per_channel = total // num_channels

            # Select the write segment and set its size
            self.driver.set32(spcm.SPC_SEQMODE_WRITESEGMENT, seg.index)
            self.driver.set32(spcm.SPC_SEQMODE_SEGMENTSIZE, samples_per_channel)
            self.driver.transfer_to_card(seg.data)
            self._segment_length_samples[seg.index] = samples_per_channel

        # 2) Write step table
        loaded = set(self._segment_length_samples)
        for step in steps:
            step.validate()
            if step.segment not in loaded:
                raise SpectrumConfigError(
                    f"Step {step.step_index} references an unloaded "
                    f"Segment {step.segment}."
                )
            self._write_step(step)

        # 3) Send setup now that all segments and steps are defined
        self.driver.command(spcm.M2CMD_CARD_WRITESETUP)

    def _write_step(self, step: SequenceStep) -> None:
        """Encode one 64-bit sequence step in SPC_SEQMODE_STEPMEM0 + index.
        High DWORD = flags | (loops & LOOPMASK); low DWORD =
        ((next_step << 16) & NEXTSTEPMASK) | (segment & SEGMENTMASK)."""
        flags = _STEP_FLAG[step.end_condition]
        high = (flags & ~_SEQ_LOOPMASK) | (step.loops & _SEQ_LOOPMASK)
        low = ((step.next_step << 16) & _SEQ_NEXTSTEPMASK) | (step.segment & _SEQ_SEGMENTMASK)
        value = (high << 32) | low
        self.driver.set64(spcm.SPC_SEQMODE_STEPMEM0 + step.step_index, value)

    # ------------------------------------------------------------------ #
    # Seamless sequence updates during playback without restart
    # ------------------------------------------------------------------ #
    def write_segment(self, index: int, data) -> None:
        """Write or update one segment, including while the card is running.
        Use an inactive segment for seamless updates, then write_step to switch at the
        next loop boundary. index must be below max_segments; int16 data is interleaved
        when multiple channels are active."""
        if self.config.replay_mode is not ReplayMode.SEQUENCE:
            raise SpectrumConfigError(
                "write_segment() requires replay_mode=ReplayMode.SEQUENCE."
            )
        if index >= self.config.max_segments:
            raise SpectrumConfigError(
                f"Segment index {index} >= max_segments ({self.config.max_segments})."
            )
        num_channels = len(self._enabled_channel_indices())
        total = len(data)
        if total % num_channels != 0:
            raise SpectrumConfigError(
                f"Segment {index}: Data length {total} not divisible by channel count "
                f"{num_channels}."
            )
        samples_per_channel = total // num_channels

        self.driver.set32(spcm.SPC_SEQMODE_WRITESEGMENT, index)
        self.driver.set32(spcm.SPC_SEQMODE_SEGMENTSIZE, samples_per_channel)
        self.driver.transfer_to_card(data)
        self._segment_length_samples[index] = samples_per_channel
        # Do not issue M2CMD_CARD_WRITESETUP during playback. An inactive
        # segment's data is updated directly through DMA.
        # WRITESETUP during playback would report an error
        # because the card is already running.

    def write_step(self, step: SequenceStep) -> None:
        """Update a sequence step, including during playback.
        After writing the inactive segment, point the active step to it. The card
        switches at the next loop boundary without restarting. Supply step_index and
        segment in the new SequenceStep."""
        if self.config.replay_mode is not ReplayMode.SEQUENCE:
            raise SpectrumConfigError(
                "write_step() requires replay_mode=ReplayMode.SEQUENCE."
            )
        step.validate()
        if step.segment not in self._segment_length_samples:
            raise SpectrumConfigError(
                f"Step references unloaded segment {step.segment}."
            )
        # STEPMEM is read live during playback; no WRITESETUP is needed
        # (it would fail during playback). Switching takes effect
        # at the next loop boundary.
        self._write_step(step)

    # ------------------------------------------------------------------ #
    # Playback controls
    # ------------------------------------------------------------------ #
    def start(self, wait: bool = False, enable_trigger: bool = True) -> None:
        """Start output. wait=True blocks until finite playback finishes (SINGLE or
        SINGLE_RESTART). enable_trigger arms triggers via M2CMD_CARD_ENABLETRIGGER."""
        cmd = spcm.M2CMD_CARD_START
        if enable_trigger:
            cmd |= spcm.M2CMD_CARD_ENABLETRIGGER
        if wait:
            cmd |= spcm.M2CMD_CARD_WAITREADY
        self.driver.command(cmd)

    def force_trigger(self) -> None:
        """Issue a software trigger (M2CMD_CARD_FORCETRIGGER)."""
        self.driver.command(spcm.M2CMD_CARD_FORCETRIGGER)

    def wait_ready(self) -> None:
        """Wait for playback completion (M2CMD_CARD_WAITREADY)."""
        self.driver.command(spcm.M2CMD_CARD_WAITREADY)

    def stop(self) -> None:
        """Stop output (M2CMD_CARD_STOP)."""
        self.driver.command(spcm.M2CMD_CARD_STOP)

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #
    def status(self) -> int:
        """Read raw status register SPC_M2STATUS."""
        return self.driver.get32(spcm.SPC_M2STATUS)

    def status_flags(self) -> dict:
        """Decode enabled status flags into a dictionary."""
        raw = self.status()
        names = {
            "ready": spcm.M2STAT_CARD_READY,
            "trigger_seen": spcm.M2STAT_CARD_TRIGGER,
            "pretrigger": spcm.M2STAT_CARD_PRETRIGGER,
            "data_end": spcm.M2STAT_DATA_END,
            "data_error": spcm.M2STAT_DATA_ERROR,
        }
        return {name: bool(raw & bit) for name, bit in names.items()}

    def is_ready(self) -> bool:
        """True when playback has ended or the card is stopped and ready."""
        return bool(self.status() & spcm.M2STAT_CARD_READY)
