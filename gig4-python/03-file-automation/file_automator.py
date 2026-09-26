#!/usr/bin/env python3
"""File automation: organise a messy folder, then merge its CSV/Excel files into one clean workbook.

Commands:
    organize   sort files into folders by type and rename them consistently (dry run by default)
    merge      combine every CSV/XLSX in a folder into one cleaned workbook with a Summary sheet
    run        organize (for real) + merge, driven by config.toml; this is what the scheduler calls
    undo       reverse an organize run using its log file

Examples:
    python file_automator.py organize                    # preview only, nothing is touched
    python file_automator.py organize --apply            # do it
    python file_automator.py merge --source "D:/exports" --output merged.xlsx
    python file_automator.py run --config config.toml    # scheduled job
    python file_automator.py undo output/logs/organize_20260926_101500.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import logging
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from core.config import ConfigError, load_toml
from core.excel import HEADER_FILL, HEADER_FONT, TITLE_FONT, autosize, save_workbook, write_table
from core.log import setup_logging

log = logging.getLogger("files")
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
SPREADSHEET_EXT = {".csv", ".xlsx", ".xlsm"}


# =============================================================== organize
@dataclass
class Move:
    source: Path
    target: Path
    action: str  # "organize" | "duplicate" | "skip"
    sha256: str
    reason: str = ""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(stem: str) -> str:
    s = stem.lower()
    s = re.sub(r"^copy of\s+", "", s)
    s = re.sub(r"\s*[-_]?\s*\(?\bcopy\b\)?", "", s)      # "file - copy", "file (copy)"
    s = re.sub(r"\s*\(\d+\)$", "", s)                     # "file (2)"
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "file"


def folder_for(ext: str, folders: dict[str, list[str]]) -> str:
    for folder, exts in folders.items():
        if ext.lower() in {e.lower() for e in exts}:
            return folder
    return "Other"


def plan_organize(inbox: Path, dest: Path, folders: dict[str, list[str]], pattern: str, date_source: str) -> list[Move]:
    if not inbox.is_dir():
        raise ConfigError(f"Inbox folder not found: {inbox}")
    existing: dict[str, Path] = {}
    if dest.exists():
        for p in dest.rglob("*"):
            if p.is_file():
                existing[sha256_of(p)] = p
    taken = {p.resolve() for p in dest.rglob("*")} if dest.exists() else set()
    moves: list[Move] = []
    seen: dict[str, Path] = {}
    # Originals first, so "Copy of X" / "X (2)" become the duplicates rather than X itself.
    copy_like = re.compile(r"(^copy of )|(\bcopy\b)|(\(\d+\)$)", re.IGNORECASE)
    files = sorted((p for p in inbox.iterdir() if p.is_file()),
                   key=lambda p: (bool(copy_like.search(p.stem)), p.name.lower()))
    for src in files:
        name = src.name
        if name.lower() in SKIP_NAMES or name.startswith("~$") or name.startswith("."):
            moves.append(Move(src, src, "skip", "", "system/temp file"))
            continue
        digest = sha256_of(src)
        if digest in existing:  # already organized by an earlier run: leave it alone
            moves.append(Move(src, src, "skip", digest, f"already organized as {existing[digest].name}"))
            continue
        if digest in seen:  # identical to another file in this batch
            original = seen[digest]
            target = dest / "Duplicates" / name
            moves.append(Move(src, _free_name(target, taken), "duplicate", digest, f"same content as {original.name}"))
            continue
        ext = src.suffix.lower()
        stamp = date.today() if date_source == "today" else datetime.fromtimestamp(src.stat().st_mtime).date()
        new_name = pattern.format(date=stamp.isoformat(), slug=slugify(src.stem), ext=ext, name=src.stem)
        target = _free_name(dest / folder_for(ext, folders) / new_name, taken)
        seen[digest] = target
        moves.append(Move(src, target, "organize", digest))
    return moves


def _free_name(target: Path, taken: set[Path]) -> Path:
    candidate, n = target, 2
    while candidate.resolve() in taken or candidate.exists():
        candidate = target.with_name(f"{target.stem}-{n}{target.suffix}")
        n += 1
    taken.add(candidate.resolve())
    return candidate


def apply_organize(moves: list[Move], mode: str, log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"organize_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with log_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time", "mode", "action", "source", "target", "sha256"])
        for m in moves:
            if m.action == "skip":
                continue
            m.target.parent.mkdir(parents=True, exist_ok=True)
            if mode == "move":
                shutil.move(str(m.source), str(m.target))
            else:
                shutil.copy2(m.source, m.target)
            writer.writerow([datetime.now().isoformat(timespec="seconds"), mode, m.action, m.source, m.target, m.sha256])
    return log_path


def undo_organize(log_path: Path) -> int:
    if not log_path.exists():
        raise ConfigError(f"Log file not found: {log_path}")
    rows = list(csv.DictReader(log_path.open(encoding="utf-8")))
    undone = 0
    for row in reversed(rows):
        src, target = Path(row["source"]), Path(row["target"])
        if not target.exists():
            log.warning("  missing, skipped: %s", target)
            continue
        if row["mode"] == "move":
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(src))
        elif sha256_of(target) == row["sha256"]:  # only remove copies we made and nobody edited
            target.unlink()
        else:
            log.warning("  changed since copy, kept: %s", target)
            continue
        undone += 1
    return undone


def rel(path: Path) -> str:
    """Short path for logs: relative to the current folder when possible."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def print_plan(moves: list[Move], inbox: Path, dest: Path) -> None:
    counts = Counter(m.action for m in moves)
    for m in moves:
        if m.action == "skip":
            log.info("  SKIP       %-34s (%s)", m.source.name, m.reason)
        else:
            label = "DUPLICATE" if m.action == "duplicate" else "ORGANIZE"
            log.info("  %-10s %-34s -> %s", label, m.source.name, m.target.relative_to(dest).as_posix())
    log.info("Plan: %d to organize, %d duplicates, %d skipped (from %s)",
             counts["organize"], counts["duplicate"], counts["skip"], rel(inbox))


