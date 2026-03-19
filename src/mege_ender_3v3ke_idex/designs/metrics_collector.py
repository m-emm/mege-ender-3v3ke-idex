import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from poemai_utils.enum_utils import add_enum_attrs


class Material(Enum):
    ALUMINUM = "ALUMINUM"
    PLA = "PLA"
    PLA_CF = "PLA_CF"
    PETG = "PETG"
    PETG_CF = "PETG_CF"
    STEEL = "STEEL"
    TPU = "TPU"


add_enum_attrs(
    {
        Material.ALUMINUM: {"density_kg_per_m3": 2.70e3},
        Material.PLA: {"density_kg_per_m3": 1.24e3},
        Material.PLA_CF: {"density_kg_per_m3": 1.30e3},
        Material.PETG: {"density_kg_per_m3": 1.27e3},
        Material.PETG_CF: {"density_kg_per_m3": 1.30e3},
        Material.STEEL: {"density_kg_per_m3": 7.85e3},
        Material.TPU: {"density_kg_per_m3": 1.21e3},
    }
)


@dataclass(frozen=True)
class LengthMetric:
    category: str
    stock_type: str
    part_name: str
    length_mm: float


@dataclass(frozen=True)
class MarkMetric:
    stock_type: str
    part_name: str
    stock_length_mm: float
    mark_name: str
    position_mm: float


@dataclass(frozen=True)
class WeightMetric:
    assembly_id: str
    material: Material
    volume_mm3: float | None = None
    mass_kg: float | None = None
    part_id: str | None = None


_length_metrics: list[LengthMetric] = []
_mark_metrics: list[MarkMetric] = []
_weight_metrics: list[WeightMetric] = []


def reset_metrics():
    _length_metrics.clear()
    _mark_metrics.clear()
    _weight_metrics.clear()


def record_length_metric(
    category: str, stock_type: str, part_name: str, length_mm: float
):
    _length_metrics.append(
        LengthMetric(
            category=category,
            stock_type=stock_type,
            part_name=part_name,
            length_mm=round(float(length_mm), 3),
        )
    )


def record_mark_metric(
    stock_type: str,
    part_name: str,
    stock_length_mm: float,
    mark_name: str,
    position_mm: float,
):
    _mark_metrics.append(
        MarkMetric(
            stock_type=stock_type,
            part_name=part_name,
            stock_length_mm=round(float(stock_length_mm), 3),
            mark_name=mark_name,
            position_mm=round(float(position_mm), 3),
        )
    )


def calculate_mass_kg(material: Material, volume_mm3: float) -> float:
    return round(float(material.density_kg_per_m3) * float(volume_mm3) * 1e-9, 6)


def calculate_weight_g(material: Material, volume_mm3: float) -> float:
    return round(calculate_mass_kg(material, volume_mm3) * 1e3, 3)


def record_weight_metric(
    assembly_id: str,
    material: Material,
    volume_mm3: float,
    part_id: str | None = None,
):
    if not assembly_id:
        raise ValueError("assembly_id must be a non-empty string")
    if not isinstance(material, Material):
        raise TypeError("material must be an instance of Material")

    normalized_volume_mm3 = round(float(volume_mm3), 3)
    if normalized_volume_mm3 < 0:
        raise ValueError("volume_mm3 must be non-negative")

    _weight_metrics.append(
        WeightMetric(
            assembly_id=assembly_id,
            material=material,
            volume_mm3=normalized_volume_mm3,
            mass_kg=None,
            part_id=part_id,
        )
    )


def record_measured_mass_metric(
    assembly_id: str,
    material: Material,
    mass_kg: float,
    part_id: str | None = None,
):
    if not assembly_id:
        raise ValueError("assembly_id must be a non-empty string")
    if not isinstance(material, Material):
        raise TypeError("material must be an instance of Material")

    normalized_mass_kg = round(float(mass_kg), 6)
    if normalized_mass_kg < 0:
        raise ValueError("mass_kg must be non-negative")

    _weight_metrics.append(
        WeightMetric(
            assembly_id=assembly_id,
            material=material,
            volume_mm3=None,
            mass_kg=normalized_mass_kg,
            part_id=part_id,
        )
    )


def get_metric_mass_kg(metric: WeightMetric) -> float:
    if metric.mass_kg is not None:
        return metric.mass_kg
    if metric.volume_mm3 is None:
        raise ValueError("weight metric must define either mass_kg or volume_mm3")

    return calculate_mass_kg(metric.material, metric.volume_mm3)


