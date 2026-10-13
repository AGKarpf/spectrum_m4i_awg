"""Generate numpy int16 waveforms for a 16-bit DAC.
Return arrays bounded by [-max_dac_value, +max_dac_value]; full scale corresponds
to the configured output amplitude. Requires numpy."""

from __future__ import annotations

import numpy as np

DEFAULT_MAX_DAC = 32767  # 16-bit DAC of the M4i.6631


def _scale(values: np.ndarray, amplitude_fraction: float, max_dac: int) -> np.ndarray:
    """Scale [-1, 1] to int16 and clamp to the DAC range."""
    peak = int(round(max_dac * amplitude_fraction))
    scaled = np.round(values * peak)
    return np.clip(scaled, -max_dac, max_dac).astype(np.int16)


def sine(num_samples: int, periods: float = 1.0,
         amplitude_fraction: float = 1.0, phase: float = 0.0,
         max_dac: int = DEFAULT_MAX_DAC) -> np.ndarray:
    """Sine waveform over num_samples with the specified full periods."""
    t = np.linspace(0.0, 2.0 * np.pi * periods, num_samples, endpoint=False)
    return _scale(np.sin(t + phase), amplitude_fraction, max_dac)


def ramp(num_samples: int, amplitude_fraction: float = 1.0,
         max_dac: int = DEFAULT_MAX_DAC) -> np.ndarray:
    """Rising sawtooth from negative peak to positive peak."""
    values = np.linspace(-1.0, 1.0, num_samples, endpoint=False)
    return _scale(values, amplitude_fraction, max_dac)


def square(num_samples: int, periods: float = 1.0, duty: float = 0.5,
           amplitude_fraction: float = 1.0,
           max_dac: int = DEFAULT_MAX_DAC) -> np.ndarray:
    """Square waveform with duty ratio in 0..1."""
    phase = (np.arange(num_samples) * periods / num_samples) % 1.0
    values = np.where(phase < duty, 1.0, -1.0)
    return _scale(values, amplitude_fraction, max_dac)


def dc(num_samples: int, level_fraction: float = 0.0,
       max_dac: int = DEFAULT_MAX_DAC) -> np.ndarray:
    """Constant level as a fraction of full scale (-1..1)."""
    values = np.full(num_samples, level_fraction, dtype=float)
    return _scale(values, 1.0, max_dac)


def interleave(*channel_signals: np.ndarray) -> np.ndarray:
    """Interleave equal-length channels into an int16 block.
    Result: ch0[0], ch1[0], ch0[1], ch1[1], ... for transfer_to_card."""
    if not channel_signals:
        raise ValueError("Supply at least one channel signal.")
    length = len(channel_signals[0])
    if any(len(s) != length for s in channel_signals):
        raise ValueError("All channel signals must have equal length.")
    stacked = np.vstack(channel_signals).astype(np.int16)
    return stacked.reshape((-1,), order="F")
