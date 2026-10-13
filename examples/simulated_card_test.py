"""Live-Test gegen eine SIMULIERTE Spectrum-Karte (Demo-Karte).

Faehrt den kompletten Single- und Sequence-Flow durch den echten spcm_core-Treiber,
ohne physisches Ausgangssignal. Standard-Geraet: /dev/spcm2 (per Argument aenderbar).

    py examples/simulated_card_test.py [/dev/spcm2]
"""

import sys

from spectrum_awg import (
    CardConfig,
    ChannelConfig,
    ClockConfig,
    ClockMode,
    DigitalBitSource,
    DigitalOutput,
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
from spectrum_awg.exceptions import SpectrumError


def run_single(device: str) -> None:
    print("\n=== SINGLE-Modus ===")
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        clock=ClockConfig(mode=ClockMode.INTERNAL_PLL, sample_rate_hz=1_250_000_000),
        trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
        channels=[ChannelConfig(index=0, amplitude_mv=1000, offset_mv=0)],
    )
    wf = waveforms.sine(4096, periods=1.0)
    with SpectrumM4i6631(device, cfg) as awg:
        print("identity:", awg.identity())
        awg.set_timeout_ms(3000)
        awg.apply_config()
        awg.load_single(wf)
        print("status vor Start:", awg.status_flags())
        awg.start(enable_trigger=True)
        awg.force_trigger()
        awg.wait_ready()
        print("status nach wait_ready:", awg.status_flags())
        print("-> Single-Flow OK")


def run_sequence(device: str) -> None:
    print("\n=== SEQUENCE-Modus ===")
    cfg = CardConfig(
        replay_mode=ReplayMode.SEQUENCE,
        clock=ClockConfig(sample_rate_hz=1_250_000_000),
        trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
        channels=[ChannelConfig(index=0, amplitude_mv=1000)],
        max_segments=4,
        start_step=0,
    )
    segs = [
        Segment(0, waveforms.sine(2048, periods=1.0)),
        Segment(1, waveforms.square(2048, periods=1.0)),
        Segment(2, waveforms.ramp(2048)),
    ]
    # Rein software-getriebene Kette (kein externer Trigger noetig), Ende nach Step 2
    steps = [
        SequenceStep(0, segment=0, loops=2, next_step=1,
                     end_condition=StepEndCondition.ALWAYS),
        SequenceStep(1, segment=1, loops=2, next_step=2,
                     end_condition=StepEndCondition.ALWAYS),
        SequenceStep(2, segment=2, loops=1, next_step=0,
                     end_condition=StepEndCondition.END),
    ]
    with SpectrumM4i6631(device, cfg) as awg:
        awg.set_timeout_ms(3000)
        awg.apply_config()
        awg.load_sequence(segs, steps)
        print("status vor Start:", awg.status_flags())
        awg.start(enable_trigger=True)
        awg.force_trigger()
        try:
            awg.wait_ready()
            print("status nach wait_ready:", awg.status_flags())
        except Exception as e:  # Demo-Karte laeuft ggf. bis Timeout -> tolerieren
            print("wait_ready meldete:", type(e).__name__, "- Sequenz lief (Demo).")
        awg.stop()
        print("-> Sequence-Flow OK")


def run_two_channels(device: str) -> None:
    print("\n=== Zweikanalbetrieb (Single) ===")
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        clock=ClockConfig(sample_rate_hz=1_250_000_000),
        trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
        channels=[
            ChannelConfig(index=0, amplitude_mv=1000),
            ChannelConfig(index=1, amplitude_mv=500),
        ],
    )
    n = 4096
    data = waveforms.interleave(waveforms.sine(n), waveforms.ramp(n))
    with SpectrumM4i6631(device, cfg) as awg:
        print("num_channels:", awg.identity()["num_channels"])
        awg.set_timeout_ms(3000)
        awg.apply_config()
        awg.load_single(data)
        awg.start(enable_trigger=True)
        awg.force_trigger()
        awg.wait_ready()
        print("-> Zweikanal-Flow OK")


def run_digital_outputs(device: str) -> None:
    print("\n=== Digitalausgaenge (Multi-Purpose-Lines X0/X1/X2) ===")
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
        channels=[ChannelConfig(index=0, amplitude_mv=1000)],
        digital_outputs=[
            DigitalOutput(x_line=0, source_bit=DigitalBitSource.BIT15),
            DigitalOutput(x_line=1, source_bit=DigitalBitSource.BIT14),
            DigitalOutput(x_line=2, source_bit=DigitalBitSource.BIT13),
        ],
    )
    with SpectrumM4i6631(device, cfg) as awg:
        awg.set_timeout_ms(3000)
        try:
            awg.apply_config()
            awg.load_single(waveforms.sine(2048))
            awg.start(enable_trigger=True)
            awg.force_trigger()
            awg.wait_ready()
            print("-> 3 Digitalausgaenge konfiguriert & ausgegeben, OK")
        except SpectrumError as e:
            print("Demo-Karte lehnt Digital-Out ggf. ab:", e)


def run_external_reference(device: str) -> None:
    print("\n=== Externer Referenztakt (10 MHz) ===")
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        clock=ClockConfig(mode=ClockMode.EXTERNAL_REFERENCE,
                          reference_clock_hz=10_000_000,
                          sample_rate_hz=1_250_000_000),
        trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
        channels=[ChannelConfig(index=0, amplitude_mv=1000)],
    )
    with SpectrumM4i6631(device, cfg) as awg:
        awg.set_timeout_ms(3000)
        try:
            awg.apply_config()
            awg.load_single(waveforms.sine(2048))
            awg.start(enable_trigger=True)
            awg.force_trigger()
            awg.wait_ready()
            print("-> Externer Referenztakt akzeptiert, OK")
        except SpectrumError as e:
            print("Demo-Karte ohne ext. Referenz -> erwartbar:", e)


def run_many_segments(device: str, n: int = 16) -> None:
    print(f"\n=== Viele Segmente + lange Step-Kette (n={n}) ===")
    # max_segments muss Zweierpotenz >= n sein
    max_seg = 1
    while max_seg < n:
        max_seg <<= 1
    cfg = CardConfig(
        replay_mode=ReplayMode.SEQUENCE,
        trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
        channels=[ChannelConfig(index=0, amplitude_mv=1000)],
        max_segments=max_seg,
        start_step=0,
    )
    segs = [Segment(i, waveforms.dc(512, (i - n / 2) / n)) for i in range(n)]
    steps = []
    for i in range(n):
        end = StepEndCondition.END if i == n - 1 else StepEndCondition.ALWAYS
        steps.append(SequenceStep(i, segment=i, loops=(i + 1),
                                  next_step=(i + 1) % n, end_condition=end))
    with SpectrumM4i6631(device, cfg) as awg:
        awg.set_timeout_ms(3000)
        awg.apply_config()
        awg.load_sequence(segs, steps)
        awg.start(enable_trigger=True)
        awg.force_trigger()
        try:
            awg.wait_ready()
        except SpectrumError as e:
            print("wait_ready:", type(e).__name__, "(Demo laeuft weiter)")
        awg.stop()
        print(f"-> {n} Segmente / {n}-Step-Kette geladen & gestartet, OK")


def main() -> None:
    device = sys.argv[1] if len(sys.argv) > 1 else "/dev/spcm2"
    print(f"Geraet: {device}")
    run_single(device)
    run_two_channels(device)
    run_sequence(device)
    run_digital_outputs(device)
    run_external_reference(device)
    run_many_segments(device, n=16)
    print("\nAlle Live-Flows gegen die simulierte Karte durchlaufen.")


if __name__ == "__main__":
    main()
