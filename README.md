# spectrum_awg — Steuerbibliothek für Spectrum M4i.6631-x8 (AWG)

Eine Python-Klassenbibliothek zur **Konfiguration** und zum **Betrieb** einer
Spectrum Instrumentation **M4i.6631-x8** (Arbitrary Waveform Generator, 2 Analog­kanäle,
16 Bit, bis 1.25 GS/s). Unterstützt den **Single-** und den **Sequenced-Modus** und
macht alle wesentlichen Parameter konfigurierbar: Kanäle (analog + digital), Takt,
Trigger, Dynamikbereich (Amplitude) sowie die Anzahl und Abfolge der Sequenzen.

> Die Bibliothek baut auf dem registerbasierten SPCM-Treiber (`pyspcm`/`regs`) auf,
> den Spectrum mit der Karte ausliefert. Sie kapselt die Register hinter sauberen
> Klassen und Dataclasses.

---

## Installation

1. **Kompilierte Kartentreiber installieren.** Den Spectrum SPCM-Treiber für die
   M4i-Karte installieren (liegt der Karte bei /
   [spectrum-instrumentation.com](https://spectrum-instrumentation.com)). Damit ist
   die Karte als `/dev/spcm0` erreichbar.

2. **SPCM-Python-Anbindung installieren (empfohlen: `spcm_core`).**

   ```bash
   pip install spcm_core
   ```

   `spcm_core` ist das offizielle pip-Paket von Spectrum. Es bindet sich zur Laufzeit
   an die in Schritt 1 installierten, kompilierten Treiber an — es müssen **keine**
   Python-Dateien von Hand auf den `PYTHONPATH` gelegt werden.

   *Alternative (klassischer Treiber):* Statt `spcm_core` können die mit dem
   SPCM-Paket ausgelieferten Module `pyspcm` und `regs`
   (`.../SPCM Examples/python`) auf den `PYTHONPATH` gelegt werden. Die Bibliothek
   erkennt beide Backends automatisch — siehe
   [`spectrum_awg/_regs.py`](spectrum_awg/_regs.py) (Auswahl über `_SPCM_BACKEND`).

3. **Diese Bibliothek installieren** (direkt von GitHub):

   ```bash
   pip install "spectrum-awg[driver] @ git+https://github.com/AGKarpf/spectrum_m4i_awg.git"
   ```

   Das Extra `[driver]` installiert `spcm_core` mit. Im ausgecheckten Repo für die
   Entwicklung: `pip install -e .[driver]`. `numpy` wird für die
   Waveform-Erzeugung benötigt.

---

## Schnellstart — Single-Modus

```python
from spectrum_awg import (
    CardConfig, ClockConfig, TriggerConfig, ChannelConfig,
    ReplayMode, ClockMode, TriggerSource, SpectrumM4i6631, waveforms,
)

config = CardConfig(
    replay_mode=ReplayMode.SINGLE,
    clock=ClockConfig(mode=ClockMode.INTERNAL_PLL, sample_rate_hz=1_250_000_000),
    trigger=TriggerConfig(source=TriggerSource.SOFTWARE),
    channels=[ChannelConfig(index=0, amplitude_mv=1000)],  # Dynamikbereich ±1 V
)

wf = waveforms.sine(num_samples=4096, periods=1.0)

with SpectrumM4i6631("/dev/spcm0", config) as awg:
    awg.apply_config()
    awg.load_single(wf)
    awg.start(enable_trigger=True)
    awg.force_trigger()
    awg.wait_ready()
```

## Schnellstart — Sequenced-Modus

```python
from spectrum_awg import (
    CardConfig, ReplayMode, ChannelConfig, Segment, SequenceStep,
    StepEndCondition, SpectrumM4i6631, waveforms,
)

config = CardConfig(
    replay_mode=ReplayMode.SEQUENCE,
    channels=[ChannelConfig(index=0, amplitude_mv=1000)],
    max_segments=4,     # Zweierpotenz
    start_step=0,
)

segments = [
    Segment(0, waveforms.sine(2048)),
    Segment(1, waveforms.square(2048)),
    Segment(2, waveforms.ramp(2048)),
]
steps = [
    SequenceStep(0, segment=0, loops=5, next_step=1, end_condition=StepEndCondition.ALWAYS),
    SequenceStep(1, segment=1, loops=3, next_step=2, end_condition=StepEndCondition.ON_TRIGGER),
    SequenceStep(2, segment=2, loops=1, next_step=0, end_condition=StepEndCondition.END),
]

with SpectrumM4i6631("/dev/spcm0", config) as awg:
    awg.apply_config()
    awg.load_sequence(segments, steps)
    awg.start(enable_trigger=True)
    awg.wait_ready()
```

Die Karte arbeitet die Steps **nicht linear** ab, sondern folgt der `next_step`-
Verkettung. Erst `StepEndCondition.END` beendet die Ausgabe. `ON_TRIGGER` wiederholt
den Step, bis ein (externer) Trigger eintrifft.

---

## Was ist konfigurierbar?

| Bereich | Klasse | Wichtige Felder |
|---|---|---|
| Wiedergabemodus | `CardConfig.replay_mode` | `SINGLE`, `SINGLE_RESTART`, `CONTINUOUS`, `SEQUENCE` |
| Takt | `ClockConfig` | `mode` (interne PLL / externe Referenz), `sample_rate_hz`, `reference_clock_hz`, `clock_output` |
| Trigger | `TriggerConfig` | `source` (Software/Ext0/Ext1), `edge`, `level_mv`, `trigger_out`, `ext_termination_50ohm` |
| Analogkanal | `ChannelConfig` | `enabled`, `output_on`, **`amplitude_mv` (Dynamikbereich)**, `offset_mv`, `filter_on`, `stop_level` |
| Digitalausgang | `DigitalOutput` | `x_line` (X0/X1/X2), `source_bit` (kostet Analogauflösung) |
| Sequenz | `Segment`, `SequenceStep` | `segment`, `loops`, `next_step`, `end_condition`, `max_segments`, `start_step` |

Der **Dynamikbereich** eines Analogkanals wird über `ChannelConfig.amplitude_mv`
(Register `SPC_AMPx`, Spitzenamplitude in mV an 50 Ω) gesetzt.

**Digitalkanäle:** Bei den M4i-AWG-Karten werden Digitalausgänge über die
Multi-Purpose-Lines (X0/X1/X2) realisiert, indem das höchstwertige Datenbit als
Digitalsignal ausgegeben wird. Jeder so genutzte Digitalausgang reduziert die
DAC-Auflösung des Analogsignals um 1 Bit.

---

## Projektstruktur

```
spectrum_m4i_awg/
├── spectrum_awg/
│   ├── __init__.py        # Öffentliche API
│   ├── card.py            # SpectrumM4i6631 — Config→Register, Single-/Sequence-Ablauf
│   ├── config.py          # Dataclasses: CardConfig, ClockConfig, TriggerConfig, ...
│   ├── enums.py           # ReplayMode, ClockMode, TriggerSource, StepEndCondition, ...
│   ├── driver.py          # SpcmDriver — fehlerprüfender ctypes-Wrapper + DMA
│   ├── waveforms.py       # int16-Waveform-Helfer (sine, square, ramp, interleave)
│   ├── exceptions.py      # Fehlerklassen
│   └── _regs.py           # Zentraler Import der SPCM-Treibersymbole
├── examples/
│   ├── single_mode_example.py
│   └── sequence_mode_example.py
├── tests/
│   ├── test_offline.py    # Hardwarefreie Tests gegen einen SPCM-Mock
│   └── stubs/             # Mock von pyspcm/regs (nur für Tests)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Testen

**Offline (ohne Treiber/Karte)** — ein Mock des SPCM-Treibers zeichnet alle
Registerzugriffe auf und prüft den kompletten Ablauf im Speicher:

```bash
py tests/test_offline.py
```

**Gegen eine simulierte Karte (Demo-Karte)** — im Spectrum Control Center lässt
sich eine Demo-Karte einrichten (z.B. als `/dev/spcm2`). Damit läuft der *echte*
`spcm_core`-Treiberpfad inkl. DMA und Sequenz-Setup durch, ohne physisches
Ausgangssignal:

```bash
py examples/simulated_card_test.py
```

### Backend-Auswahl erzwingen

Standardmäßig wird `spcm_core` bevorzugt, sonst der klassische Treiber. Über die
Umgebungsvariable `SPECTRUM_AWG_BACKEND` lässt sich das erzwingen:

| Wert | Wirkung |
|---|---|
| `auto` (Default) | `spcm_core` bevorzugen, sonst `pyspcm`/`regs` |
| `spcm_core` | nur `spcm_core` |
| `pyspcm` | nur klassischen Treiber / Test-Stubs |

Der Offline-Test setzt `SPECTRUM_AWG_BACKEND=pyspcm`, damit er hermetisch bleibt,
auch wenn `spcm_core` installiert ist.

---

## Einbindung in andere Projekte

Das Paket `spectrum_awg` liegt im Repo-Root. Andere Projekte tragen es als
Abhängigkeit in ihre `pyproject.toml` ein:

```toml
dependencies = [
    "spectrum-awg @ git+https://github.com/AGKarpf/spectrum_m4i_awg.git",
]
```

Danach im Code einfach:

```python
from spectrum_awg import SpectrumM4i6631, CardConfig, ReplayMode  # ...
```

> Hinweis: Der **Import-Name** ist `spectrum_awg`, der **Repo-/Ordnername**
> `spectrum_m4i_awg`, der **pip-Name** `spectrum-awg`.

## Wichtige Hinweise

- **Registerwerte gegen das Handbuch prüfen.** Die Zuordnung Enum → SPCM-Register in
  [`card.py`](spectrum_awg/card.py) folgt dem Standard-Schema der M4i-Serie. Bitte vor
  dem Produktiveinsatz mit dem *SPCM Hardware Manual* der M4i.6631 abgleichen
  (insbesondere Einheiten von `SPC_OFFSx` und zulässige `SPC_AMPx`-Bereiche).
- **Gerätestring** `/dev/spcm0` gilt für die erste lokale Karte (auch unter Windows).
  Weitere Karten: `/dev/spcm1` usw.; Netbox: VISA-artiger String.
- **Amplitudengrenzen** sind in `ChannelConfig.validate()` auf 1–2500 mV gesetzt;
  bei Bedarf an die tatsächlichen Kartengrenzen anpassen.
- Die Bibliothek überträgt Daten **blockierend** (`M2CMD_DATA_STARTDMA | WAITDMA`).
  Für sehr große / FIFO-gestreamte Waveforms wäre ein Notify-basierter Transfer zu ergänzen.
