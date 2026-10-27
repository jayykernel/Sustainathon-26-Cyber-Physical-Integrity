"""Regression coverage for the CALCE real-cell validation path."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from physiguard.eval.calce_validation import (
    DischargeCycle,
    TracePoint,
    fit_voltage_model,
    load_discharge_cycles,
    predict_cycle_voltage,
)


def _cycle(index: int, parameters: tuple[float, float, float], ocv: np.ndarray) -> DischargeCycle:
    """Build a deterministic measured-shape cycle with variable discharge load."""
    currents = [-0.55 if step % 30 < 15 else -0.2 for step in range(150)]
    capacity_ah = sum(-current for current in currents) * 30.0 / 3600.0
    provisional = [
        TracePoint(step * 30.0, current, 0.0, sum(-x for x in currents[: step + 1]) * 30 / 3600)
        for step, current in enumerate(currents)
    ]
    cycle = DischargeCycle(
        measured_on=date(2020, 1, 1),
        source_file=f"cycle-{index}",
        cycle_index=index,
        capacity_origin_ah=0.0,
        capacity_ah=capacity_ah,
        points=tuple(provisional),
    )
    prediction, _ = predict_cycle_voltage(cycle, *parameters, ocv)
    measured = tuple(
        TracePoint(point.time_s, point.current_a, float(prediction[pos]), point.discharge_ah)
        for pos, point in enumerate(cycle.points)
    )
    return DischargeCycle(
        cycle.measured_on,
        cycle.source_file,
        index,
        cycle.capacity_origin_ah,
        cycle.capacity_ah,
        measured,
    )


def _write_xlsx(path: Path, channel_name: str = "Channel_1-006") -> None:
    """Write a tiny workbook fixture without adding an XLSX dependency."""
    labels = ["Test_Time(s)", "Cycle_Index", "Current(A)", "Voltage(V)", "Discharge_Capacity(Ah)"]
    shared = "".join(f"<si><t>{label}</t></si>" for label in labels)
    rows = [
        '<row r="1">'
        + "".join(f'<c r="{col}1" t="s"><v>{i}</v></c>' for i, col in enumerate("ABCDE"))
        + "</row>"
    ]
    for row in range(2, 23):
        capacity = row / 100.0
        current = -0.5
        values = [row * 30, 1, current, 3.8 - capacity, 11.0 + capacity]
        cells = "".join(
            f'<c r="{col}{row}"><v>{value}</v></c>'
            for col, value in zip("ABCDE", values, strict=True)
        )
        rows.append(f'<row r="{row}">{cells}</row>')
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{shared}</sst>',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{channel_name}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(rows)
            + "</sheetData></worksheet>",
        )


def test_discharge_capacity_is_zeroed_per_cycle_when_loaded(tmp_path: Path) -> None:
    """CALCE file capacity is cumulative, but each cycle is normalized locally."""
    path = tmp_path / "CS2_33_10_04_10.xlsx"
    _write_xlsx(path)
    cycles = load_discharge_cycles(path)
    assert len(cycles) == 1
    assert np.isclose(cycles[0].capacity_origin_ah, 11.02)
    assert np.isclose(cycles[0].capacity_ah, 0.2)


def test_discharge_loader_accepts_cell_specific_channel_suffix(tmp_path: Path) -> None:
    path = tmp_path / "CS2_34_10_04_10.xlsx"
    _write_xlsx(path, channel_name="Channel_1-007")

    assert len(load_discharge_cycles(path)) == 1


def test_one_rc_fit_predicts_synthetic_heldout_cycles() -> None:
    """Chronological held-out fit remains low-error for a matching one-RC cell."""
    ocv = np.linspace(3.0, 4.2, 11)
    cycles = [_cycle(index, (0.08, 0.12, 85.0), ocv) for index in range(12)]
    fit = fit_voltage_model(cycles[:9], cycles[9:], max_points_per_cycle=80)
    assert fit.train_rmse_v < 0.005
    assert fit.test_rmse_v < 0.005
    assert fit.r0_ohm > 0
    assert fit.r1_ohm > 0
    assert fit.tau_s > 0
