"""Checked wrapper around SPCM ctypes calls.
Own a card handle, provide typed register access and DMA transfers, and translate
error codes into SpectrumDriverError with spcm_dwGetErrorInfo_i32 text."""

from __future__ import annotations

import ctypes
from typing import Sequence, Union

from . import _regs as spcm
from .exceptions import SpectrumDriverError, SpectrumNotConnectedError

try:  # numpy is optional but recommended for large waveforms
    import numpy as _np
    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    _np = None
    _HAS_NUMPY = False

# int16 type for the M4i.6631 16-bit DAC
_c_int16_p = ctypes.POINTER(ctypes.c_int16)

DataLike = Union["Sequence[int]", "object"]  # list[int] or numpy.ndarray(int16)


class SpcmDriver:
    """Own the handle and low-level register access for one SPCM card."""

    def __init__(self, device: str = "/dev/spcm0") -> None:
        """device: local /dev/spcm0, /dev/spcm1, ... or a network NETBOX resource
        such as TCPIP::192.168.1.10::inst0::INSTR."""
        self.device = device
        self._handle = None

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    @property
    def is_open(self) -> bool:
        return self._handle is not None

    def open(self) -> None:
        """Open the card; raise SpectrumDriverError if it cannot be found."""
        handle = spcm.spcm_hOpen(ctypes.create_string_buffer(self.device.encode("ascii")))
        if not handle:
            raise SpectrumDriverError(
                f"Card '{self.device}' could not be opened. "
                "Check driver installation and card visibility in Device Manager. "
                "Check the device string."
            )
        self._handle = handle

    def close(self) -> None:
        """Close the card; safe to call repeatedly."""
        if self._handle is not None:
            spcm.spcm_vClose(self._handle)
            self._handle = None

    def _require_handle(self):
        if self._handle is None:
            raise SpectrumNotConnectedError("No card is open.")
        return self._handle

    # ------------------------------------------------------------------ #
    # Register access
    # ------------------------------------------------------------------ #
    def set32(self, register: int, value: int) -> None:
        """Write a 32-bit register via spcm_dwSetParam_i32."""
        err = spcm.spcm_dwSetParam_i32(self._require_handle(), register, int(value))
        self._check(err, register)

    def set64(self, register: int, value: int) -> None:
        """Write a 64-bit register via spcm_dwSetParam_i64."""
        err = spcm.spcm_dwSetParam_i64(self._require_handle(), register, int(value))
        self._check(err, register)

    def get32(self, register: int) -> int:
        """Read a 32-bit register via spcm_dwGetParam_i32."""
        val = ctypes.c_int32(0)
        err = spcm.spcm_dwGetParam_i32(self._require_handle(), register, ctypes.pointer(val))
        self._check(err, register)
        return val.value

    def get64(self, register: int) -> int:
        """Read a 64-bit register via spcm_dwGetParam_i64."""
        val = ctypes.c_int64(0)
        err = spcm.spcm_dwGetParam_i64(self._require_handle(), register, ctypes.pointer(val))
        self._check(err, register)
        return val.value

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    def command(self, command_flags: int) -> None:
        """Issue one or more M2CMD commands through SPC_M2CMD."""
        self.set32(spcm.SPC_M2CMD, command_flags)

    # ------------------------------------------------------------------ #
    # Data transfer (PC -> card)
    # ------------------------------------------------------------------ #
    def transfer_to_card(self, data: DataLike, board_offset_bytes: int = 0) -> None:
        """Transfer int16 samples to card memory using blocking DMA.
        Accept a Python sequence or numpy int16 array. Interleave multiple channels.
        board_offset_bytes selects the target memory offset; sequence mode normally
        handles offsets for segments above zero itself."""
        handle = self._require_handle()
        buf, size_bytes = self._make_buffer(data)

        # Define DMA: PC -> card, data buffer, no notification (0 = blocking)
        err = spcm.spcm_dwDefTransfer_i64(
            handle,
            spcm.SPCM_BUF_DATA,
            spcm.SPCM_DIR_PCTOCARD,
            0,                                   # dwNotifySize (0 = entire block)
            ctypes.cast(buf, ctypes.c_void_p),   # pvDataBuffer
            board_offset_bytes,                  # qwBrdOffs
            size_bytes,                          # qwTransferLen
        )
        self._check(err, spcm.SPCM_BUF_DATA)

        # Start transfer and wait for completion
        self.command(spcm.M2CMD_DATA_STARTDMA | spcm.M2CMD_DATA_WAITDMA)

    @staticmethod
    def _make_buffer(data: DataLike):
        """Build a contiguous int16 buffer; return (ctypes buffer, size in bytes)."""
        if _HAS_NUMPY and isinstance(data, _np.ndarray):
            arr = _np.ascontiguousarray(data, dtype=_np.int16)
            size_bytes = arr.nbytes
            ptr = arr.ctypes.data_as(ctypes.c_void_p)
            # Retain the array on the pointer object to prevent garbage collection
            ptr._keepalive = arr  # type: ignore[attr-defined]
            return ptr, size_bytes

        # Fallback: Python sequence -> ctypes array
        n = len(data)
        arr_t = ctypes.c_int16 * n
        buf = arr_t(*[int(x) for x in data])
        return buf, ctypes.sizeof(buf)

    # ------------------------------------------------------------------ #
    # Error handling
    # ------------------------------------------------------------------ #
    def _check(self, err_code: int, register: int) -> None:
        """Check a driver return code and raise SpectrumDriverError on failure."""
        if err_code == spcm.ERR_OK:
            return
        text = self._error_text()
        raise SpectrumDriverError(
            f"SPCM error (code {err_code}) at register/command {register}: {text}",
            code=err_code,
            register=register,
            text=text,
        )

    def _error_text(self) -> str:
        """Read the native driver's latest error text."""
        if self._handle is None:
            return "<no handle>"
        buf = ctypes.create_string_buffer(spcm.ERRORTEXTLEN)
        spcm.spcm_dwGetErrorInfo_i32(self._handle, None, None, buf)
        return buf.value.decode("ascii", errors="replace")

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #
    def __enter__(self) -> "SpcmDriver":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