def build_weight_totals_by_assembly_id() -> dict[str, float]:
    totals_by_assembly_id = defaultdict(float)
    for metric in _weight_metrics:
        totals_by_assembly_id[metric.assembly_id] += get_metric_mass_kg(metric)

    return {
        assembly_id: round(total_mass_kg, 6)
        for assembly_id, total_mass_kg in sorted(totals_by_assembly_id.items())
    }


def _round_length_mm(length_mm: float) -> int:
    return int(float(length_mm) + 0.5)


def _format_length(length_mm: float) -> str:
    return str(_round_length_mm(length_mm))


def _format_mass_kg(mass_kg: float) -> str:
    return f"{float(mass_kg):.6f} kg"


def build_cut_stock_report_lines() -> list[str]:
    if not _length_metrics and not _mark_metrics:
        return ["Cut stock metrics: no metrics recorded."]

    grouped_metrics = defaultdict(list)
    for metric in _length_metrics:
        key = (metric.category, metric.stock_type)
        grouped_metrics[key].append(metric)

    lines = ["Cut stock metrics:"]
    for category, stock_type in sorted(grouped_metrics):
        lines.append(f"{category} {stock_type}:")

        lengths_grouped = defaultdict(list)
        for metric in grouped_metrics[(category, stock_type)]:
            rounded_length_mm = _round_length_mm(metric.length_mm)
            lengths_grouped[rounded_length_mm].append(metric.part_name)

        for length_mm in sorted(lengths_grouped):
            part_names = sorted(lengths_grouped[length_mm])
            lines.append(f"  {_format_length(length_mm)} mm x{len(part_names)}")
            for part_name in part_names:
                lines.append(f"    - {part_name}")

    if _mark_metrics:
        lines.append("Stock marks:")

        grouped_marks = defaultdict(list)
        for mark_metric in _mark_metrics:
            key = (
                mark_metric.stock_type,
                mark_metric.part_name,
                _round_length_mm(mark_metric.stock_length_mm),
            )
            grouped_marks[key].append(mark_metric)

        for stock_type, part_name, stock_length_mm in sorted(grouped_marks):
            lines.append(
                f"{part_name} ({stock_type}, {_format_length(stock_length_mm)} mm):"
            )
            for mark_metric in sorted(
                grouped_marks[(stock_type, part_name, stock_length_mm)],
                key=lambda current_mark: (
                    _round_length_mm(current_mark.position_mm),
                    current_mark.mark_name,
                ),
            ):
                lines.append(
                    f"  mark at {_format_length(mark_metric.position_mm)} mm - {mark_metric.mark_name}"
                )

    return lines


def build_weight_report_lines() -> list[str]:
    if not _weight_metrics:
        return ["Weight metrics: no metrics recorded."]

    assembly_metrics = defaultdict(list)
    for metric in _weight_metrics:
        assembly_metrics[metric.assembly_id].append(metric)

    lines = ["Weight metrics:"]
    for assembly_id in sorted(assembly_metrics):
        material_totals = defaultdict(float)
        part_totals = defaultdict(float)
        for metric in assembly_metrics[assembly_id]:
            mass_kg = get_metric_mass_kg(metric)
            material_totals[metric.material] += mass_kg
            if metric.part_id:
                part_totals[(metric.part_id, metric.material)] += mass_kg

        total_mass_kg = round(sum(material_totals.values()), 6)
        lines.append(f"{assembly_id}: {_format_mass_kg(total_mass_kg)}")

        for material in sorted(
            material_totals, key=lambda current_material: current_material.name
        ):
            lines.append(
                f"  {material.name}: {_format_mass_kg(round(material_totals[material], 6))}"
            )

        for part_id, material in sorted(
            part_totals,
            key=lambda current_part: (current_part[0], current_part[1].name),
        ):
            lines.append(
                f"  {part_id} ({material.name}): {_format_mass_kg(round(part_totals[(part_id, material)], 6))}"
            )

    return lines


def build_metrics_report_lines() -> list[str]:
    if not _length_metrics and not _mark_metrics and not _weight_metrics:
        return ["Cut stock metrics: no metrics recorded."]

    lines = []
    if _length_metrics or _mark_metrics:
        lines.extend(build_cut_stock_report_lines())
    if _weight_metrics:
        if lines:
            lines.append("")
        lines.extend(build_weight_report_lines())

    return lines


def log_metrics_report(logger: logging.Logger):
    for line in build_metrics_report_lines():
        logger.info(line)
