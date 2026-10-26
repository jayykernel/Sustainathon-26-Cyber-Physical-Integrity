"""Regression tests for twin propagation and EKF numerical behavior."""

import numpy as np
import pytest

from physiguard.config import Config
from physiguard.plant import ocv_lookup
from physiguard.twin import EKF, NumericalError, Twin


def test_twin_step_uses_configured_charge_and_thermal_model() -> None:
    """Twin state follows the one-RC equations and returns voltage and temperature."""
    config = Config()
    twin = Twin(config)
    initial_soc = float(twin.x[0])

    predicted = twin.step(20.0)

    assert twin.x[0] - initial_soc == pytest.approx(
        config.plant.eta * 20.0 / (3600 * config.twin.Q_n)
    )
    assert predicted.shape == (2,)
    assert predicted[0] == pytest.approx(
        ocv_lookup(twin.x[0]) + 20.0 * config.twin.R0_n + twin.x[1]
    )
    assert predicted[1] == pytest.approx(twin.x[2])


def test_ekf_updates_state_and_keeps_covariance_symmetric() -> None:
    """A valid measurement update returns finite NIS and a symmetric covariance."""
    ekf = EKF(Config())
    ekf.initialize(3.6, 35.0)
    ekf.predict(10.0)

    result = ekf.update(3.61, 35.05, 10.0, I_meas=10.1)

    assert result["NIS"] >= 0
    assert result["r_I"] == pytest.approx(0.1)
    assert np.all(np.isfinite(result["x_updated"]))
    np.testing.assert_allclose(ekf.P, ekf.P.T, atol=1e-12)


def test_ekf_singular_innovation_covariance_raises_typed_error() -> None:
    """Singular innovation covariance does not fall back to an unstable pseudoinverse."""
    ekf = EKF(Config())
    ekf.initialize(3.6, 35.0)
    ekf.P[:] = 0.0
    ekf.R[:] = 0.0

    with pytest.raises(NumericalError, match="singular"):
        ekf.update(3.6, 35.0, 0.0, I_meas=0.0)


def test_compute_nis_restores_filter_state() -> None:
    """Diagnostic NIS evaluation leaves the live filter state unchanged."""
    ekf = EKF(Config())
    ekf.initialize(3.6, 35.0)
    state_before = ekf.x.copy()
    covariance_before = ekf.P.copy()

    nis, innovation = ekf.compute_NIS(3.61, 35.1, 5.0)

    assert nis >= 0
    assert innovation.shape == (2,)
    np.testing.assert_array_equal(ekf.x, state_before)
    np.testing.assert_array_equal(ekf.P, covariance_before)
