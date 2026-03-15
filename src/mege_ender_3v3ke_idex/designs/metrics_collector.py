import logging
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class LengthMetric:
    category: str
    stock_type: str
    part_name: str
    length_mm: float


_metrics: list[LengthMetric] = []


def reset_metrics():
    _metrics.clear()


def record_length_metric(
    category: str, stock_type: str, part_name: str, length_mm: float
):
    _metrics.append(
        LengthMetric(
            category=category,
            stock_type=stock_type,
            part_name=part_name,
            length_mm=round(float(length_mm), 3),
        )
    )


def _round_length_mm(length_mm: float) -> int:
    return int(float(length_mm) + 0.5)


def _format_length(length_mm: float) -> str:
    return str(_round_length_mm(length_mm))


def build_metrics_report_lines() -> list[str]:
    if not _metrics:
        return ["Cut stock metrics: no metrics recorded."]

    grouped_metrics = defaultdict(list)
    for metric in _metrics:
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

    return lines


def log_metrics_report(logger: logging.Logger):
    for line in build_metrics_report_lines():
        logger.info(line)
