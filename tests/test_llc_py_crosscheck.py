# -*- coding: utf-8 -*-
"""llc_py（纯 Python，生产打包路径） 与 llc_model（NumPy，权威） 数值一致性交叉验证。

保证：移除 matplotlib / numpy 后，生产路径的计算结果不会被忽略的漂移破坏。
"""

from __future__ import annotations

import os
import random
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import llc_model  # noqa: E402
import llc_py  # noqa: E402

K_SAMPLES = (1.5, 2.0, 3.3, 5.0, 6.7, 10.0)
Q_SAMPLES = (0.05, 0.1, 0.3, 0.5, 1.0, 3.0, 10.0)


@pytest.mark.parametrize("K", K_SAMPLES)
@pytest.mark.parametrize("Q", Q_SAMPLES)
def test_gain_matches_vectorized(K, Q):
    fn = np.array([0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0], dtype=float)
    a = llc_model.llc_gain(fn, K, Q)
    b = llc_py.llc_gain(fn.tolist(), K, Q)
    assert np.allclose(a, b, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("K", K_SAMPLES)
@pytest.mark.parametrize("Q", Q_SAMPLES)
def test_input_impedance_matches_vectorized(K, Q):
    fn = [0.3, 0.7, 1.0, 1.5, 3.0]
    z_model = [llc_model.llc_input_impedance_normalized(f, K, Q) for f in fn]
    z_py = llc_py.llc_input_impedance_normalized(fn, K, Q)
    for zm, zp in zip(z_model, z_py):
        assert abs(zm - zp) < 1e-12


@pytest.mark.parametrize("K", K_SAMPLES)
def test_boundary_gain_matches(K):
    fn = [0.41, 0.5, 0.7, 0.9, 0.99]
    a = llc_model.boundary_gain(np.array(fn), K)
    b = llc_py.boundary_gain(fn, K)
    assert np.allclose(a, np.array(b), rtol=1e-12, atol=1e-12, equal_nan=True)


@pytest.mark.parametrize("K", K_SAMPLES)
@pytest.mark.parametrize("Q", Q_SAMPLES)
def test_boundary_frequency_matches(K, Q):
    assert llc_py.boundary_frequency(K, Q) == pytest.approx(
        llc_model.boundary_frequency(K, Q), rel=1e-12)


def test_constants_identical():
    for name in ("FN_MIN", "FN_MAX", "N_CURVE_POINTS", "GAIN_CLIP", "DEFAULT_K",
                 "DEFAULT_Q", "DEFAULT_FN", "DEFAULT_FR_KHZ", "DEFAULT_YMAX",
                 "K_MIN", "K_MAX", "Q_MIN", "Q_MAX"):
        assert getattr(llc_py, name) == getattr(llc_model, name), name
    assert llc_py.Q_FAMILY == llc_model.Q_FAMILY


def test_input_region_matches():
    for K in (3.0, 5.0, 8.0):
        for Q in (0.3, 1.0):
            fb = llc_py.boundary_frequency(K, Q)
            for fn in (fb * 0.8, fb * 1.2):
                assert llc_py.input_region(fn, K, Q) == llc_model.input_region(fn, K, Q)


def test_format_result_text_has_boundary_marker():
    v = {
        "K": 5.0, "Q": 0.5, "fn": 1.1, "Mfn": 0.9,
        "fnp": 0.408, "Mfnp": 3.0, "fnr": 1.0, "Mfnr": 1.0,
        "fn_peak": 0.65, "Mpeak": 1.2, "fr_khz": 124.4, "ymax": 2.2,
        "region": "inductive", "fn_boundary": 0.648, "M_boundary": 1.174,
    }
    text = llc_py.format_result_text(v)
    assert "感性区" in text
    assert "fn_boundary" in text
    assert "∠Zin" in text