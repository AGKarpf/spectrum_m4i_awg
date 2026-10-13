"""Import SPCM register constants, driver functions and error codes centrally.
Prefer Spectrum spcm_core, which binds to installed native card drivers and
provides regs/spcerr. Fall back to classic pyspcm and regs modules supplied in
the SPCM Examples/python directory on PYTHONPATH. SPECTRUM_AWG_BACKEND selects
auto, spcm_core or pyspcm; _SPCM_BACKEND identifies the selected implementation."""

from __future__ import annotations

import os

# Optional backend selection through an environment variable:
# SPECTRUM_AWG_BACKEND=spcm_core -> try spcm_core only
# SPECTRUM_AWG_BACKEND=pyspcm -> try classic driver / stubs only
# (unset or auto) -> prefer spcm_core, otherwise pyspcm
_FORCED = os.environ.get("SPECTRUM_AWG_BACKEND", "auto").lower()
_TRY_SPCM_CORE = _FORCED in ("auto", "spcm_core")
_TRY_PYSPCM = _FORCED in ("auto", "pyspcm")

_SPCM_BACKEND = None

_core_err = None
if _TRY_SPCM_CORE:
    try:
        # 1) Preferred: official spcm_core pip package
        from spcm_core import *          # noqa: F401,F403 (driver functions and ctypes types)
        from spcm_core.regs import *     # noqa: F401,F403 (register constants)
        try:
            from spcm_core.spcerr import *  # noqa: F401,F403 (error codes, ERR_OK, ...)
        except ImportError:
            pass  # ERR_OK is normally included by from spcm_core import *
        _SPCM_BACKEND = "spcm_core"
    except ImportError as exc:
        _core_err = exc

if _SPCM_BACKEND is None and _TRY_PYSPCM:
    try:
        # 2) Classic driver: Python modules supplied with the card
        from pyspcm import *   # noqa: F401,F403
        from regs import *     # noqa: F401,F403
        try:
            from spcerr import *  # noqa: F401,F403
        except ImportError:
            pass
        _SPCM_BACKEND = "pyspcm"
    except ImportError:
        pass

if _SPCM_BACKEND is None:  # pragma: no cover - depends on target environment
    raise ImportError(
            "Spectrum SPCM driver not found.\n"
            "Recommended: 'pip install spcm_core' (requires installed native "
            "card drivers).\n"
            "Alternatively add pyspcm and regs from the "
            "SPCM installation directory to PYTHONPATH.\n"
            f"See README.md. (SPECTRUM_AWG_BACKEND={_FORCED})"
        ) from _core_err
