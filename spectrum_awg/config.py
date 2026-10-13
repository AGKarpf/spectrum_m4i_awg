"""Declarative dataclasses for clocks, triggers, channels and sequence steps.
card.py translates these settings into SPCM registers. Validation can be tested
without installed hardware drivers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from .enums import (
    ClockMode,
    DigitalBitSource,
    ReplayMode,
    StepEndCondition,
    TriggerEdge,
    TriggerSource,
)
from .exceptions import SpectrumConfigError


@dataclass
class ClockConfig:
    """Clock settings: mode selects internal PLL or external reference.
    sample_rate_hz sets output sample rate; reference_clock_hz applies to
    EXTERNAL_REFERENCE. clock_output enables the clock output connector."""

    mode: ClockMode = ClockMode.INTERNAL_PLL
    sample_rate_hz: int = 1_250_000_000
    reference_clock_hz: Optional[int] = None
    clock_output: bool = False

    def validate(self) -> None:
        if self.sample_rate_hz <= 0:
            raise SpectrumConfigError("sample_rate_hz must be greater than zero.")
        if self.mode is ClockMode.EXTERNAL_REFERENCE and not self.reference_clock_hz:
            raise SpectrumConfigError(
                "ClockMode.EXTERNAL_REFERENCE requires reference_clock_hz."
            )


@dataclass
class TriggerConfig:
    """Trigger settings: source selects software, Ext0 or Ext1; edge selects
    external edge/level mode; level_mv is the external threshold. trigger_out
    enables trigger output; ext_termination_50ohm enables 50-ohm input termination."""

    source: TriggerSource = TriggerSource.SOFTWARE
    edge: TriggerEdge = TriggerEdge.RISING
    level_mv: int = 1500
    trigger_out: bool = False
    ext_termination_50ohm: bool = True

    def validate(self) -> None:
        if self.source in (TriggerSource.EXTERNAL0, TriggerSource.EXTERNAL1):
            if self.edge is None:
                raise SpectrumConfigError("External trigger requires an edge.")


@dataclass
class DigitalOutput:
    """Digital output on X0/X1/X2. x_line selects 0, 1 or 2. source_bit
    selects the data bit, reducing analog resolution; source_channel is 0 or 1."""

    x_line: int
    source_bit: DigitalBitSource = DigitalBitSource.BIT15
    source_channel: int = 0

    def validate(self) -> None:
        if self.x_line not in (0, 1, 2):
            raise SpectrumConfigError(f"x_line must be 0, 1 or 2 (got {self.x_line}).")
        if self.source_channel not in (0, 1):
            raise SpectrumConfigError(
                f"source_channel must be 0 or 1 (got {self.source_channel})."
            )


@dataclass
class ChannelConfig:
    """Analog channel settings. index is 0 or 1; enabled includes the channel;
    output_on enables its amplifier (SPC_ENABLEOUTx). amplitude_mv sets peak output
    into 50 ohms (SPC_AMPx, e.g. 80..2500 mV). offset_mv sets DC offset; filter_on
    enables bandwidth limiting. stop_level is zero, low, high or hold."""

    index: int = 0
    enabled: bool = True
    output_on: bool = True
    amplitude_mv: int = 1000
    offset_mv: int = 0
    filter_on: bool = False
    stop_level: str = "zero"

    def validate(self) -> None:
        if self.index < 0:
            raise SpectrumConfigError("Channel index must not be negative.")
        if not (0 < self.amplitude_mv <= 2500):
            raise SpectrumConfigError(
                f"amplitude_mv ({self.amplitude_mv}) outside the permitted "
                "range (1..2500 mV)."
            )
        if self.stop_level not in ("zero", "low", "high", "hold"):
            raise SpectrumConfigError(
                f"stop_level '{self.stop_level}' ungueltig "
                "(erlaubt: zero, low, high, hold)."
            )


@dataclass
class SequenceStep:
    """Sequence playback step. Follow next_step rather than sequential indices;
    END finishes playback. step_index selects the table entry; segment selects the
    buffer; loops is 1..2^20-1; end_condition determines when the next step begins."""

    step_index: int
    segment: int
    loops: int = 1
    next_step: int = 0
    end_condition: StepEndCondition = StepEndCondition.ALWAYS

    LOOP_MAX = (1 << 20) - 1  # SPCSEQ_LOOPMASK

    def validate(self) -> None:
        if self.step_index < 0:
            raise SpectrumConfigError("step_index must not be negative.")
        if self.segment < 0:
            raise SpectrumConfigError("segment must not be negative.")
        if not (1 <= self.loops <= self.LOOP_MAX):
            raise SpectrumConfigError(
                f"loops ({self.loops}) must be between 1 and {self.LOOP_MAX} inclusive."
            )
        if self.next_step < 0:
            raise SpectrumConfigError("next_step must not be negative.")


@dataclass
class Segment:
    """Sequence data segment: index selects card memory; data contains int16
    samples (-32768..32767), interleaved for multiple active channels."""

    index: int
    data: "Sequence[int]"

    def validate(self) -> None:
        if self.index < 0:
            raise SpectrumConfigError("Segment index must not be negative.")
        if len(self.data) == 0:
            raise SpectrumConfigError(f"Segment {self.index} contains no data.")


@dataclass
class CardConfig:
    """Full card configuration combining replay mode, clock, trigger and channels.
    The card has two analog channels (0 and 1); channel 0 is active by default.
    List both ChannelConfig objects for two-channel operation. digital_outputs
    configures X lines; loops sets SINGLE_RESTART repeats (0 = endless).
    max_segments reserves a power-of-two segment count; start_step selects entry."""

    replay_mode: ReplayMode = ReplayMode.SINGLE
    clock: ClockConfig = field(default_factory=ClockConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    channels: list[ChannelConfig] = field(default_factory=lambda: [ChannelConfig()])
    digital_outputs: list[DigitalOutput] = field(default_factory=list)
    loops: int = 1
    max_segments: int = 2
    start_step: int = 0

    def validate(self) -> None:
        self.clock.validate()
        self.trigger.validate()
        if not self.channels:
            raise SpectrumConfigError("Configure at least one channel.")
        for ch in self.channels:
            ch.validate()
        for do in self.digital_outputs:
            do.validate()
        if self.replay_mode is ReplayMode.SEQUENCE:
            if self.max_segments < 1 or (self.max_segments & (self.max_segments - 1)) != 0:
                raise SpectrumConfigError(
                    f"max_segments ({self.max_segments}) must be a power of two."
                )
        if self.loops < 0:
            raise SpectrumConfigError("loops must not be negative (0 = endless).")
