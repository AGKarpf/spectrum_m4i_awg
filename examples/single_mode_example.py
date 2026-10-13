"""Beispiel: Single-Modus.

Gibt einen einzelnen Sinus (eine Periode) auf Kanal 0 aus, ausgeloest per
Software-Trigger. Fuer Dauerbetrieb einfach ReplayMode.CONTINUOUS setzen.

Voraussetzung: SPCM-Treiber installiert, Karte als /dev/spcm0 erreichbar.
"""

from spectrum_awg import (
    CardConfig,
    ChannelConfig,
    ClockConfig,
    ClockMode,
    ReplayMode,
    SpectrumM4i6631,
    TriggerConfig,
    TriggerSource,
    waveforms,
)


def main() -> None:
    config = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        clock=ClockConfig(
            mode=ClockMode.INTERNAL_PLL,
            sample_rate_hz=1_250_000_000,   # 1.25 GS/s (Maximum der M4i.6631)
            clock_output=False,
        ),
        trigger=TriggerConfig(
            source=TriggerSource.SOFTWARE,  # Start per Software
        ),
        channels=[
            ChannelConfig(
                index=0,
                enabled=True,
                output_on=True,
                amplitude_mv=1000,          # Dynamikbereich: +/-1 V in 50 Ohm
                offset_mv=0,
                filter_on=False,
                stop_level="zero",
            ),
        ],
    )

    # Eine Sinusperiode ueber 4096 Samples, Vollausschlag
    waveform = waveforms.sine(num_samples=4096, periods=1.0, amplitude_fraction=1.0)

    with SpectrumM4i6631("/dev/spcm0", config) as awg:
        print("Karteninfo:", awg.identity())
        awg.set_timeout_ms(5000)

        awg.apply_config()          # Takt/Trigger/Kanaele/Modus schreiben
        awg.load_single(waveform)   # Waveform in den Speicher laden

        awg.start(enable_trigger=True)   # Ausgabe starten, Trigger scharf
        awg.force_trigger()              # Software-Trigger ausloesen
        awg.wait_ready()                 # auf Ende der Ausgabe warten
        print("Ausgabe abgeschlossen.")


if __name__ == "__main__":
    main()
