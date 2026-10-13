"""Exceptions raised by the Spectrum AWG library."""

from __future__ import annotations


class SpectrumError(Exception):
    """Base exception for this library."""


class SpectrumDriverError(SpectrumError):
    """A native SPCM call returned an error.
    code is the numeric ERR_* value; register identifies the failing register or
    command if known; text is the native spcm_dwGetErrorInfo_i32 explanation."""

    def __init__(self, message: str, code: int | None = None,
                 register: int | None = None, text: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.register = register
        self.text = text


class SpectrumConfigError(SpectrumError):
    """Invalid or conflicting settings detected before a driver call."""


class SpectrumNotConnectedError(SpectrumError):
    """An operation was requested with no open card."""
