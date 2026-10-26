"""Regression tests for twin propagation and EKF numerical behavior."""

import numpy as np
import pytest
from scipy.stats import chi2

from physiguard.config import Config
from physiguard.plant import ocv_lookup
from physiguard.twin import EKF, NumericalError, Twin, twin_ocv_lookup


def test_twin_ocv_scalar_interpolation_matches_numpy_reference_and_propagates_nan() -> None:
    config = Config()
    table = np.asarray(config.twin.OCV_n, dtype=np.float64)
    points = np.linspace(0.0, 1.0, table.size)
    for soc in (0.013, 0.26, 0.543, 0.997, -0.1, 1.1):
        expected = float(np.interp(soc, points, table))
        assert twin_ocv_lookup(soc, config) == pytest.approx(expected)
    assert np.isnan(twin_ocv_lookup(float("nan"), config))


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


def test_ekf_fixed_size_update_matches_joseph_reference() -> None:
    """The scalar 2x2 solve preserves the generic Joseph update numerically."""
    config = Config()
    ekf = EKF(config)
    ekf.initialize(3.6, 35.0)
    ekf.predict(10.0)
    prior_x = ekf.x.copy()
    prior_p = ekf.P.copy()
    soc, v1, temperature = prior_x
    h = ekf._d_ocv_d_soc(float(soc))
    observation = np.array([[h, 1.0, 0.0], [0.0, 0.0, 1.0]])
    prediction = np.array(
        [twin_ocv_lookup(float(soc), config) + 10.0 * config.twin.R0_n + v1, temperature]
    )
    innovation = np.array([3.61, 35.05]) - prediction
    covariance = observation @ prior_p @ observation.T + ekf.R
    gain = np.linalg.solve(covariance, observation @ prior_p).T
    residual_map = np.eye(3) - gain @ observation
    expected_p = residual_map @ prior_p @ residual_map.T + gain @ ekf.R @ gain.T
    expected_x = prior_x + gain @ innovation

    result = ekf.update(3.61, 35.05, 10.0, I_meas=10.1)

    np.testing.assert_allclose(result["x_updated"], expected_x, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(ekf.P, expected_p, rtol=1e-11, atol=1e-12)


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


def test_ekf_nis_and_nees_are_consistent_on_a_synthetic_linear_system() -> None:
    """Linear OCV makes the battery EKF a known linear Gaussian filter here."""
    config = Config()
    config.twin.OCV_n = np.linspace(3.0, 4.2, 11).tolist()
    config.twin.T_amb_hat = 0.0
    config.sensors.V_sigma = 0.01
    config.sensors.T_sigma = 0.1
    rng = np.random.default_rng(20261026)
    ekf = EKF(config)
    process_noise = ekf.Q.copy()
    decay_v1 = np.exp(-config.simulation.dt / config.twin.tau1_n)
    decay_temp = 1.0 - config.simulation.dt / (config.twin.C_th_n * config.twin.R_th_n)
    transition = np.diag([1.0, decay_v1, decay_temp])
    state = np.array([0.4, 0.05, 0.3], dtype=np.float64)

    initial_measurement = 3.0 + 1.2 * state[0] + state[1]
    ekf.initialize(
        initial_measurement + rng.normal(0.0, config.sensors.V_sigma),
        state[2] + rng.normal(0.0, config.sensors.T_sigma),
    )
    nis_values: list[float] = []
    nees_values: list[float] = []
    burn_in = 500
    for index in range(2500):
        state = transition @ state + rng.multivariate_normal(np.zeros(3), process_noise)
        ekf.predict(0.0)
        voltage = 3.0 + 1.2 * state[0] + state[1]
        voltage += rng.normal(0.0, config.sensors.V_sigma)
        temperature = state[2] + rng.normal(0.0, config.sensors.T_sigma)
        result = ekf.update(voltage, temperature, 0.0, I_meas=0.0)
        if index >= burn_in:
            error = state - result["x_updated"]
            nees = float(error @ np.linalg.solve(result["P_updated"], error))
            nis_values.append(result["NIS"])
            nees_values.append(nees)

    samples = len(nis_values)
    for values, degrees_of_freedom in ((nis_values, 2), (nees_values, 3)):
        total = float(np.sum(values))
        lower = chi2.ppf(0.005, degrees_of_freedom * samples)
        upper = chi2.ppf(0.995, degrees_of_freedom * samples)
        assert lower <= total <= upper