# ================================================================== merge
@dataclass
class Column:
    name: str
    type: str = "text"      # text | int | number | date
    required: bool = False
    aliases: list[str] = field(default_factory=list)


@dataclass
class MergeResult:
    headers: list[str]
    rows: list[list[Any]] = field(default_factory=list)
    rejected: list[list[Any]] = field(default_factory=list)
    duplicates: list[list[Any]] = field(default_factory=list)
    per_file: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    skipped_files: list[tuple[str, str]] = field(default_factory=list)


def norm_header(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9# ]+", " ", str(value or "").lower())).strip()


def parse_number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty")
    negative = text.startswith("(") and text.endswith(")") or text.startswith("-")
    text = re.sub(r"[^\d.,]", "", text)
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text:
        text = text.replace(",", ".") if re.search(r",\d{1,2}$", text) else text.replace(",", "")
    if not text or text == ".":
        raise ValueError(f"not a number: {value!r}")
    number = float(text)
    return -number if negative else number


def parse_date(value: Any, formats: list[str]) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {text!r}")


def read_csv_rows(path: Path) -> list[list[Any]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def read_xlsx_rows(path: Path) -> Iterator[tuple[str, list[list[Any]]]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            yield ws.title, [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def find_header(rows: list[list[Any]], lookup: dict[str, str], search_rows: int) -> tuple[int, dict[int, str]] | None:
    best: tuple[int, dict[int, str]] | None = None
    for i, row in enumerate(rows[:search_rows]):
        mapping = {j: lookup[norm_header(v)] for j, v in enumerate(row) if norm_header(v) in lookup}
        if len(set(mapping.values())) >= 2 and (best is None or len(mapping) > len(best[1])):
            best = (i, mapping)
    return best


def merge_folder(source: Path, columns: list[Column], cfg: dict[str, Any]) -> MergeResult:
    if not source.is_dir():
        raise ConfigError(f"Merge source folder not found: {source}")
    lookup: dict[str, str] = {}
    for col in columns:
        for alias in [col.name, *col.aliases]:
            lookup[norm_header(alias)] = col.name
    formats = cfg.get("date_formats", ["%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%Y", "%b %d, %Y"])
    title_case = set(cfg.get("title_case", []))
    dedupe_on = cfg.get("dedupe_on", [])
    search_rows = int(cfg.get("header_search_rows", 10))
    required = [c.name for c in columns if c.required]

    result = MergeResult(headers=[c.name for c in columns] + ["source_file", "source_row"])
    seen_keys: dict[tuple, str] = {}
    files = sorted(p for p in source.iterdir() if p.suffix.lower() in SPREADSHEET_EXT and not p.name.startswith("~$"))
    if not files:
        raise ConfigError(f"No .csv/.xlsx files in {source}")

    for path in files:
        try:
            tables = [("", read_csv_rows(path))] if path.suffix.lower() == ".csv" else list(read_xlsx_rows(path))
        except Exception as exc:  # noqa: BLE001 - a corrupt file must not stop the batch
            result.skipped_files.append((path.name, f"unreadable: {exc}"))
            log.warning("  %s: unreadable (%s)", path.name, exc)
            continue
        for sheet, rows in tables:
            label = f"{path.name}" + (f" [{sheet}]" if sheet and len(tables) > 1 else "")
            header = find_header(rows, lookup, search_rows)
            if header is None:
                result.skipped_files.append((label, "no recognisable header row"))
                log.warning("  %s: no recognisable header row, skipped", label)
                continue
            header_idx, mapping = header
            missing = [r for r in required if r not in mapping.values()]
            if missing:
                result.skipped_files.append((label, f"missing required columns: {', '.join(missing)}"))
                log.warning("  %s: missing required columns %s, skipped", label, missing)
                continue
            stats = result.per_file[label]
            for line_no, raw in enumerate(rows[header_idx + 1:], start=header_idx + 2):
                if not any(str(v).strip() for v in raw if v is not None):
                    continue
                stats["read"] += 1
                record: dict[str, Any] = {c.name: None for c in columns}
                for j, name in mapping.items():
                    if j < len(raw):
                        record[name] = raw[j]
                errors = []
                for col in columns:
                    value = record[col.name]
                    blank = value is None or str(value).strip() == ""
                    if blank:
                        record[col.name] = None
                        if col.required:
                            errors.append(f"{col.name} is empty")
                        continue
                    try:
                        if col.type == "date":
                            record[col.name] = parse_date(value, formats)
                        elif col.type == "number":
                            record[col.name] = round(parse_number(value), 2)
                        elif col.type == "int":
                            record[col.name] = int(round(parse_number(value)))
                        else:
                            text = re.sub(r"\s+", " ", str(value)).strip()
                            record[col.name] = text.title() if col.name in title_case else text
                    except ValueError as exc:
                        errors.append(f"{col.name}: {exc}")
                out = [record[c.name] for c in columns] + [path.name, line_no]
                if errors:
                    result.rejected.append(out + ["; ".join(errors)])
                    stats["rejected"] += 1
                    continue
                key = tuple(str(record[k]).lower() for k in dedupe_on)
                if dedupe_on and key in seen_keys:
                    result.duplicates.append(out + [f"duplicate of row in {seen_keys[key]}"])
                    stats["duplicates"] += 1
                    continue
                if dedupe_on:
                    seen_keys[key] = path.name
                result.rows.append(out)
                stats["kept"] += 1
            log.info("  %-44s read %3d  kept %3d  dupes %2d  rejected %2d",
                     label[:44], stats["read"], stats["kept"], stats["duplicates"], stats["rejected"])
    return result


def write_summary_sheet(wb: Workbook, result: MergeResult, columns: list[Column], summary_cfg: dict[str, Any], source: Path) -> None:
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "Merged data summary"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Source: {rel(source)}   |   Generated {datetime.now():%Y-%m-%d %H:%M}"
    ws["A2"].font = Font(italic=True, color="6B7280")

    totals = Counter()
    for c in result.per_file.values():
        totals.update(c)
    sum_col = summary_cfg.get("sum")
    names = result.headers
    sum_idx = names.index(sum_col) if sum_col in names else None
    grand = round(sum(r[sum_idx] or 0 for r in result.rows), 2) if sum_idx is not None else None

    headline = [("Files merged", len(result.per_file)), ("Rows read", totals["read"]), ("Rows kept", totals["kept"]),
                ("Duplicates removed", totals["duplicates"]), ("Rows rejected (see sheet)", totals["rejected"]),
                ("Files/sheets skipped", len(result.skipped_files))]
    if grand is not None:
        headline.append((f"Total {sum_col}", grand))
    row = 4
    for label, value in headline:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        cell = ws.cell(row=row, column=2, value=value)
        if isinstance(value, float):
            cell.number_format = "#,##0.00"
        row += 1

    def table(start_row: int, title: str, headers: list[str], rows: list[list[Any]], money_cols: set[int]) -> int:
        ws.cell(row=start_row, column=1, value=title).font = Font(bold=True, size=12)
        for j, h in enumerate(headers, 1):
            c = ws.cell(row=start_row + 1, column=j, value=h)
            c.fill, c.font = HEADER_FILL, HEADER_FONT
        for i, r in enumerate(rows, start_row + 2):
            for j, v in enumerate(r, 1):
                c = ws.cell(row=i, column=j, value=v)
                if j in money_cols:
                    c.number_format = "#,##0.00"
        return start_row + len(rows) + 3

    row = table(row + 1, "Per file", ["File", "Rows read", "Kept", "Duplicates", "Rejected"],
                [[f, c["read"], c["kept"], c["duplicates"], c["rejected"]] for f, c in result.per_file.items()], set())
    if result.skipped_files:
        row = table(row, "Skipped", ["File", "Reason"], [list(x) for x in result.skipped_files], set())
    if sum_idx is not None:
        for group in summary_cfg.get("group_by", []):
            if group not in names:
                continue
            g_idx = names.index(group)
            agg: dict[str, list[float]] = defaultdict(list)
            for r in result.rows:
                agg[str(r[g_idx] or "(blank)")].append(r[sum_idx] or 0)
            rows = sorted(([k, len(v), round(sum(v), 2), round(sum(v) / len(v), 2)] for k, v in agg.items()),
                          key=lambda x: -x[2])
            rows.append(["Total", sum(len(v) for v in agg.values()), grand, None])
            row = table(row, f"{sum_col} by {group}", [group, "Orders", f"Total {sum_col}", f"Avg {sum_col}"], rows, {3, 4})
    autosize(ws)
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width, 28)


def write_merged(result: MergeResult, columns: list[Column], cfg: dict[str, Any], source: Path, output: Path) -> None:
    wb = Workbook()
    write_summary_sheet(wb, result, columns, cfg.get("summary", {}), source)
    formats = {c.name: ("yyyy-mm-dd" if c.type == "date" else "#,##0.00" if c.type == "number" else "0")
               for c in columns if c.type in ("date", "number", "int")}
    write_table(wb, "Data", result.headers, result.rows, number_formats=formats)
    write_table(wb, "Rejected", result.headers + ["reason"], result.rejected, number_formats=formats, style="TableStyleMedium3")
    write_table(wb, "Duplicates removed", result.headers + ["reason"], result.duplicates, number_formats=formats, style="TableStyleLight1")
    save_workbook(wb, output)
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(result.headers)
        for r in result.rows:
            writer.writerow([v.isoformat() if isinstance(v, date) else v for v in r])


def load_columns(cfg: dict[str, Any]) -> list[Column]:
    spec = cfg.get("columns")
    if not spec:
        raise ConfigError("config [merge.columns] is empty: define the output columns")
    cols = []
    for name, opts in spec.items():
        if opts.get("type", "text") not in ("text", "int", "number", "date"):
            raise ConfigError(f"column {name}: type must be text, int, number or date")
        cols.append(Column(name, opts.get("type", "text"), bool(opts.get("required", False)), list(opts.get("aliases", []))))
    return cols


# ==================================================================== CLI
def resolve_path(value: str | None, base: Path) -> Path | None:
    if value is None:
        return None
    p = Path(value)
    return p if p.is_absolute() else (base / p)


class RunLock:
    """Stops two scheduled runs from overlapping."""

    def __init__(self, path: Path, stale_after: int = 6 * 3600) -> None:
        self.path, self.stale_after = path, stale_after

    def __enter__(self) -> "RunLock":
        if self.path.exists() and time.time() - self.path.stat().st_mtime < self.stale_after:
            raise ConfigError(f"Another run is in progress (lock file {self.path}). Delete it if that's not true.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)


def cmd_organize(cfg: dict[str, Any], base: Path, args: argparse.Namespace, apply: bool) -> int:
    o = cfg.get("organize", {})
    inbox = resolve_path(args.inbox or o.get("inbox"), base)
    dest = resolve_path(args.dest or o.get("dest"), base)
    if inbox is None or dest is None:
        raise ConfigError("Set organize.inbox and organize.dest in config.toml (or pass --inbox/--dest)")
    mode = args.mode or o.get("mode", "copy")
    if mode not in ("copy", "move"):
        raise ConfigError("mode must be copy or move")
    folders = o.get("folders", {"Spreadsheets": [".csv", ".xlsx"], "PDFs": [".pdf"]})
    moves = plan_organize(inbox, dest, folders, o.get("rename", "{date}_{slug}{ext}"), o.get("date_source", "modified"))
    log.info("Organize %s -> %s (%s mode)%s", rel(inbox), rel(dest), mode, "" if apply else "  [DRY RUN]")
    print_plan(moves, inbox, dest)
    if not apply:
        log.info("DRY RUN: nothing changed. Add --apply to do it.")
        return 0
    if not any(m.action != "skip" for m in moves):
        log.info("Nothing new to organize.")
        return 0
    log_path = apply_organize(moves, mode, dest / "_logs")
    log.info("Done. Undo log: %s", rel(log_path))
    return 0


def cmd_merge(cfg: dict[str, Any], base: Path, args: argparse.Namespace) -> int:
    m = cfg.get("merge", {})
    source = resolve_path(args.source or m.get("source"), base)
    output = resolve_path(args.output or m.get("output", "merged.xlsx"), base)
    if source is None:
        raise ConfigError("Set merge.source in config.toml (or pass --source)")
    columns = load_columns(m)
    log.info("Merge %s -> %s", rel(source), rel(output))
    result = merge_folder(source, columns, m)
    write_merged(result, columns, m, source, output)
    log.info("Merged %d rows from %d file(s): %d duplicates removed, %d rejected -> %s (+ .csv)",
             len(result.rows), len(result.per_file), len(result.duplicates), len(result.rejected), rel(output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Organise folders and merge CSV/Excel files into one clean workbook.")
    p.add_argument("--config", default="config.toml", help="TOML config (default config.toml)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--log-file", help="write the log here too (default: logs/file_automator.log next to the config)")
    # Accept the global options after the command too ("run --config x.toml").
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--log-file", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="command", required=True)
    o = sub.add_parser("organize", parents=[common], help="sort + rename files (dry run unless --apply)")
    o.add_argument("--inbox")
    o.add_argument("--dest")
    o.add_argument("--mode", choices=["copy", "move"])
    o.add_argument("--apply", action="store_true", help="actually copy/move files")
    m = sub.add_parser("merge", parents=[common], help="merge CSV/XLSX files into one workbook")
    m.add_argument("--source")
    m.add_argument("--output")
    r = sub.add_parser("run", parents=[common], help="organize --apply + merge, for schedulers")
    r.add_argument("--skip-organize", action="store_true")
    u = sub.add_parser("undo", parents=[common], help="reverse an organize run")
    u.add_argument("log", help="path to an organize_*.csv log")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for attr in ("inbox", "dest", "mode", "source", "output"):
        if not hasattr(args, attr):
            setattr(args, attr, None)
    config_path = Path(args.config).resolve()
    base = config_path.parent
    try:
        cfg = load_toml(config_path)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    setup_logging(args.verbose, args.log_file or base / "logs" / "file_automator.log")
    started = time.monotonic()
    try:
        if args.command == "organize":
            code = cmd_organize(cfg, base, args, apply=args.apply)
        elif args.command == "merge":
            code = cmd_merge(cfg, base, args)
        elif args.command == "undo":
            log.info("Undid %d file operation(s)", undo_organize(Path(args.log)))
            code = 0
        else:
            with RunLock(base / "logs" / "run.lock"):
                code = 0
                if not args.skip_organize and cfg.get("run", {}).get("organize", True):
                    code = cmd_organize(cfg, base, args, apply=True)
                code = code or cmd_merge(cfg, base, args)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    except PermissionError as exc:
        log.error("%s", exc)
        return 1
    log.info("Finished in %.1fs", time.monotonic() - started)
    return code


if __name__ == "__main__":
    sys.exit(main())
