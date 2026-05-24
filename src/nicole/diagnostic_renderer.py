from __future__ import annotations

from dataclasses import dataclass

from .errors import Diagnostic

__all__ = ["render_diagnostic", "render_diagnostic_error"]


@dataclass(frozen=True, slots=True)
class _RenderConfig:
    max_excerpt_lines: int = 8
    max_line_length: int = 160


def render_diagnostic(
    diagnostic: Diagnostic,
    *,
    max_excerpt_lines: int = 8,
    max_line_length: int = 160,
) -> str:
    config = _RenderConfig(
        max_excerpt_lines=max(1, max_excerpt_lines),
        max_line_length=max(1, max_line_length),
    )
    lines = [_header_line(diagnostic)]
    span = diagnostic.span
    if span is not None:
        lines.append(f"--> {span.source.path}:{span.line}:{span.column}")
        excerpt = _render_excerpt(diagnostic, config)
        if excerpt:
            lines.extend(excerpt)
    _append_metadata(lines, diagnostic)
    return "\n".join(lines)


def render_diagnostic_error(error: Exception, *, max_excerpt_lines: int = 8, max_line_length: int = 160) -> str:
    diagnostic = getattr(error, "diagnostic", None)
    if diagnostic is None:
        return str(error)
    return render_diagnostic(
        diagnostic,
        max_excerpt_lines=max_excerpt_lines,
        max_line_length=max_line_length,
    )


def _header_line(diagnostic: Diagnostic) -> str:
    return f"{diagnostic.severity.name} [{diagnostic.phase.name}/{diagnostic.code}] {diagnostic.message}"


def _append_metadata(lines: list[str], diagnostic: Diagnostic) -> None:
    if diagnostic.suggestion:
        lines.append(f"help: {diagnostic.suggestion}")
    for note in diagnostic.notes:
        lines.append(f"note: {note}")


def _render_excerpt(diagnostic: Diagnostic, config: _RenderConfig) -> list[str]:
    span = diagnostic.span
    if span is None:
        return []
    text = span.source.text
    if text is None:
        return []

    source_lines = text.splitlines()
    if not source_lines:
        source_lines = [""]

    start_line = _normalize_line(span.start.line, len(source_lines))
    end_line = _normalize_line(span.end.line, len(source_lines))
    if end_line < start_line:
        end_line = start_line

    selected = _select_lines(start_line, end_line, config.max_excerpt_lines)
    line_no_width = len(str(selected[-1])) if selected else 1

    rendered: list[str] = []
    omitted_marker_rendered = False
    for idx, line_no in enumerate(selected):
        if idx > 0 and line_no != selected[idx - 1] + 1 and not omitted_marker_rendered:
            rendered.append(f"{'.':>{line_no_width}} | ...")
            omitted_marker_rendered = True
        line_text = _line_text(source_lines, line_no)
        marker_bounds = _line_marker_bounds(
            span.start.line,
            span.start.column,
            span.end.line,
            span.end.column,
            line_no,
            line_text,
        )
        clipped_line, clipped_marker_bounds = _clip_line_and_marker(
            line_text,
            marker_bounds,
            config.max_line_length,
        )
        rendered.append(f"{line_no:>{line_no_width}} | {clipped_line}")
        marker = _line_marker(clipped_marker_bounds)
        if marker is not None:
            rendered.append(f"{'':>{line_no_width}} | {marker}")
    return rendered


