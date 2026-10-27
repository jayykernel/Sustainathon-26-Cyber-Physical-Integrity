"""Real-cell electrical-model checks using public CALCE CS2 workbook logs."""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares  # type: ignore[import-untyped]

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS = {"m": _MAIN, "r": _REL}
_COLUMNS = {
    "Test_Time(s)": "time",
    "Cycle_Index": "cycle",
    "Current(A)": "current",
    "Voltage(V)": "voltage",
    "Discharge_Capacity(Ah)": "discharge_capacity",
}


@dataclass(frozen=True)
class TracePoint:
    """A measured discharge sample; time is seconds, current A, voltage V."""

    time_s: float
    current_a: float
    voltage_v: float
    discharge_ah: float


@dataclass(frozen=True)
class DischargeCycle:
    """One cell discharge record, identified by source file and cycle index."""

    measured_on: date
    source_file: str
    cycle_index: int
    capacity_origin_ah: float
    capacity_ah: float
    points: tuple[TracePoint, ...]


@dataclass(frozen=True)
class FitResult:
    """One-RC electrical parameters fitted only on training cycles."""

    r0_ohm: float
    r1_ohm: float
    tau_s: float
    ocv_nodes_v: tuple[float, ...]
    train_cycles: int
    train_samples: int
    train_rmse_v: float
    test_cycles: int
    test_samples: int
    test_rmse_v: float
    test_mae_v: float
    test_p95_abs_error_v: float


def parse_record_date(path: Path) -> date:
    """Parse CALCE names with month_day_year components (e.g. 10_04_10)."""
    match = re.search(r"_(\d{1,2})_(\d{1,2})_(\d{2})$", path.stem)
    if match is None:
        raise ValueError(f"Workbook filename does not contain a CALCE date: {path.name}")
    month, day, year = (int(value) for value in match.groups())
    return datetime.strptime(f"{month}-{day}-{year:02d}", "%m-%d-%y").date()


def _cell_column(reference: str) -> str:
    return "".join(char for char in reference if char.isalpha())


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(text.text or "" for text in item.findall(".//m:t", _NS))
        for item in root.findall("m:si", _NS)
    ]


def _channel_worksheet(archive: zipfile.ZipFile) -> str:
    """Find the workbook's single measured channel sheet across CS2 cell IDs."""
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    names = [
        sheet.attrib.get("name", "")
        for sheet in workbook.findall(".//m:sheet", _NS)
        if re.fullmatch(r"Channel_1-\d+", sheet.attrib.get("name", ""))
    ]
    if len(names) != 1:
        raise ValueError(f"Expected one Channel_1-NNN sheet, found {names}")
    return names[0]


