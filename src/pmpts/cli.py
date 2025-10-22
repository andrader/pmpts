from __future__ import annotations

import argparse
import json
import shutil
import sys
import textwrap
import time
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from rich import print
except Exception:
    print = print
    pass

DEFAULT_ROOT = "/mnt/c/Users/Rubens/AppData/Roaming/Code/User/prompts"
CONFIG_PATH = Path.home() / ".promptcli.json"
SUFFIX = ".prompt.md"


def load_config() -> Dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_config(cfg: Dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception as e:
        print(f"Failed to write config: {e}", file=sys.stderr)


def get_root(config: Dict) -> Path:
    root = config.get("root") or DEFAULT_ROOT
    return Path(root)


def ensure_root(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)


def trash_dir_for(root: Path) -> Path:
    d = root / ".trash"
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_file(root: Path, src: Path, cfg: Dict, force: bool = False) -> Tuple[bool, str]:
    if not src.exists():
        return False, f"File not found: {src}"

    base = src.name
    if not base.endswith(SUFFIX):
        base = base + SUFFIX

    dest = root / base

    overwritten_trash = None
    if dest.exists():
        if not force:
            # prompt user
            ans = input(f"{dest} already exists. Overwrite? [y/N]: ")
            if ans.strip().lower() not in ("y", "yes"):
                return False, "aborted"
        # move existing to trash and record for undo
        td = trash_dir_for(root)
        tname = f"{int(time.time())}_{dest.name}"
        overwritten_trash = td / tname
        try:
            shutil.move(str(dest), str(overwritten_trash))
        except Exception as e:
            return False, f"Failed to move existing prompt to trash: {e}"

    try:
        shutil.move(str(src), str(dest))
    except Exception as e:
        # attempt to restore overwritten file if we moved it
        if overwritten_trash and overwritten_trash.exists():
            try:
                shutil.move(str(overwritten_trash), str(dest))
            except Exception:
                pass
        return False, f"Failed to move: {e}"

    # Save undo info in config
    cfg_last = {
        "action": "add",
        "src": str(src),
        "dest": str(dest),
    }
    if overwritten_trash:
        cfg_last["overwritten_trash"] = str(overwritten_trash)
    cfg["last_action"] = cfg_last
    save_config(cfg)

    name_no_suffix = base[: -len(SUFFIX)] if base.endswith(SUFFIX) else base
    return True, f"added prompt {base}\nuse /{name_no_suffix} to use it"


def remove_prompt(
    root: Path, name: str, cfg: Dict, yes: bool = False
) -> Tuple[bool, str]:
    candidate = name if name.endswith(SUFFIX) else name + SUFFIX
    p = root / candidate
    if not p.exists():
        return False, f"Not found: {candidate}"
    if not yes:
        ans = input(f"Remove {p}? [y/N]: ")
        if ans.strip().lower() not in ("y", "yes"):
            return False, "aborted"
    td = trash_dir_for(root)
    tname = f"{int(time.time())}_{p.name}"
    trashed = td / tname
    try:
        shutil.move(str(p), str(trashed))
    except Exception as e:
        return False, f"Failed to remove (move to trash): {e}"

    cfg["last_action"] = {"action": "remove", "dest": str(p), "trashed": str(trashed)}
    save_config(cfg)
    return True, f"removed {candidate} (moved to trash)"


def copy_prompt(root: Path, name: str, out: Path) -> Tuple[bool, str]:
    candidate = name if name.endswith(SUFFIX) else name + SUFFIX
    p = root / candidate
    if not p.exists():
        return False, f"Not found: {candidate}"
    try:
        shutil.copy2(str(p), str(out))
    except Exception as e:
        return False, f"Failed to copy: {e}"
    return True, f"copied {candidate} -> {out}"


def rename_prompt(
    root: Path, old: str, new: str, cfg: Dict, force: bool = False
) -> Tuple[bool, str]:
    old_candidate = old if old.endswith(SUFFIX) else old + SUFFIX
    new_candidate = new if new.endswith(SUFFIX) else new + SUFFIX
    p_old = root / old_candidate
    p_new = root / new_candidate
    if not p_old.exists():
        return False, f"Not found: {old_candidate}"
    if p_new.exists():
        if not force:
            ans = input(f"{p_new} already exists. Overwrite? [y/N]: ")
            if ans.strip().lower() not in ("y", "yes"):
                return False, "aborted"
        # move existing new to trash
        td = trash_dir_for(root)
        tname = f"{int(time.time())}_{p_new.name}"
        overwritten = td / tname
        try:
            shutil.move(str(p_new), str(overwritten))
        except Exception as e:
            return False, f"Failed to move existing target to trash: {e}"
    else:
        overwritten = None

    try:
        shutil.move(str(p_old), str(p_new))
    except Exception as e:
        # try restore overwritten if moved
        if overwritten and overwritten.exists():
            try:
                shutil.move(str(overwritten), str(p_new))
            except Exception:
                pass
        return False, f"Failed to rename: {e}"

    cfg["last_action"] = {"action": "rename", "old": str(p_old), "new": str(p_new)}
    if overwritten:
        cfg["last_action"]["overwritten_trash"] = str(overwritten)
    save_config(cfg)
    return True, f"renamed {old_candidate} -> {new_candidate}"


def perform_undo(cfg: Dict) -> Tuple[bool, str]:
    last = cfg.get("last_action")
    if not last:
        return False, "no action to undo"

    action = last.get("action")
    if action == "remove":
        trashed = Path(last.get("trashed"))
        dest = Path(last.get("dest"))
        if not trashed.exists():
            return False, "trashed file not found"
        try:
            # restore
            dest_parent = dest.parent
            dest_parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(trashed), str(dest))
        except Exception as e:
            return False, f"failed to restore: {e}"
        cfg.pop("last_action", None)
        save_config(cfg)
        return True, f"restored {dest.name}"

    if action == "add":
        dest = Path(last.get("dest"))
        src = last.get("src")
        overwritten = last.get("overwritten_trash")
        if not dest.exists():
            return False, "added file not found"
        try:
            # if there was an overwritten file, restore it first
            if overwritten:
                overwritten_p = Path(overwritten)
                if overwritten_p.exists():
                    shutil.move(str(overwritten_p), str(dest))
                    # move the new added file to trash
                    td = trash_dir_for(dest.parent)
                    tname = f"{int(time.time())}_{dest.name}.added"
                    shutil.move(str(dest), str(td / tname))
                    cfg.pop("last_action", None)
                    save_config(cfg)
                    return (
                        True,
                        "restored overwritten prompt and moved new added file to trash",
                    )
            # else try moving dest back to original source if possible
            if src:
                try:
                    dest_parent = Path(src).parent
                    dest_parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dest), str(src))
                    cfg.pop("last_action", None)
                    save_config(cfg)
                    return True, f"moved {dest.name} back to {src}"
                except Exception:
                    pass
            # fallback: move to current directory
            fallback = Path.cwd() / dest.name
            shutil.move(str(dest), str(fallback))
            cfg.pop("last_action", None)
            save_config(cfg)
            return True, f"moved {dest.name} to {fallback}"
        except Exception as e:
            return False, f"failed to undo add: {e}"

    return False, "unknown last action"


