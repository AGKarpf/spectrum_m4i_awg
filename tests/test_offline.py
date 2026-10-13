"""Hardwarefreie Offline-Tests gegen den SPCM-Mock (tests/stubs).

Ausfuehren:  python tests/test_offline.py
Diese Tests brauchen KEINE Karte und KEINEN echten Treiber.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
# Stubs (pyspcm/regs) VOR alles andere, damit _regs sie findet:
sys.path.insert(0, os.path.join(_HERE, "stubs"))
sys.path.insert(0, _ROOT)
# Backend hart auf den klassischen/Stub-Pfad zwingen, damit der Test hermetisch
# bleibt, auch wenn spcm_core installiert ist (sonst wuerde die echte Karte angesprochen):
os.environ["SPECTRUM_AWG_BACKEND"] = "pyspcm"

import pyspcm  # noqa: E402  (Mock)
import regs as R  # noqa: E402  (Mock-Konstanten)

from spectrum_awg import (  # noqa: E402
    CardConfig,
    ChannelConfig,
    ClockConfig,
    ClockMode,
    DigitalBitSource,
    DigitalOutput,
    ReplayMode,
    Segment,
    SequenceStep,
    SpectrumConfigError,
    SpectrumM4i6631,
    StepEndCondition,
    TriggerConfig,
    TriggerEdge,
    TriggerSource,
    waveforms,
)


def _sets(kind=None):
    """Liefert dict register->wert der aufgezeichneten Schreibzugriffe."""
    return {reg: val for (art, reg, val) in pyspcm.writes
            if kind is None or art == kind}


def _commands():
    return [val for (art, reg, val) in pyspcm.writes if art == "cmd"]


def test_config_validation():
    # ungueltige Amplitude
    try:
        ChannelConfig(amplitude_mv=9999).validate()
        assert False, "erwartete SpectrumConfigError"
    except SpectrumConfigError:
        pass
    # max_segments keine Zweierpotenz
    try:
        CardConfig(replay_mode=ReplayMode.SEQUENCE, max_segments=3).validate()
        assert False, "erwartete SpectrumConfigError"
    except SpectrumConfigError:
        pass
    # externer Referenztakt ohne Frequenz
    try:
        ClockConfig(mode=ClockMode.EXTERNAL_REFERENCE).validate()
        assert False, "erwartete SpectrumConfigError"
    except SpectrumConfigError:
        pass
    print("[ok] Konfigurationsvalidierung")


def test_waveforms():
    s = waveforms.sine(1024, periods=2.0)
    assert s.dtype.name == "int16"
    assert len(s) == 1024
    assert s.max() <= 32767 and s.min() >= -32768
    il = waveforms.interleave(waveforms.dc(4, 0.0), waveforms.dc(4, 1.0))
    assert list(il) == [0, 32767, 0, 32767, 0, 32767, 0, 32767]
    print("[ok] Waveform-Erzeugung + Interleave")


def test_single_mode():
    pyspcm.reset_recording()
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        clock=ClockConfig(sample_rate_hz=1_250_000_000),
        trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
        channels=[ChannelConfig(index=0, amplitude_mv=1000, offset_mv=50)],
    )
    wf = waveforms.sine(4096, periods=1.0)
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        info = awg.identity()
        assert info["card_type"] == 0x6631
        assert info["max_dac_value"] == 32767
        awg.apply_config()
        awg.load_single(wf)
        awg.start(enable_trigger=True)
        awg.force_trigger()
        awg.wait_ready()

    sets = _sets("set32")
    assert sets[R.SPC_CARDMODE] == R.SPC_REP_STD_SINGLE
    assert sets[R.SPC_CHENABLE] == 1                      # nur Kanal 0 aktiviert
    assert sets[R.SPC_AMP0] == 1000
    assert sets[R.SPC_OFFS0] == 50
    assert sets[R.SPC_CLOCKMODE] == R.SPC_CM_INTPLL
    assert sets[R.SPC_TRIG_ORMASK] == R.SPC_TMASK_SOFTWARE
    sets64 = _sets("set64")
    assert sets64[R.SPC_SAMPLERATE] == 1_250_000_000
    assert sets64[R.SPC_MEMSIZE] == 4096
    assert sets64[R.SPC_LOOPS] == 1                       # SINGLE erzwingt 1
    # genau ein DMA-Transfer, Groesse 4096 * 2 Byte
    assert len(pyspcm.transfers) == 1
    assert pyspcm.transfers[0][3] == 4096 * 2
    # Kommandos: WRITESETUP, START|ENABLE, FORCE, WAITREADY, STOP (beim Close)
    cmds = _commands()
    assert any(c & R.M2CMD_CARD_WRITESETUP for c in cmds)
    assert any(c & R.M2CMD_CARD_START for c in cmds)
    assert any(c & R.M2CMD_CARD_FORCETRIGGER for c in cmds)
    print("[ok] Single-Modus (Register + DMA + Kommandos)")


def test_external_trigger_and_digital():
    pyspcm.reset_recording()
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        trigger=TriggerConfig(source=TriggerSource.EXTERNAL0,
                              edge=TriggerEdge.FALLING, level_mv=800),
        channels=[ChannelConfig(index=0, amplitude_mv=500)],
        digital_outputs=[DigitalOutput(x_line=1, source_bit=DigitalBitSource.BIT15)],
    )
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
    sets = _sets("set32")
    assert sets[R.SPC_TRIG_ORMASK] == R.SPC_TMASK_EXT0
    assert sets[R.SPC_TRIG_EXT0_MODE] == R.SPC_TM_NEG
    assert sets[R.SPC_TRIG_EXT0_LEVEL0] == 800
    x1_reg = R.SPCM_X0_MODE + 1 * (R.SPCM_X1_MODE - R.SPCM_X0_MODE)
    expected = (R.SPCM_XMODE_DIGOUT | R.SPCM_XMODE_DIGOUTSRC_CH0
                | R.SPCM_XMODE_DIGOUTSRC_BIT15)
    assert sets[x1_reg] == expected
    print("[ok] Externer Trigger + Digitalausgang")


def test_sequence_mode():
    pyspcm.reset_recording()
    cfg = CardConfig(
        replay_mode=ReplayMode.SEQUENCE,
        channels=[ChannelConfig(index=0, amplitude_mv=1000)],
        max_segments=4,
        start_step=0,
    )
    segs = [
        Segment(index=0, data=waveforms.sine(2048)),
        Segment(index=1, data=waveforms.square(2048)),
        Segment(index=2, data=waveforms.ramp(2048)),
    ]
    steps = [
        SequenceStep(0, segment=0, loops=5, next_step=1,
                     end_condition=StepEndCondition.ALWAYS),
        SequenceStep(1, segment=1, loops=3, next_step=2,
                     end_condition=StepEndCondition.ON_TRIGGER),
        SequenceStep(2, segment=2, loops=1, next_step=0,
                     end_condition=StepEndCondition.END),
    ]
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
        awg.load_sequence(segs, steps)
        awg.start(enable_trigger=True)

    sets = _sets("set32")
    assert sets[R.SPC_CARDMODE] == R.SPC_REP_STD_SEQUENCE
    assert sets[R.SPC_SEQMODE_MAXSEGMENTS] == 4
    assert sets[R.SPC_SEQMODE_STARTSTEP] == 0
    # 3 Segmente -> 3 DMA-Transfers
    assert len(pyspcm.transfers) == 3

    sets64 = _sets("set64")
    # Step 1 Encoding pruefen: ON_TRIGGER, loops=3, next=2, segment=1
    step1_reg = R.SPC_SEQMODE_STEPMEM0 + 1
    expected = (0x40000003 << 32) | 0x00020001
    assert sets64[step1_reg] == expected, hex(sets64[step1_reg])
    # Step 2: END, loops=1, next=0, segment=2
    step2_reg = R.SPC_SEQMODE_STEPMEM0 + 2
    expected2 = (0x80000001 << 32) | 0x00000002
    assert sets64[step2_reg] == expected2, hex(sets64[step2_reg])
    print("[ok] Sequenz-Modus (Segmente + Step-Encoding)")


def test_sequence_guards():
    cfg = CardConfig(replay_mode=ReplayMode.SEQUENCE, max_segments=2,
                     channels=[ChannelConfig(index=0)])
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
        # Step referenziert nicht geladenes Segment
        try:
            awg.load_sequence(
                [Segment(0, waveforms.dc(64, 0.0))],
                [SequenceStep(0, segment=5, end_condition=StepEndCondition.END)],
            )
            assert False, "erwartete SpectrumConfigError"
        except SpectrumConfigError:
            pass
    print("[ok] Sequenz-Schutzpruefungen")


def test_continuous_and_restart_modes():
    # CONTINUOUS mit endlosen Loops (0)
    pyspcm.reset_recording()
    cfg = CardConfig(replay_mode=ReplayMode.CONTINUOUS, loops=0,
                     channels=[ChannelConfig(index=0)])
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
        awg.load_single(waveforms.sine(1024))
    assert _sets("set32")[R.SPC_CARDMODE] == R.SPC_REP_STD_CONTINUOUS
    assert _sets("set64")[R.SPC_LOOPS] == 0            # endlos
    assert _sets("set64")[R.SPC_MEMSIZE] == 1024

    # SINGLE_RESTART mit fester Wiederholungszahl
    pyspcm.reset_recording()
    cfg = CardConfig(replay_mode=ReplayMode.SINGLE_RESTART, loops=7,
                     channels=[ChannelConfig(index=0)])
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
        awg.load_single(waveforms.sine(512))
    assert _sets("set32")[R.SPC_CARDMODE] == R.SPC_REP_STD_SINGLERESTART
    assert _sets("set64")[R.SPC_LOOPS] == 7
    print("[ok] Continuous- + Single-Restart-Modus (Loops)")


def test_external_reference_clock():
    pyspcm.reset_recording()
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        clock=ClockConfig(mode=ClockMode.EXTERNAL_REFERENCE,
                          reference_clock_hz=10_000_000,
                          sample_rate_hz=1_250_000_000,
                          clock_output=True),
        channels=[ChannelConfig(index=0)],
    )
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
    sets = _sets("set32")
    assert sets[R.SPC_CLOCKMODE] == R.SPC_CM_EXTREFCLOCK
    assert sets[R.SPC_REFERENCECLOCK] == 10_000_000
    assert sets[R.SPC_CLOCKOUT] == 1
    assert _sets("set64")[R.SPC_SAMPLERATE] == 1_250_000_000
    print("[ok] Externer Referenztakt")


def test_multiple_digital_outputs():
    pyspcm.reset_recording()
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        channels=[ChannelConfig(index=0)],
        digital_outputs=[
            DigitalOutput(x_line=0, source_bit=DigitalBitSource.BIT15),
            DigitalOutput(x_line=1, source_bit=DigitalBitSource.BIT14),
            DigitalOutput(x_line=2, source_bit=DigitalBitSource.BIT13),
        ],
    )
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
    sets = _sets("set32")
    for line, bitflag in ((0, R.SPCM_XMODE_DIGOUTSRC_BIT15),
                          (1, R.SPCM_XMODE_DIGOUTSRC_BIT14),
                          (2, R.SPCM_XMODE_DIGOUTSRC_BIT13)):
        reg = R.SPCM_X0_MODE + line * (R.SPCM_X1_MODE - R.SPCM_X0_MODE)
        expected = R.SPCM_XMODE_DIGOUT | R.SPCM_XMODE_DIGOUTSRC_CH0 | bitflag
        assert sets[reg] == expected, (line, hex(sets[reg]))
    print("[ok] Mehrere Digitalausgaenge (X0/X1/X2)")


def test_many_segments_long_chain():
    pyspcm.reset_recording()
    n = 8
    cfg = CardConfig(replay_mode=ReplayMode.SEQUENCE, max_segments=8,
                     channels=[ChannelConfig(index=0)], start_step=0)
    segs = [Segment(i, waveforms.dc(256, (i - 4) / 8.0)) for i in range(n)]
    # Kette 0->1->...->7, letzter Step END; grosse Loop-Zahl testen
    steps = []
    for i in range(n):
        end = StepEndCondition.END if i == n - 1 else StepEndCondition.ALWAYS
        loops = 100000 if i == 0 else (i + 1)
        steps.append(SequenceStep(i, segment=i, loops=loops,
                                  next_step=(i + 1) % n, end_condition=end))
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
        awg.load_sequence(segs, steps)
        awg.start(enable_trigger=True)

    assert _sets("set32")[R.SPC_SEQMODE_MAXSEGMENTS] == 8
    assert len(pyspcm.transfers) == n
    sets64 = _sets("set64")
    # jedes Step-Encoding rekonstruieren und vergleichen
    for st in steps:
        flag = {StepEndCondition.ALWAYS: 0x00000000,
                StepEndCondition.END: 0x80000000}[st.end_condition]
        high = flag | (st.loops & 0x000FFFFF)
        low = ((st.next_step << 16) & 0xFFFF0000) | (st.segment & 0x0000FFFF)
        expected = (high << 32) | low
        reg = R.SPC_SEQMODE_STEPMEM0 + st.step_index
        assert sets64[reg] == expected, (st.step_index, hex(sets64[reg]))
    print("[ok] Viele Segmente + lange Step-Kette (inkl. grosser Loop-Zahl)")


def test_channel_params_and_stop_levels():
    for level, const in (("zero", R.SPCM_STOPLVL_ZERO), ("low", R.SPCM_STOPLVL_LOW),
                         ("high", R.SPCM_STOPLVL_HIGH), ("hold", R.SPCM_STOPLVL_HOLDLAST)):
        pyspcm.reset_recording()
        cfg = CardConfig(channels=[ChannelConfig(index=0, amplitude_mv=2500,
                                                 offset_mv=-200, filter_on=True,
                                                 stop_level=level)])
        with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
            awg.apply_config()
        sets = _sets("set32")
        assert sets[R.SPC_AMP0] == 2500
        assert sets[R.SPC_OFFS0] == -200
        assert sets[R.SPC_FILTER0] == 1
        assert sets[R.SPC_CH0_STOPLEVEL] == const, level
    print("[ok] Kanalparameter (Amplitude/Offset/Filter/Stop-Level)")


def test_ext1_trigger():
    pyspcm.reset_recording()
    cfg = CardConfig(
        trigger=TriggerConfig(source=TriggerSource.EXTERNAL1,
                              edge=TriggerEdge.RISING, level_mv=1200,
                              trigger_out=True),
        channels=[ChannelConfig(index=0)],
    )
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
    sets = _sets("set32")
    assert sets[R.SPC_TRIG_ORMASK] == R.SPC_TMASK_EXT1
    assert sets[R.SPC_TRIG_EXT1_MODE] == R.SPC_TM_POS
    assert sets[R.SPC_TRIG_EXT1_LEVEL0] == 1200
    assert sets[R.SPC_TRIGGEROUT] == 1
    print("[ok] Externer Trigger Ext1 + Trigger-Ausgang")


def test_two_channels():
    pyspcm.reset_recording()
    n = 2048
    cfg = CardConfig(
        replay_mode=ReplayMode.SINGLE,
        channels=[
            ChannelConfig(index=0, amplitude_mv=1000, offset_mv=0),
            ChannelConfig(index=1, amplitude_mv=500, offset_mv=100, filter_on=True),
        ],
    )
    # interleaved: ch0[0], ch1[0], ch0[1], ch1[1], ...  -> Laenge 2*n
    data = waveforms.interleave(waveforms.sine(n), waveforms.ramp(n))
    assert len(data) == 2 * n
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        assert awg.identity()["num_channels"] == 2
        awg.apply_config()
        awg.load_single(data)

    sets = _sets("set32")
    assert sets[R.SPC_CHENABLE] == 0b11               # beide Kanaele (CH0|CH1)
    assert sets[R.SPC_AMP0] == 1000
    assert sets[R.SPC_AMP1] == 500                    # Kanal 1 ueber Stride
    assert sets[R.SPC_OFFS1] == 100
    assert sets[R.SPC_FILTER1] == 1
    # Speichergroesse ist Samples PRO Kanal -> n (nicht 2*n)
    assert _sets("set64")[R.SPC_MEMSIZE] == n
    print("[ok] Zweikanalbetrieb (Enable-Maske, per-Kanal-Register, interleaved)")


def test_channel_index_guards():
    # Kanalindex ausserhalb 0..1
    cfg = CardConfig(channels=[ChannelConfig(index=2)])
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        try:
            awg.apply_config()
            assert False, "erwartete SpectrumConfigError"
        except SpectrumConfigError:
            pass
    # doppelter Kanalindex
    cfg = CardConfig(channels=[ChannelConfig(index=0), ChannelConfig(index=0)])
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        try:
            awg.apply_config()
            assert False, "erwartete SpectrumConfigError"
        except SpectrumConfigError:
            pass
    print("[ok] Kanalindex-Schutzpruefungen (Bereich + Duplikate)")


def test_more_guards():
    # ungueltige X-Line
    try:
        DigitalOutput(x_line=3).validate()
        assert False
    except SpectrumConfigError:
        pass
    # loops ausserhalb des zulaessigen Bereichs
    try:
        SequenceStep(0, segment=0, loops=0).validate()
        assert False
    except SpectrumConfigError:
        pass
    try:
        SequenceStep(0, segment=0, loops=SequenceStep.LOOP_MAX + 1).validate()
        assert False
    except SpectrumConfigError:
        pass
    # ungueltiger stop_level
    try:
        ChannelConfig(stop_level="foo").validate()
        assert False
    except SpectrumConfigError:
        pass
    # load_single im SEQUENCE-Modus verboten
    cfg = CardConfig(replay_mode=ReplayMode.SEQUENCE, channels=[ChannelConfig(0)])
    with SpectrumM4i6631("/dev/spcm0", cfg) as awg:
        awg.apply_config()
        try:
            awg.load_single(waveforms.dc(64, 0.0))
            assert False
        except SpectrumConfigError:
            pass
    print("[ok] Weitere Schutzpruefungen")


def main():
    test_config_validation()
    test_waveforms()
    test_single_mode()
    test_external_trigger_and_digital()
    test_sequence_mode()
    test_sequence_guards()
    test_continuous_and_restart_modes()
    test_external_reference_clock()
    test_multiple_digital_outputs()
    test_many_segments_long_chain()
    test_channel_params_and_stop_levels()
    test_ext1_trigger()
    test_two_channels()
    test_channel_index_guards()
    test_more_guards()
    print("\nAlle Offline-Tests bestanden.")


if __name__ == "__main__":
    main()
