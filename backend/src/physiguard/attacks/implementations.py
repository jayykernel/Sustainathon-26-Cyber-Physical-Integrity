"""AT1–AT6 hooks, each constrained by its documented knowledge boundary."""

from __future__ import annotations

from copy import deepcopy

import numpy as np

from ..charger import ChargeProfile, execute_request
from ..config import Config
from ..plant import Plant
from ..twin import Twin, twin_ocv_lookup
from .base import (
    AttackBase,
    AttackContext,
    AttackDefinition,
    OracleContext,
    ReplayContext,
    Telemetry,
    TruthState,
)


class AT1Spike(AttackBase):
    """Short temperature spikes and small voltage glitches."""

    attack_id = "AT1"

    def apply(
        self,
        t_s: float,
        truth: TruthState,
        reported: Telemetry,
        rng: np.random.Generator,
        ctx: AttackContext,
    ) -> Telemetry:
        del truth, ctx
        result = reported.copy()
        if not self.is_active(t_s):
            return result
        elapsed = t_s - self.onset_s
        period = int(self.parameters["pulse_period_s"])
        pulse_duration = int(self.parameters["pulse_duration_s"])
        if elapsed % period < pulse_duration:
            result["T_rep"] += float(self.parameters["temperature_spike_c"])
            glitch = float(self.parameters["voltage_glitch_v"])
            result["V_rep"] += float(rng.choice((-glitch, glitch)))
        return result


class AT2Drift(AttackBase):
    """Slowly under-report temperature at a configured per-minute rate."""

    attack_id = "AT2"

    def apply(
        self,
        t_s: float,
        truth: TruthState,
        reported: Telemetry,
        rng: np.random.Generator,
        ctx: AttackContext,
    ) -> Telemetry:
        del truth, rng, ctx
        result = reported.copy()
        if self.is_active(t_s):
            rate = float(self.parameters["temperature_drift_c_per_min"])
            result["T_rep"] -= rate * (t_s - self.onset_s) / 60.0
        return result


class AT3Replay(AttackBase):
    """Replay older clean telemetry while degrading physical cooling."""

    attack_id = "AT3"

    def apply(
        self,
        t_s: float,
        truth: TruthState,
        reported: Telemetry,
        rng: np.random.Generator,
        ctx: AttackContext,
    ) -> Telemetry:
        del truth, rng
        if not self.is_active(t_s):
            return reported.copy()
        if not isinstance(ctx, ReplayContext):
            raise ValueError("AT3 requires recorded attack-free telemetry")
        if not ctx.telemetry or not all(
            channel in ctx.telemetry for channel in ("V_rep", "I_rep", "T_rep")
        ):
            raise ValueError("AT3 replay telemetry is incomplete")
        trace_length = len(ctx.telemetry["V_rep"])
        if trace_length == 0:
            raise ValueError("AT3 replay telemetry must not be empty")
        delay = int(self.parameters["replay_delay_s"])
        replay_index = int(t_s - delay) % trace_length
        return {
            "V_rep": float(ctx.telemetry["V_rep"][replay_index]),
            "I_rep": float(ctx.telemetry["I_rep"][replay_index]),
            "T_rep": float(ctx.telemetry["T_rep"][replay_index]),
        }

    def physical(self, t_s: float, plant: object) -> None:
        if self.is_active(t_s):
            if not isinstance(plant, Plant):
                raise TypeError("AT3 physical payload requires a Plant instance")
            plant.set_cooling_degradation(float(self.parameters["cooling_Rth_factor"]))