def parse_frontmatter(md_path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return data

    if not text.startswith("---"):
        return data

    lines = text.splitlines()
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line == "---":
            break
        if not line or line.startswith("#"):
            i += 1
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            data[k] = v
        i += 1

    return data


def list_prompts(root: Path, verbose: bool, show_files: bool = False) -> None:
    if not root.exists():
        print("(no prompts directory)")
        return

    file_list = sorted(
        [p for p in root.iterdir() if p.is_file() and p.name.endswith(SUFFIX)]
    )

    if not verbose and not show_files:
        for p in file_list:
            print(p.name[: -len(SUFFIX)])
        return

    if not verbose and show_files:
        for p in file_list:
            name = p.name[: -len(SUFFIX)]
            print(f"{name}\t{p.name}")
        return

    rows: List[Dict[str, str]] = []
    keys = set()
    for p in file_list:
        fm = parse_frontmatter(p)
        row = {"name": p.name[: -len(SUFFIX)], **fm}
        rows.append(row)
        keys.update(row.keys())

    cols = ["name"]
    if "description" in keys:
        cols.append("description")
    other = sorted(k for k in keys if k not in cols)
    cols.extend(other)

    MAX_WIDTH = 40

    def cell_lines(val: str) -> List[str]:
        if val is None:
            return [""]
        val = str(val)
        lines = []
        for part in val.splitlines() or [""]:
            wrapped = textwrap.wrap(part, width=MAX_WIDTH) or [""]
            lines.extend(wrapped)
        return lines

    col_lines: Dict[str, List[List[str]]] = {}
    for c in cols:
        col_lines[c] = [cell_lines(r.get(c, "")) for r in rows]

    widths = {}
    for c in cols:
        max_cell = max((len(l) for cell in col_lines[c] for l in cell), default=0)
        widths[c] = max(len(c), max_cell)

    row_line_counts = [
        max(len(col_lines[c][i]) for c in cols) for i in range(len(rows))
    ]

    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)

    for i, r in enumerate(rows):
        lines_count = row_line_counts[i]
        for ln in range(lines_count):
            parts = []
            for c in cols:
                cell = col_lines[c][i]
                part = cell[ln] if ln < len(cell) else ""
                parts.append(part.ljust(widths[c]))
            print(" | ".join(parts))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pmpts", description="Manage VS Code prompt files"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_setroot = sub.add_parser("setroot", help="Set prompts root directory")
    p_setroot.add_argument("path", help="Path to prompts root (absolute or relative)")

    p_add = sub.add_parser("add", help="Move a file into prompts root")
    p_add.add_argument("file", help="Path to file to add")
    p_add.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing prompt without prompting",
    )

    p_remove = sub.add_parser("remove", help="Remove a prompt by name")
    p_remove.add_argument("name", help="Prompt name (with or without suffix)")
    p_remove.add_argument(
        "-y", "--yes", action="store_true", help="Don't prompt for confirmation"
    )

    p_undo = sub.add_parser("undo", help="Undo the last add/remove where possible")

    p_copy = sub.add_parser("copy", help="Copy a prompt to output file")
    p_copy.add_argument("name", help="Prompt name (with or without suffix)")
    p_copy.add_argument("out", help="Output filepath")

    p_rename = sub.add_parser("rename", help="Rename a prompt")
    p_rename.add_argument("old", help="Existing prompt name (with or without suffix)")
    p_rename.add_argument("new", help="New prompt name (with or without suffix)")
    p_rename.add_argument(
        "-f", "--force", action="store_true", help="Overwrite target if exists"
    )

    p_list = sub.add_parser("list", help="List prompts")
    p_list.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show frontmatter fields in a table",
    )
    p_list.add_argument(
        "-f",
        "--files",
        action="store_true",
        help="Also show filenames (with and without suffix)",
    )

    args = parser.parse_args(argv)

    cfg = load_config()
    root = get_root(cfg)

    if args.cmd == "setroot":
        new_root = Path(args.path).expanduser()
        cfg["root"] = str(new_root)
        save_config(cfg)
        print(f"root set to: {new_root}")
        return 0

    ensure_root(root)

    if args.cmd == "add":
        ok, msg = add_file(
            root,
            Path(args.file).expanduser(),
            cfg,
            force=bool(getattr(args, "force", False)),
        )
        print(msg)
        return 0 if ok else 1

    if args.cmd == "remove":
        ok, msg = remove_prompt(
            root, args.name, cfg, yes=bool(getattr(args, "yes", False))
        )
        print(msg)
        return 0 if ok else 1

    if args.cmd == "undo":
        ok, msg = perform_undo(cfg)
        print(msg)
        return 0 if ok else 1

    if args.cmd == "copy":
        ok, msg = copy_prompt(root, args.name, Path(args.out).expanduser())
        print(msg)
        return 0 if ok else 1

    if args.cmd == "list":
        list_prompts(root, args.verbose, show_files=bool(getattr(args, "files", False)))
        return 0

    if args.cmd == "rename":
        ok, msg = rename_prompt(
            root, args.old, args.new, cfg, force=bool(getattr(args, "force", False))
        )
        print(msg)
        return 0 if ok else 1

    parser.print_help()
    return 2


def main_entry() -> None:
    raise SystemExit(main())
