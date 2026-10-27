"""Undefended closed-loop execution harness for attack scenarios."""

from __future__ import annotations

from typing import TypedDict, cast

import numpy as np
from numpy.typing import NDArray

from ..charger import ChargeProfile, execute_request
from ..command_guard import CommandGuard
from ..config import Config, get_config, load_detection_config
from ..detectors.gain import evaluate_gain_window, load_gain_thresholds
from ..detectors.passive import PassiveDetectors
from ..detectors.probe import (
    ProbeScheduler,
    ProbeWindow,
    generate_probe_window,
    is_probe_current_safe,
)
from ..pipeline import run_pipeline
from ..plant import Plant, vary_unit_config
from ..response import ResponseEvent, ResponseManager, VirtualSensor
from ..sensors import Sensors
from ..twin import EKF, twin_ocv_lookup
from .base import (
    AttackBase,
    AttackContext,
    OracleContext,
    ReplayContext,
    Telemetry,
    TruthState,
    make_attack,
)


class AttackTrajectory(TypedDict):
    """Sampled truth, forged telemetry, control signals, and passive alarms."""

    t: NDArray[np.float64]
    soc_true: NDArray[np.float64]
    V_true: NDArray[np.float64]
    T_true: NDArray[np.float64]
    V_rep: NDArray[np.float64]
    I_rep: NDArray[np.float64]
    T_rep: NDArray[np.float64]
    I_req: NDArray[np.float64]
    I_base_cmd: NDArray[np.float64]
    I_cmd: NDArray[np.float64]
    attack_active: NDArray[np.bool_]
    B0_alarm: NDArray[np.bool_]
    B1_alarm: NDArray[np.bool_]
    B2_alarm: NDArray[np.bool_]
    CUSUM_V_alarm: NDArray[np.bool_]
    CUSUM_T_alarm: NDArray[np.bool_]
    CUSUM_I_alarm: NDArray[np.bool_]
    defended: bool
    response_state: NDArray[np.str_]
    command_unsafe: NDArray[np.bool_]
    command_tampered: NDArray[np.bool_]
    virtual_temperature: NDArray[np.float64]
    estimate_degraded: NDArray[np.bool_]
    events: list[ResponseEvent]
    probe_active: NDArray[np.bool_]
    probe_delta: NDArray[np.float64]
    B3_alarm: NDArray[np.bool_]
    probe_gain_alarm: NDArray[np.bool_]
    nis: NDArray[np.float64]
    nis_window_sum: NDArray[np.float64]
    innovation_v: NDArray[np.float64]
    innovation_i: NDArray[np.float64]
    innovation_t: NDArray[np.float64]
    estimate_soc: NDArray[np.float64]
    estimate_voltage: NDArray[np.float64]
    estimate_temperature: NDArray[np.float64]
    attack_onset_s: int | None
    cusum_v_score: NDArray[np.float64]
    cusum_i_score: NDArray[np.float64]
    cusum_t_score: NDArray[np.float64]
    probe_gain_v: list[float | None]
    probe_gain_i: list[float | None]


