"""Small, dependency-free SVG bar chart renderer for low-spec Linux hosts."""
from __future__ import annotations

from html import escape
from math import ceil, isfinite
from pathlib import Path


def write_bar_chart(path: Path, title: str, unit: str, labels: list[str],
                    values: list[float], *, reference: float | None = None) -> None:
    """Plot one horizontal bar per label; designed for comparability, not decoration."""
    if not labels or len(labels) != len(values):
        return
    if not all(isfinite(float(v)) and v >= 0 for v in values):
        raise ValueError('Chart values must be nonnegative finite numbers')
    width, left, right, top, pitch, bottom = 1300, 500, 105, 100, 38, 65
    height = top + pitch * len(labels) + bottom
    area = width - left - right
    top_value = max(max(float(v) for v in values), reference or 0, 1e-9)
    top_value *= 1.12

    def fmt(value: float) -> str:
        if value >= 10000: return f'{value:,.0f}'
        if value >= 100: return f'{value:,.1f}'
        if value >= 10: return f'{value:,.2f}'
        return f'{value:.3f}'

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="35" y="39" font-family="sans-serif" font-size="24" font-weight="bold" fill="#222">{escape(title)}</text>',
             f'<text x="35" y="67" font-family="sans-serif" font-size="15" fill="#555">{escape(unit)}</text>']
    for k in range(5):
        tick = k * top_value / 4
        x = left + area * k / 4
        parts.append(f'<line x1="{x:.1f}" y1="{top-15}" x2="{x:.1f}" y2="{height-bottom+10}" stroke="#e3e3e3"/>')
        parts.append(f'<text x="{x:.1f}" y="{height-25}" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#555">{escape(fmt(tick))}</text>')
    if reference is not None:
        x = left + area * reference / top_value
        parts.append(f'<line x1="{x:.1f}" y1="{top-15}" x2="{x:.1f}" y2="{height-bottom+10}" stroke="#333" stroke-width="2" stroke-dasharray="6,4"/>')
        parts.append(f'<text x="{x+7:.1f}" y="{top-25}" font-family="sans-serif" font-size="13" fill="#444">Baseline {fmt(reference)}x</text>')
    for i, (label, value) in enumerate(zip(labels, values)):
        y = top + i * pitch
        # Keep path accessible by XML consumers; show full label in title too.
        label = str(label).replace('\n', ' / ')
        truncated = label if len(label) <= 63 else label[:60] + '...'
        parts.append(f'<text x="{left-15}" y="{y+17}" text-anchor="end" font-family="sans-serif" font-size="15" fill="#222"><title>{escape(label)}</title>{escape(truncated)}</text>')
        bar_width = max(0, area * float(value) / top_value)
        parts.append(f'<rect x="{left}" y="{y+3}" width="{bar_width:.2f}" height="22" rx="3" fill="#5675a2"/>')
        value_x = min(left + bar_width + 8, width - 70)
        parts.append(f'<text x="{value_x:.1f}" y="{y+20}" font-family="sans-serif" font-size="13" fill="#222">{escape(fmt(float(value)))}</text>')
    parts.append('</svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(parts), encoding='utf-8')
