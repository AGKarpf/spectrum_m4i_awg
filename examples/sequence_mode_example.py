"""Beispiel: Sequenced-Modus.

Definiert 3 Segmente (Sinus, Rechteck, Rampe) und eine Step-Abfolge:

    Step 0: Segment 0 (Sinus)    x5   -> Step 1
    Step 1: Segment 1 (Rechteck) x3   -> Step 2  (Wechsel erst nach externem Trigger)
    Step 2: Segment 2 (Rampe)    x1   -> ENDE

Die Karte folgt der next_step-Verkettung; erst StepEndCondition.END beendet die
Ausgabe. Segmentanzahl und Abfolge sind frei konfigurierbar.
"""

from spectrum_awg import (
    CardConfig,
    ChannelConfig,
    ClockConfig,
    ClockMode,
    ReplayMode,
    Segment,
    SequenceStep,
    SpectrumM4i6631,
    StepEndCondition,
    TriggerConfig,
    TriggerEdge,
    TriggerSource,
    waveforms,
)

SEG_LEN = 2048  # Samples pro Segment (pro Kanal)


def main() -> None:
    config = CardConfig(
        replay_mode=ReplayMode.SEQUENCE,
        clock=ClockConfig(mode=ClockMode.INTERNAL_PLL, sample_rate_hz=1_250_000_000),
        trigger=TriggerConfig(
            source=TriggerSource.EXTERNAL0,   # externer Trigger (fuer ON_TRIGGER-Step)
            edge=TriggerEdge.RISING,
            level_mv=1500,
            ext_termination_50ohm=True,
        ),
        channels=[ChannelConfig(index=0, amplitude_mv=1000)],
        max_segments=4,      # Zweierpotenz, >= Anzahl genutzter Segmente
        start_step=0,
    )

    # --- Datensegmente ---
    segments = [
        Segment(index=0, data=waveforms.sine(SEG_LEN, periods=1.0)),
        Segment(index=1, data=waveforms.square(SEG_LEN, periods=1.0, duty=0.5)),
        Segment(index=2, data=waveforms.ramp(SEG_LEN)),
    ]

    # --- Ablaufplan (Step-Tabelle) ---
    steps = [
        SequenceStep(step_index=0, segment=0, loops=5, next_step=1,
                     end_condition=StepEndCondition.ALWAYS),
        SequenceStep(step_index=1, segment=1, loops=3, next_step=2,
                     end_condition=StepEndCondition.ON_TRIGGER),
        SequenceStep(step_index=2, segment=2, loops=1, next_step=0,
                     end_condition=StepEndCondition.END),
    ]

    with SpectrumM4i6631("/dev/spcm0", config) as awg:
        print("Karteninfo:", awg.identity())
        awg.set_timeout_ms(10000)

        awg.apply_config()                  # Modus + Sequenz-Grundparameter
        awg.load_sequence(segments, steps)  # Segmente + Step-Tabelle laden

        awg.start(enable_trigger=True)      # Ausgabe starten, auf Trigger warten
        print("Sequenz laeuft. Externer Trigger noetig, um Step 1 zu verlassen.")
        awg.wait_ready()                    # blockiert bis StepEndCondition.END erreicht
        print("Sequenz abgeschlossen.")


if __name__ == "__main__":
    main()