def run_attack_scenario(
    attack_id: str,
    seed: int,
    config: Config | None = None,
    duration_s: int | None = None,
    attack_config_path: str | None = None,
    defended: bool = False,
    operator_reset_at: float | None = None,
) -> AttackTrajectory:
    """Simulate one attack run, optionally adding command guard and response."""
    base_config = config or get_config()
    if duration_s is None:
        duration_s = base_config.simulation.duration
    if duration_s < 1:
        raise ValueError("duration_s must be at least one second")
    detection = load_detection_config(base_config=base_config)
    run_config = vary_unit_config(base_config, seed)
    run_config.detection = detection
    attack: AttackBase | None = (
        None
        if attack_id == "baseline"
        else make_attack(attack_id, run_config, seed, attack_config_path)
    )
    plant = Plant(run_config)
    sensors = Sensors(run_config, seed + 1)
    profile = ChargeProfile(run_config)
    monitor = PassiveDetectors(run_config)
    ekf = EKF(run_config)
    command_guard = CommandGuard(run_config) if defended else None
    response = ResponseManager(run_config) if defended else None
    virtual_sensor = VirtualSensor(run_config) if defended else None
    previous_current_a = 0.0

    replay_ctx: ReplayContext | None = None
    if attack_id == "AT3":
        clean = run_pipeline(
            run_config,
            seed=seed,
            duration_s=duration_s,
            unit_variation=False,
        )
        replay_ctx = ReplayContext(
            telemetry={
                "V_rep": clean["V_rep"],
                "I_rep": clean["I_rep"],
                "T_rep": clean["T_rep"],
            }
        )

    keys = (
        "t",
        "soc_true",
        "V_true",
        "T_true",
        "V_rep",
        "I_rep",
        "T_rep",
        "I_req",
        "I_base_cmd",
        "I_cmd",
    )
    samples: dict[str, list[float]] = {key: [] for key in keys}
    active_values: list[bool] = []
    b0_values: list[bool] = []
    b1_values: list[bool] = []
    b2_values: list[bool] = []
    cusum_values: dict[str, list[bool]] = {channel: [] for channel in ("V", "T", "I")}
    response_values: list[str] = []
    command_unsafe_values: list[bool] = []
    command_tampered_values: list[bool] = []
    virtual_temperature_values: list[float] = []
    estimate_degraded_values: list[bool] = []
    probe_active_values: list[bool] = []
    probe_delta_values: list[float] = []
    probe_gain_alarm_values: list[bool] = []
    nis_values: list[float] = []
    nis_window_values: list[float] = []
    innovation_v_values: list[float] = []
    innovation_i_values: list[float] = []
    innovation_t_values: list[float] = []
    estimate_soc_values: list[float] = []
    estimate_voltage_values: list[float] = []
    estimate_temperature_values: list[float] = []
    cusum_score_values: dict[str, list[float]] = {channel: [] for channel in ("V", "I", "T")}
    probe_gain_v_values: list[float | None] = []
    probe_gain_i_values: list[float | None] = []
    latest_probe_gain_v: float | None = None
    latest_probe_gain_i: float | None = None
    b3_values: list[bool] = []
    probe_scheduler = ProbeScheduler(run_config, seed + 2) if defended else None
    gain_thresholds = load_gain_thresholds(base_config) if defended else None
    probe_key = run_config.probe.key or f"validation-probe-key-{seed}"
    active_challenge: ProbeWindow | None = None
    active_challenge_mode = ""
    active_challenge_start = 0

    for index in range(duration_s):
        t_s = index * float(run_config.simulation.dt)
        truth: TruthState = {
            "soc_true": plant.soc,
            "V_true": plant.get_terminal_voltage(),
            "T_true": plant.temperature_c,
        }
        raw: Telemetry = sensors.read(truth["V_true"], previous_current_a, truth["T_true"])
        if attack_id == "AT6":
            attack_context: AttackContext = OracleContext(I_cmd=previous_current_a)
        elif replay_ctx is not None:
            attack_context = replay_ctx
        else:
            attack_context = AttackContext()
        reported = (
            attack.apply(t_s, truth, raw, attack.rng, attack_context) if attack is not None else raw
        )

        update = None
        decision = None
        if index == 0:
            ekf.initialize(reported["V_rep"], reported["T_rep"])
            passive_alarms: set[str] = set()
        else:
            ekf.predict(previous_current_a)
            update = ekf.update(
                reported["V_rep"],
                reported["T_rep"],
                previous_current_a,
                I_meas=reported["I_rep"],
            )
            decision = monitor.update(
                update["NIS"],
                update["nu"],
                update["innovation_std"],
                update["r_I"],
                reported["V_rep"],
                reported["I_rep"],
                reported["T_rep"],
            )
            passive_alarms = decision["alarms"]

        for channel in cusum_values:
            cusum_values[channel].append(f"CUSUM_{channel}" in passive_alarms)
            detector = monitor.cusum[channel]
            cusum_score_values[channel].append(max(detector.positive, detector.negative))

        requested = profile.request(reported["V_rep"])
        authorized_request = requested
        if attack is not None:
            requested = attack.request(t_s, requested, truth)
            attack.physical(t_s, plant)
        command_tampered = not np.isclose(requested, authorized_request, rtol=0.0, atol=1e-6)
        b0_alarm = any(alarm.startswith("RANGE_") for alarm in passive_alarms)
        b1_alarm = "NIS" in passive_alarms
        b2_alarm = b1_alarm or any(alarm.startswith("CUSUM_") for alarm in passive_alarms)

        command_unsafe = False
        virtual_temperature = reported["T_rep"]
        estimate_degraded = False
        response_state = "NORMAL"
        control_request = requested
        derate_temperature = reported["T_rep"]
        probe_mode = "NORMAL"
        probe_failed = False
        probe_challenge_completed = False
        probe_gain_alarm = False
        if defended:
            assert command_guard is not None and response is not None and virtual_sensor is not None
            assert gain_thresholds is not None
            window_samples = int(round(run_config.probe.window / run_config.simulation.dt))
            if (
                active_challenge is not None
                and index == active_challenge_start + window_samples
                and index <= len(probe_delta_values)
            ):
                window_start = active_challenge_start
                delta_window = np.asarray(probe_delta_values[window_start:index], dtype=np.float64)
                if (
                    delta_window.size == window_samples
                    and float(delta_window @ delta_window) > 1e-10
                ):
                    voltage_window = np.asarray(
                        [*samples["V_rep"][window_start + 1 : index], reported["V_rep"]],
                        dtype=np.float64,
                    )
                    current_window = np.asarray(
                        [*samples["I_rep"][window_start + 1 : index], reported["I_rep"]],
                        dtype=np.float64,
                    ) - np.asarray(samples["I_base_cmd"][window_start:index], dtype=np.float64)
                    gain_decision = evaluate_gain_window(
                        voltage_window,
                        current_window,
                        delta_window,
                        config=run_config,
                        g_min_v=gain_thresholds[0],
                        g_min_i=gain_thresholds[1],
                        initial_soc=samples["soc_true"][window_start],
                    )
                    probe_failed = gain_decision.detected_combined
                    probe_gain_alarm = probe_failed
                    probe_challenge_completed = True
                    latest_probe_gain_v = float(gain_decision.voltage.gain)
                    latest_probe_gain_i = float(gain_decision.current.gain)
            flagged_channels = {
                channel
                for channel, alarm in (("V", "CUSUM_V"), ("T", "CUSUM_T"))
                if alarm in passive_alarms
            }
            virtual_temperature, estimate_quality = virtual_sensor.update(
                reported["V_rep"],
                reported["T_rep"],
                previous_current_a,
                flagged_channels,
                force_degraded=response.state == "SAFE_MODE",
            )
            estimate_degraded = estimate_quality == "degraded"
            guard_result = command_guard.evaluate(
                requested,
                virtual_sensor.state,
                worst_case=response.state == "SAFE_MODE",
            )
            command_unsafe = guard_result.unsafe
            evidence_classes: set[str] = set()
            if b1_alarm:
                evidence_classes.add("passive_NIS")
            if any(alarm.startswith("CUSUM_") for alarm in passive_alarms):
                evidence_classes.add("CUSUM")
            if probe_gain_alarm:
                evidence_classes.add("probe_gain")
            snapshot = response.update(
                t_s,
                evidence_classes,
                probe_failed=probe_failed,
                command_tampered=command_tampered,
                prediction_violation=guard_result.violation,
                clean_challenge=(
                    probe_challenge_completed
                    and not evidence_classes
                    and not command_tampered
                    and not probe_failed
                ),
            )
            if (
                operator_reset_at is not None
                and t_s >= operator_reset_at
                and response.state == "SAFE_MODE"
            ):
                response.request_operator_reset(t_s)
                operator_reset_at = None
            if snapshot.safe_mode:
                guard_result = command_guard.evaluate(
                    requested, virtual_sensor.state, worst_case=True
                )
                command_unsafe = command_unsafe or guard_result.unsafe
            control_request = guard_result.applied_request_a
            response_state = snapshot.state
            probe_mode = snapshot.state
            if snapshot.use_virtual_temperature:
                derate_temperature = virtual_temperature
        applied = execute_request(control_request, derate_temperature, run_config)
        probe_delta = 0.0
        probe_active = False
        if defended:
            assert probe_scheduler is not None
            if probe_mode == "NORMAL":
                probe_active = probe_scheduler.is_active(t_s, "NORMAL")
                if probe_active:
                    challenge_index = probe_scheduler.window_index(t_s, "NORMAL")
                    challenge_start = int(
                        round(challenge_index * run_config.probe.period / run_config.simulation.dt)
                    )
                    if (
                        active_challenge is None
                        or active_challenge_mode != "NORMAL"
                        or active_challenge_start != challenge_start
                    ):
                        nonce = probe_scheduler.nonce_for(t_s, "NORMAL")
                        if nonce is None:
                            raise RuntimeError("normal probe window has no nonce")
                        active_challenge = generate_probe_window(
                            applied,
                            control_request,
                            int(round(run_config.probe.window / run_config.simulation.dt)),
                            key=probe_key,
                            nonce=nonce,
                            config=run_config,
                            plant=plant,
                        )
                        active_challenge_mode = "NORMAL"
                        active_challenge_start = challenge_start
                    offset = index - active_challenge_start
                    if active_challenge is not None and 0 <= offset < len(active_challenge.delta_I):
                        probe_delta = float(active_challenge.delta_I[offset])
            else:
                probe_active = True
                window_samples = int(round(run_config.probe.window / run_config.simulation.dt))
                if (
                    active_challenge is None
                    or active_challenge_mode != probe_mode
                    or index >= active_challenge_start + window_samples
                ):
                    nonce = probe_scheduler.nonce_for(t_s, probe_mode)
                    if nonce is None:
                        raise RuntimeError("continuous probe window has no nonce")
                    active_challenge = generate_probe_window(
                        applied,
                        control_request,
                        window_samples,
                        key=probe_key,
                        nonce=nonce,
                        config=run_config,
                        plant=plant,
                    )
                    active_challenge_mode = probe_mode
                    active_challenge_start = index
                offset = index - active_challenge_start
                if active_challenge is not None and 0 <= offset < len(active_challenge.delta_I):
                    probe_delta = float(active_challenge.delta_I[offset])
            if probe_active and is_probe_current_safe(applied + probe_delta, plant, run_config):
                applied += probe_delta
            else:
                probe_delta = 0.0
                probe_active = False
        if defended:
            response_values.append(response_state)
            command_unsafe_values.append(command_unsafe)
            virtual_temperature_values.append(float(virtual_temperature))
            estimate_degraded_values.append(estimate_degraded)
            probe_active_values.append(probe_active)
            probe_delta_values.append(probe_delta)
        command_tampered_values.append(command_tampered)

        state = {
            "t": t_s,
            "soc_true": truth["soc_true"],
            "V_true": truth["V_true"],
            "T_true": truth["T_true"],
            "V_rep": reported["V_rep"],
            "I_rep": reported["I_rep"],
            "T_rep": reported["T_rep"],
            "I_req": requested,
            "I_base_cmd": applied - probe_delta,
            "I_cmd": applied,
        }
        for key, value in state.items():
            samples[key].append(value)
        active_values.append(attack.is_active(t_s) if attack is not None else False)
        b0_values.append(b0_alarm)
        b1_values.append(b1_alarm)
        b2_values.append(b2_alarm)
        b3_values.append(defended and response_state != "NORMAL")
        probe_gain_alarm_values.append(probe_gain_alarm)
        probe_gain_v_values.append(latest_probe_gain_v)
        probe_gain_i_values.append(latest_probe_gain_i)
        nis_values.append(float(update["NIS"]) if update is not None else 0.0)
        nis_window_values.append(
            float(decision["nis_window_sum"])
            if decision is not None and decision["nis_window_sum"] is not None
            else 0.0
        )
        innovation_v_values.append(float(update["nu"][0]) if update is not None else 0.0)
        innovation_t_values.append(float(update["nu"][1]) if update is not None else 0.0)
        innovation_i_values.append(float(update["r_I"]) if update is not None else 0.0)
        estimate_soc_values.append(float(ekf.x[0]))
        estimate_temperature_values.append(float(ekf.x[2]))
        estimate_voltage_values.append(
            float(
                twin_ocv_lookup(float(ekf.x[0]), run_config)
                + previous_current_a * run_config.twin.R0_n
                + ekf.x[1]
            )
        )

        plant.step(applied)
        previous_current_a = applied

    return cast(
        AttackTrajectory,
        {
            **{key: np.asarray(values, dtype=np.float64) for key, values in samples.items()},
            "attack_active": np.asarray(active_values, dtype=np.bool_),
            "B0_alarm": np.asarray(b0_values, dtype=np.bool_),
            "B1_alarm": np.asarray(b1_values, dtype=np.bool_),
            "B2_alarm": np.asarray(b2_values, dtype=np.bool_),
            "CUSUM_V_alarm": np.asarray(cusum_values["V"], dtype=np.bool_),
            "CUSUM_T_alarm": np.asarray(cusum_values["T"], dtype=np.bool_),
            "CUSUM_I_alarm": np.asarray(cusum_values["I"], dtype=np.bool_),
            "defended": defended,
            "response_state": np.asarray(response_values, dtype=np.str_),
            "command_unsafe": np.asarray(command_unsafe_values, dtype=np.bool_),
            "command_tampered": np.asarray(command_tampered_values, dtype=np.bool_),
            "virtual_temperature": np.asarray(virtual_temperature_values, dtype=np.float64),
            "estimate_degraded": np.asarray(estimate_degraded_values, dtype=np.bool_),
            "events": response.events if response is not None else [],
            "probe_active": np.asarray(probe_active_values, dtype=np.bool_),
            "probe_delta": np.asarray(probe_delta_values, dtype=np.float64),
            "B3_alarm": np.asarray(b3_values, dtype=np.bool_),
            "probe_gain_alarm": np.asarray(probe_gain_alarm_values, dtype=np.bool_),
            "nis": np.asarray(nis_values, dtype=np.float64),
            "nis_window_sum": np.asarray(nis_window_values, dtype=np.float64),
            "innovation_v": np.asarray(innovation_v_values, dtype=np.float64),
            "innovation_i": np.asarray(innovation_i_values, dtype=np.float64),
            "innovation_t": np.asarray(innovation_t_values, dtype=np.float64),
            "estimate_soc": np.asarray(estimate_soc_values, dtype=np.float64),
            "estimate_voltage": np.asarray(estimate_voltage_values, dtype=np.float64),
            "estimate_temperature": np.asarray(estimate_temperature_values, dtype=np.float64),
            "attack_onset_s": attack.onset_s if attack is not None else None,
            "cusum_v_score": np.asarray(cusum_score_values["V"], dtype=np.float64),
            "cusum_i_score": np.asarray(cusum_score_values["I"], dtype=np.float64),
            "cusum_t_score": np.asarray(cusum_score_values["T"], dtype=np.float64),
            "probe_gain_v": probe_gain_v_values,
            "probe_gain_i": probe_gain_i_values,
        },
    )


def run_paired_scenario(
    attack_id: str,
    seed: int,
    config: Config | None = None,
    duration_s: int | None = None,
    attack_config_path: str | None = None,
    operator_reset_at: float | None = None,
) -> tuple[AttackTrajectory, AttackTrajectory]:
    """Run undefended and defended plants from identical seed and attack inputs."""
    undefended = run_attack_scenario(
        attack_id,
        seed,
        config=config,
        duration_s=duration_s,
        attack_config_path=attack_config_path,
        defended=False,
    )
    defended = run_attack_scenario(
        attack_id,
        seed,
        config=config,
        duration_s=duration_s,
        attack_config_path=attack_config_path,
        defended=True,
        operator_reset_at=operator_reset_at,
    )
    return undefended, defended
