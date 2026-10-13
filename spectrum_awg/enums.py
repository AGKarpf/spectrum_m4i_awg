"""Driver-independent enums for card configuration."""

from __future__ import annotations

from enum import Enum


class ReplayMode(Enum):
    """Card replay mode (SPC_CARDMODE)."""

    #: Play the buffer once per trigger (single shot).
    SINGLE = "single"
    #: Play once, then wait for the next trigger.
    SINGLE_RESTART = "single_restart"
    #: Repeat indefinitely after the first trigger until STOP.
    CONTINUOUS = "continuous"
    #: Sequence mode: play segments according to the step table.
    SEQUENCE = "sequence"


class ClockMode(Enum):
    """Clock source (SPC_CLOCKMODE)."""

    #: Internal PLL with adjustable sample rate.
    INTERNAL_PLL = "internal_pll"
    #: External reference (e.g. 10 MHz); internal PLL derives sample rate.
    EXTERNAL_REFERENCE = "external_reference"


class TriggerSource(Enum):
    """Trigger source."""

    #: Software trigger (M2CMD_CARD_FORCETRIGGER or immediate start).
    SOFTWARE = "software"
    #: External input Ext0 (main SMA trigger).
    EXTERNAL0 = "external0"
    #: External input Ext1 (multi-purpose X1 if configured).
    EXTERNAL1 = "external1"


class TriggerEdge(Enum):
    """External trigger edge or level mode (SPC_TRIG_EXTx_MODE)."""

    RISING = "rising"     # SPC_TM_POS
    FALLING = "falling"   # SPC_TM_NEG
    HIGH = "high"         # SPC_TM_HIGH (level triggered)
    LOW = "low"           # SPC_TM_LOW


class StepEndCondition(Enum):
    """Sequence step end condition (STEPMEM flags)."""

    #: After loops repeats, advance immediately (SPCSEQ_ENDLOOPALWAYS).
    ALWAYS = "always"
    #: Repeat the current step until triggered, then advance (SPCSEQ_ENDLOOPONTRIG).
    ON_TRIGGER = "on_trigger"
    #: Final step: stop after loops repeats (SPCSEQ_END).
    END = "end"


class DigitalBitSource(Enum):
    """Data bit routed to a digital multi-purpose output.
    M4i AWG outputs use the highest data bits; each digital output reduces analog
    DAC resolution by one bit."""

    BIT15 = 15   # reduces analog resolution by 1 bit
    BIT14 = 14   # reduces analog resolution by 2 bits
    BIT13 = 13   # reduces analog resolution by 3 bits
