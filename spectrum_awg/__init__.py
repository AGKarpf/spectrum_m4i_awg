"""Spectrum M4i.6631-x8 AWG library: two analog channels, 16-bit DAC, up to
1.25 GS/s. Export card configuration, driver, waveform helpers and replay enums."""

from __future__ import annotations

from .card import SpectrumM4i6631
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
    DigitalBitSource,
    ReplayMode,
    StepEndCondition,
    TriggerEdge,
    TriggerSource,
)
from .exceptions import (
    SpectrumConfigError,
    SpectrumDriverError,
    SpectrumError,
    SpectrumNotConnectedError,
)

__all__ = [
    "SpectrumM4i6631",
    "SpcmDriver",
    "CardConfig",
    "ClockConfig",
    "TriggerConfig",
    "ChannelConfig",
    "DigitalOutput",
    "Segment",
    "SequenceStep",
    "ReplayMode",
    "ClockMode",
    "TriggerSource",
    "TriggerEdge",
    "StepEndCondition",
    "DigitalBitSource",
    "SpectrumError",
    "SpectrumDriverError",
    "SpectrumConfigError",
    "SpectrumNotConnectedError",
]

__version__ = "0.1.0"
