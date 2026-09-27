"""Unit conversions. Internal values are SI; these are for display and config."""

M_TO_FT = 3.28084
MS_TO_KT = 1.943844


def m_to_ft(m: float) -> float:
    return m * M_TO_FT


def ft_to_m(ft: float) -> float:
    return ft / M_TO_FT


def ms_to_kt(ms: float) -> float:
    return ms * MS_TO_KT


def kt_to_ms(kt: float) -> float:
    return kt / MS_TO_KT


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def mm_to_in(mm: float) -> float:
    return mm / 25.4