def _worksheet_path(archive: zipfile.ZipFile, name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = next(
        (
            sheet.attrib.get(f"{{{_REL}}}id")
            for sheet in workbook.findall(".//m:sheet", _NS)
            if sheet.attrib.get("name") == name
        ),
        None,
    )
    if relationship_id is None:
        raise ValueError(f"Workbook is missing the {name!r} sheet")
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next(
        (
            rel.attrib.get("Target")
            for rel in relationships.findall(f"{{{_PKG_REL}}}Relationship")
            if rel.attrib.get("Id") == relationship_id
        ),
        None,
    )
    if target is None:
        raise ValueError(f"Workbook has no relationship for worksheet {name!r}")
    if target.startswith("/"):
        return target.lstrip("/")
    return f"xl/{target.removeprefix('xl/')}"


def load_discharge_cycles(path: Path) -> list[DischargeCycle]:
    """Read measured negative-current samples from a CALCE CS2 workbook."""
    records: dict[int, list[TracePoint]] = {}
    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        sheet_path = _worksheet_path(archive, _channel_worksheet(archive))
        with archive.open(sheet_path) as sheet:
            header: dict[str, str] = {}
            for _, element in ET.iterparse(sheet, events=("end",)):
                if element.tag != f"{{{_MAIN}}}row":
                    continue
                values: dict[str, str] = {}
                for cell in element.findall(f"{{{_MAIN}}}c"):
                    ref = cell.attrib.get("r", "")
                    value = cell.find(f"{{{_MAIN}}}v")
                    if not ref or value is None or value.text is None:
                        continue
                    raw = value.text
                    if cell.attrib.get("t") == "s":
                        raw = strings[int(raw)]
                    values[_cell_column(ref)] = raw
                if not header:
                    header = {column: values[column] for column in values}
                    indexes = {label: col for col, label in header.items() if label in _COLUMNS}
                    missing = set(_COLUMNS) - set(indexes)
                    if missing:
                        raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
                elif values:
                    index = int(float(values[indexes["Cycle_Index"]]))
                    current = float(values[indexes["Current(A)"]])
                    capacity = float(values[indexes["Discharge_Capacity(Ah)"]])
                    if current < -0.05 and capacity >= 0:
                        records.setdefault(index, []).append(
                            TracePoint(
                                time_s=float(values[indexes["Test_Time(s)"]]),
                                current_a=current,
                                voltage_v=float(values[indexes["Voltage(V)"]]),
                                discharge_ah=capacity,
                            )
                        )
                element.clear()

    measured_on = parse_record_date(path)
    cycles = []
    for index, points in records.items():
        ordered = tuple(sorted(points, key=lambda point: point.time_s))
        capacity_origin_ah = min(point.discharge_ah for point in ordered)
        capacity_ah = max(point.discharge_ah for point in ordered) - capacity_origin_ah
        if capacity_ah > 0.1 and len(ordered) >= 20:
            cycles.append(
                DischargeCycle(
                    measured_on, path.name, index, capacity_origin_ah, capacity_ah, ordered
                )
            )
    return cycles


def load_dataset(directory: Path) -> list[DischargeCycle]:
    """Load and chronologically order every CS2_33 workbook in a directory."""
    workbooks = sorted(directory.glob("CS2_33_*.xlsx"), key=parse_record_date)
    if not workbooks:
        raise FileNotFoundError(f"No CALCE CS2_33 workbooks found under {directory}")
    cycles = [cycle for path in workbooks for cycle in load_discharge_cycles(path)]
    cycles.sort(key=lambda cycle: (cycle.measured_on, cycle.cycle_index, cycle.source_file))
    if len(cycles) < 10:
        raise ValueError(f"Only {len(cycles)} usable discharge cycles found; need at least 10")
    return cycles


def _decimate(cycle: DischargeCycle, max_points: int) -> tuple[TracePoint, ...]:
    if len(cycle.points) <= max_points:
        return cycle.points
    indices = np.linspace(0, len(cycle.points) - 1, max_points, dtype=int)
    return tuple(cycle.points[int(index)] for index in np.unique(indices))


def predict_cycle_voltage(
    cycle: DischargeCycle,
    r0_ohm: float,
    r1_ohm: float,
    tau_s: float,
    ocv_nodes_v: NDArray[np.float64],
    max_points: int = 0,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Predict voltage using measured throughput as reference SOC for this test."""
    points: Iterable[TracePoint] = cycle.points
    if max_points > 0:
        points = _decimate(cycle, max_points)
    selected = tuple(points)
    soc = np.array(
        [
            1.0 - (point.discharge_ah - cycle.capacity_origin_ah) / cycle.capacity_ah
            for point in selected
        ]
    )
    current = np.array([point.current_a for point in selected])
    times = np.array([point.time_s for point in selected])
    voltage = np.array([point.voltage_v for point in selected])
    knots = np.linspace(0.0, 1.0, len(ocv_nodes_v))
    ocv = np.interp(soc, knots, ocv_nodes_v)

    polarization = np.zeros(len(selected), dtype=np.float64)
    for index in range(1, len(selected)):
        dt_s = max(0.0, float(times[index] - times[index - 1]))
        decay = float(np.exp(-dt_s / tau_s))
        polarization[index] = (
            polarization[index - 1] * decay + r1_ohm * (1.0 - decay) * current[index]
        )
    prediction = ocv + current * r0_ohm + polarization
    return prediction, voltage


def fit_voltage_model(
    training: list[DischargeCycle], testing: list[DischargeCycle], max_points_per_cycle: int = 100
) -> FitResult:
    """Fit OCV and one-RC electrical parameters on earlier cycles; score later cycles."""
    if len(training) < 3 or not testing:
        raise ValueError("At least three training cycles and one test cycle are required")
    knots = 11

    def predictions(
        parameters: NDArray[np.float64], cycles: list[DischargeCycle]
    ) -> list[NDArray[np.float64]]:
        r0, r1, tau = np.exp(parameters[:3])
        ocv = parameters[3:]
        return [
            predict_cycle_voltage(
                cycle, float(r0), float(r1), float(tau), ocv, max_points_per_cycle
            )[0]
            for cycle in cycles
        ]

    def objective(parameters: NDArray[np.float64]) -> NDArray[np.float64]:
        output = predictions(parameters, training)
        observed = [
            predict_cycle_voltage(cycle, 0.0, 0.0, 1.0, parameters[3:], max_points_per_cycle)[1]
            for cycle in training
        ]
        return np.concatenate(
            [pred - target for pred, target in zip(output, observed, strict=True)]
        )

    initial_ocv = np.linspace(2.8, 4.2, knots)
    lower = np.concatenate((np.log([1e-4, 1e-4, 1.0]), np.array([2.5, *([0.0] * (knots - 1))])))
    upper = np.concatenate((np.log([2.0, 2.0, 3600.0]), np.array([4.3, *([0.5] * (knots - 1))])))
    # Parameterize the OCV curve as a bounded base voltage plus nonnegative rises.
    initial_deltas = np.diff(initial_ocv)
    initial = np.concatenate((np.log([0.05, 0.05, 60.0]), [initial_ocv[0]], initial_deltas))

    def unpack(parameters: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.cumsum(parameters[3:])

    def constrained_objective(parameters: NDArray[np.float64]) -> NDArray[np.float64]:
        expanded = np.concatenate((parameters[:3], unpack(parameters)))
        return objective(expanded)

    fit = least_squares(
        constrained_objective,
        initial,
        bounds=(lower, upper),
        max_nfev=250,
        x_scale="jac",
    )
    fitted_ocv = unpack(fit.x)
    fitted_r0, fitted_r1, fitted_tau = np.exp(fit.x[:3])

    def errors(cycles: list[DischargeCycle]) -> NDArray[np.float64]:
        return np.concatenate(
            [
                predict_cycle_voltage(
                    cycle,
                    float(fitted_r0),
                    float(fitted_r1),
                    float(fitted_tau),
                    fitted_ocv,
                    max_points_per_cycle,
                )[0]
                - predict_cycle_voltage(cycle, 0.0, 0.0, 1.0, fitted_ocv, max_points_per_cycle)[1]
                for cycle in cycles
            ]
        )

    train_errors = errors(training)
    test_errors = errors(testing)
    return FitResult(
        r0_ohm=float(fitted_r0),
        r1_ohm=float(fitted_r1),
        tau_s=float(fitted_tau),
        ocv_nodes_v=tuple(float(value) for value in fitted_ocv),
        train_cycles=len(training),
        train_samples=int(train_errors.size),
        train_rmse_v=float(np.sqrt(np.mean(np.square(train_errors)))),
        test_cycles=len(testing),
        test_samples=int(test_errors.size),
        test_rmse_v=float(np.sqrt(np.mean(np.square(test_errors)))),
        test_mae_v=float(np.mean(np.abs(test_errors))),
        test_p95_abs_error_v=float(np.quantile(np.abs(test_errors), 0.95)),
    )


def fit_chronological_split(cycles: list[DischargeCycle], train_fraction: float = 0.7) -> FitResult:
    """Use the first chronological fraction for fitting and later cycles for test."""
    split = int(len(cycles) * train_fraction)
    training_pool = cycles[:split]
    if len(training_pool) > 150:
        indices = np.linspace(0, len(training_pool) - 1, 150, dtype=int)
        training_pool = [training_pool[int(index)] for index in np.unique(indices)]
    return fit_voltage_model(training_pool, cycles[split:])


def write_report(
    path: Path, cycles: list[DischargeCycle], fit: FitResult, archive_sha256: str
) -> None:
    """Write reproducibility metadata and measured real-cell fit results."""
    payload = {
        "dataset": "CALCE CS2_33 cell cycling logs",
        "source": "https://web.calce.umd.edu/batteries/data/CS2_33.zip",
        "description": "Single 1.1 Ah LiCoO2 prismatic cell; constant-current/constant-voltage cycling.",
        "archive_sha256": archive_sha256,
        "method": "Chronological 70/30 cycle split; evenly sample at most 150 cycles from the earlier fit pool; fit one-RC voltage model and monotone OCV curve; score every later held-out cycle.",
        "reference_soc": "Per-cycle logged discharge capacity normalized by that cycle's delivered capacity; reference throughput, not an online SOC estimate.",
        "scope_limitations": [
            "One small laboratory cell; not an EV pack or Tesla BMS.",
            "No cyberattack labels or attacked signal paths are present.",
            "The workbook provides no time-series cell-temperature channel; thermal-model validation is not possible.",
            "The measured-throughput SOC is a reference for voltage-model assessment and is unavailable as ground truth in deployment.",
            "This does not validate attack detection, command guard, vehicle response, or safety claims.",
        ],
        "records": {
            "discharge_cycles": len(cycles),
            "chronological_fit_pool_cycles": len(cycles) - fit.test_cycles,
            "held_out_cycles": fit.test_cycles,
            "first_cycle_date": cycles[0].measured_on.isoformat(),
            "last_cycle_date": cycles[-1].measured_on.isoformat(),
        },
        "fit": asdict(fit),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