def _select_lines(start_line: int, end_line: int, max_excerpt_lines: int) -> list[int]:
    all_lines = list(range(start_line, end_line + 1))
    if len(all_lines) <= max_excerpt_lines:
        return all_lines
    head_count = max(1, max_excerpt_lines // 2)
    tail_count = max(1, max_excerpt_lines - head_count)
    head = all_lines[:head_count]
    tail = all_lines[-tail_count:]
    return head + tail


def _line_text(source_lines: list[str], line_no: int) -> str:
    if 1 <= line_no <= len(source_lines):
        return source_lines[line_no - 1]
    return ""


def _normalize_line(line_no: int, line_count: int) -> int:
    if line_no < 1:
        return 1
    if line_no > line_count + 1:
        return line_count + 1
    return line_no


def _line_marker_bounds(
    start_line: int,
    start_column: int,
    end_line: int,
    end_column: int,
    line_no: int,
    line_text: str,
) -> tuple[int, int] | None:
    if line_no < start_line or line_no > end_line:
        return None

    text_len = len(line_text)
    start_col = max(1, start_column)
    end_col = max(1, end_column)

    if start_line == end_line:
        marker_start = min(start_col, text_len + 1)
        marker_end = min(max(marker_start, end_col), text_len + 1)
    elif line_no == start_line:
        marker_start = min(start_col, text_len + 1)
        marker_end = text_len + 1
    elif line_no == end_line:
        marker_start = 1
        marker_end = min(max(1, end_col), text_len + 1)
    else:
        marker_start = 1
        marker_end = text_len + 1

    return (marker_start, marker_end)


def _line_marker(marker_bounds: tuple[int, int] | None) -> str | None:
    if marker_bounds is None:
        return None
    marker_start, marker_end = marker_bounds
    marker_len = max(1, marker_end - marker_start)
    return f"{' ' * (marker_start - 1)}{'^' * marker_len}"


def _clip_line_and_marker(
    line_text: str,
    marker_bounds: tuple[int, int] | None,
    max_line_length: int,
) -> tuple[str, tuple[int, int] | None]:
    if len(line_text) <= max_line_length:
        return line_text, marker_bounds

    if marker_bounds is None:
        if max_line_length < 4:
            return line_text[:max_line_length], None
        visible = line_text[: max_line_length - 3] + "..."
        return visible, None

    marker_start, marker_end = marker_bounds
    marker_start_idx = max(0, marker_start - 1)
    marker_end_idx = max(marker_start_idx, marker_end - 1)

    content_space = max(1, max_line_length)
    desired_start = max(0, marker_start_idx - (content_space // 3))
    window_start = min(desired_start, max(0, len(line_text) - content_space))
    window_end = min(len(line_text), window_start + content_space)

    left_omitted = window_start > 0
    right_omitted = window_end < len(line_text)
    core = line_text[window_start:window_end]
    prefix, suffix, visible_core, core_visible_start = _fit_core_with_omission_markers(
        core,
        marker_start_idx=max(0, marker_start_idx - window_start),
        marker_end_idx=max(0, marker_end_idx - window_start),
        left_omitted=left_omitted,
        right_omitted=right_omitted,
        max_line_length=max_line_length,
    )
    visible = f"{prefix}{visible_core}{suffix}"

    visible_start = max(0, marker_start_idx - window_start - core_visible_start)
    visible_end = max(visible_start, marker_end_idx - window_start - core_visible_start)
    visible_start = min(visible_start, len(visible_core))
    visible_end = min(visible_end, len(visible_core))

    marker_start_clipped = len(prefix) + visible_start + 1
    marker_end_clipped = len(prefix) + visible_end + 1
    marker_end_clipped = max(marker_start_clipped, marker_end_clipped)
    marker_start_clipped = min(marker_start_clipped, len(visible))
    marker_end_clipped = min(max(marker_start_clipped, marker_end_clipped), len(visible))

    return visible, (marker_start_clipped, marker_end_clipped)


def _fit_core_with_omission_markers(
    core: str,
    *,
    marker_start_idx: int,
    marker_end_idx: int,
    left_omitted: bool,
    right_omitted: bool,
    max_line_length: int,
) -> tuple[str, str, str, int]:
    if max_line_length < 4:
        retained_index = min(max(0, marker_start_idx), max(0, len(core) - 1))
        core_start = min(retained_index, max(0, len(core) - max_line_length))
        return "", "", core[core_start : core_start + max_line_length], core_start

    prefix = "..." if left_omitted else ""
    suffix = "..." if right_omitted else ""
    budget = max_line_length - len(prefix) - len(suffix)

    if budget >= 1:
        core_start = _core_window_start(
            core_len=len(core),
            marker_start_idx=marker_start_idx,
            marker_end_idx=marker_end_idx,
            budget=budget,
        )
        return prefix, suffix, core[core_start : core_start + budget], core_start

    # Degrade markers to honor strict width when line budget is too small.
    if right_omitted and suffix:
        suffix = "."
    if left_omitted and prefix and max_line_length - len(prefix) - len(suffix) < 1:
        prefix = "."
    if right_omitted and suffix and max_line_length - len(prefix) - len(suffix) < 1:
        suffix = ""
    if left_omitted and prefix and max_line_length - len(prefix) - len(suffix) < 1:
        prefix = ""

    budget = max(1, max_line_length - len(prefix) - len(suffix))
    core_start = _core_window_start(
        core_len=len(core),
        marker_start_idx=marker_start_idx,
        marker_end_idx=marker_end_idx,
        budget=budget,
    )
    return prefix, suffix, core[core_start : core_start + budget], core_start


def _core_window_start(*, core_len: int, marker_start_idx: int, marker_end_idx: int, budget: int) -> int:
    if core_len <= budget:
        return 0
    marker_start_idx = min(max(0, marker_start_idx), core_len - 1)
    marker_end_idx = min(max(marker_start_idx, marker_end_idx), core_len)
    # Keep at least one span character visible by centering around the span start.
    desired = marker_start_idx - (budget // 2)
    min_start = max(0, marker_end_idx - budget)
    max_start = min(marker_start_idx, core_len - budget)
    if min_start > max_start:
        return min(max(0, desired), core_len - budget)
    return min(max(desired, min_start), max_start)