class _TwinSynthesis(AttackBase):
    """Private twin state used by A1/A2 spoofers; no live actuator context."""

    def __init__(
        self,
        definition: AttackDefinition,
        config: Config,
        onset_range_s: tuple[int, int],
        seed: int,
    ) -> None:
        super().__init__(definition, config, onset_range_s, seed)
        self.model_config = deepcopy(config)
        error_pct = float(self.parameters["model_R0_error_pct"])
        self.model_config.twin.R0_n *= 1.0 + error_pct / 100.0
        self.twin = Twin(self.model_config)
        self.profile = ChargeProfile(self.model_config)
        self.estimated_current_a = 0.0
        self.cooling_model_enabled = False
        self.synthesis_initialized = False

    def _advance_model(self, current_a: float) -> tuple[float, float]:
        prediction = self.twin.step(current_a)
        request = self.profile.request(float(prediction[0]))
        self.estimated_current_a = execute_request(
            request, float(prediction[1]), self.model_config
        )
        return float(prediction[0]), float(prediction[1])

    def _synthesize(
        self,
        t_s: float,
        reported: Telemetry,
        rng: np.random.Generator,
        current_a: float,
        current_is_observed: bool = False,
    ) -> Telemetry:
        taking_over = self.is_active(t_s) and not self.synthesis_initialized
        if taking_over:
            # Calibrate the private model from the telemetry already visible at takeover.
            voltage_ocv = reported["V_rep"] - self.estimated_current_a * self.model_config.twin.R0_n
            ocv_values = np.asarray(self.model_config.twin.OCV_n, dtype=np.float64)
            soc_points = np.linspace(0.0, 1.0, ocv_values.size)
            soc = float(np.interp(voltage_ocv, ocv_values, soc_points))
            polarization = reported["V_rep"] - twin_ocv_lookup(soc, self.model_config)
            polarization -= self.estimated_current_a * self.model_config.twin.R0_n
            self.twin.x = np.array([soc, polarization, reported["T_rep"]], dtype=np.float64)
            self.synthesis_initialized = True
        if self.is_active(t_s) and not self.cooling_model_enabled:
            self.model_config.twin.R_th_n *= float(
                self.parameters.get("cooling_Rth_factor", 1.0)
            )
            self.cooling_model_enabled = True
        voltage_hat, temperature_hat = self._advance_model(current_a)
        if not self.is_active(t_s):
            return reported.copy()
        sensors = self.model_config.sensors
        return {
            "V_rep": voltage_hat + float(rng.normal(0.0, sensors.V_sigma)),
            "I_rep": (
                current_a
                if current_is_observed
                else current_a + float(rng.normal(0.0, sensors.I_sigma))
            ),
            "T_rep": temperature_hat + float(rng.normal(0.0, sensors.T_sigma)),
        }

    def physical(self, t_s: float, plant: object) -> None:
        if self.is_active(t_s):
            if not isinstance(plant, Plant):
                raise TypeError("model-synthesis physical payload requires a Plant instance")
            plant.set_cooling_degradation(float(self.parameters["cooling_Rth_factor"]))


class AT4ModelSynthesis(_TwinSynthesis):
    """A1 model-aware spoof, with no I_cmd or probe available in its context."""

    attack_id = "AT4"

    def apply(
        self,
        t_s: float,
        truth: TruthState,
        reported: Telemetry,
        rng: np.random.Generator,
        ctx: AttackContext,
    ) -> Telemetry:
        # Neither truth nor ctx is inspected: in particular no true I_cmd/probe is read.
        del truth, ctx
        # The attacker observes telemetry current; using it as a twin input does not
        # expose the hidden actuator command or any probe signal.
        return self._synthesize(
            t_s, reported, rng, reported["I_rep"], current_is_observed=True
        )


class AT5MaliciousCommand(AttackBase):
    """Force a valid 150 A request after the SOC trigger and random delay."""

    attack_id = "AT5"

    def __init__(
        self,
        definition: AttackDefinition,
        config: Config,
        onset_range_s: tuple[int, int],
        seed: int,
    ) -> None:
        super().__init__(definition, config, onset_range_s, seed)
        self.delay_s = float(self.rng.uniform(0.0, float(self.parameters["max_delay_s"])))
        self.soc_crossing_s: float | None = None
        self.attack_start_s: float | None = None

    def is_active(self, t_s: float) -> bool:
        return self.attack_start_s is not None and t_s >= self.attack_start_s

    def request(self, t_s: float, I_req: float, truth: TruthState) -> float:
        if self.soc_crossing_s is None and truth["soc_true"] >= float(
            self.parameters["soc_trigger"]
        ):
            self.soc_crossing_s = t_s
            self.attack_start_s = t_s + self.delay_s
        if self.is_active(t_s):
            return float(self.parameters["forced_current_a"])
        return I_req


class AT6Oracle(_TwinSynthesis):
    """A2 out-of-scope oracle spoof driven by the actual actuator current."""

    attack_id = "AT6"

    def apply(
        self,
        t_s: float,
        truth: TruthState,
        reported: Telemetry,
        rng: np.random.Generator,
        ctx: AttackContext,
    ) -> Telemetry:
        del truth
        if not isinstance(ctx, OracleContext):
            raise ValueError("AT6 requires its documented oracle I_cmd context")
        return self._synthesize(t_s, reported, rng, ctx.I_cmd)
