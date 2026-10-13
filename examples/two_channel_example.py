"""Beispiel: Zweikanalbetrieb (Single-Modus).

Die M4i.6631-x8 hat 2 Analogkanaele. Hier gibt Kanal 0 einen Sinus und Kanal 1
eine Rampe aus. Die Sample-Daten beider Kanaele werden interleaved uebergeben
(ch0[0], ch1[0], ch0[1], ch1[1], ...).

Voraussetzung: SPCM-Treiber/spcm_core, Karte als /dev/spcm0 (oder Demo /dev/spcm2).
"""

import sys

from spectrum_awg import (
    CardConfig,
    ChannelConfig,
    ClockConfig,
    ReplayMode,
    SpectrumM4i6631,
    TriggerConfig,
    TriggerSource,
    waveforms,
)


def main() -> None:
    device = sys.argv[1] if len(sys.argv) > 1 else "/dev/spcm0"

    config = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        clock=ClockConfig(sample_rate_hz=1_250_000_000),
        trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
        channels=[
            ChannelConfig(index=0, amplitude_mv=1000),   # Kanal 0: +/-1 V
            ChannelConfig(index=1, amplitude_mv=500),    # Kanal 1: +/-0.5 V
        ],
    )

    n = 4096
    ch0 = waveforms.sine(n, periods=1.0)
    ch1 = waveforms.ramp(n)
    data = waveforms.interleave(ch0, ch1)   # -> Laenge 2*n, interleaved

    with SpectrumM4i6631(device, config) as awg:
        print("Karteninfo:", awg.identity())
        awg.set_timeout_ms(5000)
        awg.apply_config()
        awg.load_single(data)
        awg.start(enable_trigger=True)
        awg.force_trigger()
        awg.wait_ready()
        print("Zweikanal-Ausgabe abgeschlossen.")


if __name__ == "__main__":
    main()
