#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = ["rich>=13.0.0"]
# ///
"""
Bidirectional sync for ~/.claude configuration files to/from git repo.

SAFETY: Only overwrites files, never deletes anything. All files are preserved.

Syncs:
- keybindings.json
- settings.json, settings.local.json
- CLAUDE.md, AGENTS.md
- hooks.json, launch.json
- agents/ directory (custom agents)
- rules/ directory (custom rules)
- skills/ directory (custom skills)
- commands/ directory (custom commands)

Usage:
  python claude-sync.py [status|push|pull|auto] [--backup] [--dry-run] [--force]

Commands:
  status    - Show what would be synced
  push      - Sync ~/.claude → repo (overwrite only)
  pull      - Sync repo → ~/.claude (overwrite only)
  auto      - Auto-detect direction (latest modtime wins)

Options:
  --dry-run - Show what would change without making changes
  --backup  - Create timestamped backups before overwriting
  --force   - Force push in auto mode (ignore conflicts)
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

# Configuration
CLAUDE_HOME = Path.home() / ".claude"
SYNC_CONFIG = {
    "files": [
        "keybindings.json",
        "settings.json",
        "settings.local.json",
        "CLAUDE.md",
        "AGENTS.md",
        "hooks.json",
        "launch.json",
    ],
    "dirs": ["agents", "rules", "skills", "commands"],
}

# Auto-detect repo root (where this script lives)
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR
SYNC_DIR = REPO_ROOT / "claude"

# Global flags
DRY_RUN = False

def ensure_sync_dir():
    """Create sync directory if it doesn't exist."""
    SYNC_DIR.mkdir(exist_ok=True)
    for d in SYNC_CONFIG["dirs"]:
        (SYNC_DIR / d).mkdir(exist_ok=True)

def backup_file(path: Path) -> Optional[Path]:
    """Create a timestamped backup of a file."""
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_stem(f"{path.stem}.backup_{timestamp}")
    shutil.copy2(path, backup)
    console.print(f"  [dim]Backed up:[/] {backup.name}")
    return backup

def get_mtime(path: Path) -> float:
    """Get modification time, return 0 if doesn't exist."""
    return path.stat().st_mtime if path.exists() else 0

def is_newer(src: Path, dst: Path) -> bool:
    """Check if src is newer than dst."""
    return get_mtime(src) > get_mtime(dst)

def sync_file(src: Path, dst: Path, backup: bool = False, direction: str = "->") -> bool:
    """Sync single file (copy/overwrite only, no deletions). Return True if changed."""
    if not src.exists():
        # Source doesn't exist - skip (never delete destination)
        return False

    if not dst.exists() or is_newer(src, dst):
        dir_color = "yellow" if direction == "->" else "cyan"
        console.print(f"  [green]Sync:[/] {src.name} [{dir_color}]{direction}[/] {dst.relative_to(dst.parent.parent)}")
        if not DRY_RUN:
            if dst.exists() and backup:
                backup_file(dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return True

    return False

def sync_dir(src: Path, dst: Path, backup: bool = False, direction: str = "->") -> bool:
    """Sync directory recursively (copy/overwrite only, no deletions). Return True if any changes."""
    changed = False
    if not src.exists():
        return False

    if not DRY_RUN:
        dst.mkdir(parents=True, exist_ok=True)

    # Sync files in src → dst (copy/overwrite only, never delete)
    for src_file in src.rglob("*"):
        if src_file.is_file():
            rel_path = src_file.relative_to(src)
            dst_file = dst / rel_path
            if sync_file(src_file, dst_file, backup, direction):
                changed = True

    return changed

def status() -> None:
    """Show sync status."""
    ensure_sync_dir()
    console.print("\n📋 [bold cyan]Claude Configuration Sync Status[/]\n")
    console.print(f"  [dim]~/.claude:[/]  {CLAUDE_HOME}")
    console.print(f"  [dim]Git repo:[/]   {SYNC_DIR}\n")

    # Files table
    table = Table(title="Files", show_header=True, header_style="bold magenta")
    table.add_column("File", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Direction", style="yellow")

    for fname in SYNC_CONFIG["files"]:
        claude_file = CLAUDE_HOME / fname
        repo_file = SYNC_DIR / fname
        status_str = "✓ exists" if claude_file.exists() else "✗ missing"
        status_color = "green" if claude_file.exists() else "red"

        mtime_diff = get_mtime(claude_file) - get_mtime(repo_file)
        if mtime_diff > 0:
            direction = "[yellow]→[/] (newer in ~/.claude)"
        elif mtime_diff < 0:
            direction = "[cyan]←[/] (newer in repo)"
        else:
            direction = "[green]=[/] (synced)"

        table.add_row(fname, f"[{status_color}]{status_str}[/]", direction)

    console.print(table)

    # Directories
    console.print("\n[bold magenta]Directories[/]")
    for dname in SYNC_CONFIG["dirs"]:
        claude_dir = CLAUDE_HOME / dname
        status_str = "[green]✓[/]" if claude_dir.exists() else "[red]✗[/]"
        console.print(f"  {status_str} [cyan]{dname}/[/]")

def push(backup: bool = False, force: bool = False) -> None:
    """Sync ~/.claude → repo."""
    ensure_sync_dir()
    dry_tag = "[bold red][DRY-RUN][/][/] " if DRY_RUN else ""
    console.print(f"\n{dry_tag}📤 [bold yellow]Pushing ~/.claude → repo[/]\n")

    changed = False

    for fname in SYNC_CONFIG["files"]:
        src = CLAUDE_HOME / fname
        dst = SYNC_DIR / fname
        if sync_file(src, dst, backup, "->"):
            changed = True

    for dname in SYNC_CONFIG["dirs"]:
        src = CLAUDE_HOME / dname
        dst = SYNC_DIR / dname
        if sync_dir(src, dst, backup, "->"):
            changed = True

    if changed:
        git_commit("Push: sync ~/.claude → repo")
        console.print(f"\n[bold green]✅ Push complete[/]")
    else:
        console.print("\n[bold cyan]✓ Already synced[/]")

def pull(backup: bool = False, force: bool = False) -> None:
    """Sync repo → ~/.claude."""
    ensure_sync_dir()
    dry_tag = "[bold red][DRY-RUN][/][/] " if DRY_RUN else ""
    console.print(f"\n{dry_tag}📥 [bold cyan]Pulling repo → ~/.claude[/]\n")

    changed = False

    for fname in SYNC_CONFIG["files"]:
        src = SYNC_DIR / fname
        dst = CLAUDE_HOME / fname
        if sync_file(src, dst, backup, "<-"):
            changed = True

    for dname in SYNC_CONFIG["dirs"]:
        src = SYNC_DIR / dname
        dst = CLAUDE_HOME / dname
        if sync_dir(src, dst, backup, "<-"):
            changed = True

    if changed:
        console.print(f"\n[bold green]✅ Pull complete[/]")
        if not DRY_RUN:
            console.print("[dim]Restart Claude Code for changes to take effect.[/]")
    else:
        console.print("\n[bold cyan]✓ Already synced[/]")

def auto_sync(backup: bool = False, force: bool = False) -> None:
    """Auto-detect direction based on modification times."""
    ensure_sync_dir()
    dry_tag = "[bold red][DRY-RUN][/][/] " if DRY_RUN else ""
    console.print(f"\n{dry_tag}🔄 [bold magenta]Auto-syncing (latest modtime wins)[/]\n")

    # Check which direction has newer files
    claude_newer = False
    repo_newer = False

    for fname in SYNC_CONFIG["files"]:
        claude_file = CLAUDE_HOME / fname
        repo_file = SYNC_DIR / fname
        if get_mtime(claude_file) > get_mtime(repo_file):
            claude_newer = True
        elif get_mtime(repo_file) > get_mtime(claude_file):
            repo_newer = True

    # Also check directories for mtime changes
    for dname in SYNC_CONFIG["dirs"]:
        claude_dir = CLAUDE_HOME / dname
        repo_dir = SYNC_DIR / dname
        if claude_dir.exists():
            for claude_file in claude_dir.rglob("*"):
                if claude_file.is_file():
                    rel_path = claude_file.relative_to(claude_dir)
                    repo_file = repo_dir / rel_path
                    if get_mtime(claude_file) > get_mtime(repo_file):
                        claude_newer = True
                        break
        if repo_dir.exists():
            for repo_file in repo_dir.rglob("*"):
                if repo_file.is_file():
                    rel_path = repo_file.relative_to(repo_dir)
                    claude_file = claude_dir / rel_path
                    if get_mtime(repo_file) > get_mtime(claude_file):
                        repo_newer = True
                        break

    if claude_newer and not repo_newer:
        console.print("[yellow]→[/] Detected changes in ~/.claude, pushing...\n")
        push(backup)
    elif repo_newer and not claude_newer:
        console.print("[cyan]←[/] Detected changes in repo, pulling...\n")
        pull(backup)
    elif claude_newer and repo_newer:
        if force:
            console.print("[bold yellow]⚠️  Conflict:[/] both sides have newer files")
            console.print("[bold yellow]--force[/] used, pushing ~/.claude...\n")
            push(backup)
        else:
            console.print("\n[bold red]⚠️  Conflict:[/] both sides have newer files")
            console.print("[yellow]Run with[/] [bold cyan]--force[/] [yellow]to push, or manually resolve[/]")
            sys.exit(1)
    else:
        console.print("[bold green]✓[/] Both sides already synced")

def git_commit(message: str) -> bool:
    """Commit changes to git."""
    try:
        # Check if there are changes
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if not result.stdout.strip():
            return False

        if DRY_RUN:
            console.print(f"\n  [bold red][DRY-RUN][/] Would commit: {message}")
            return True

        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "add", str(SYNC_DIR)],
            check=True,
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "commit", "-m", message],
            check=True,
            capture_output=True,
            timeout=5,
        )
        console.print(f"\n  [dim]Committed:[/] {message}")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"  [bold red]✗ Git commit failed:[/] {e}")
        return False
    except Exception as e:
        console.print(f"  [bold red]✗ Git error:[/] {e}")
        return False

def main():
    global DRY_RUN

    parser = argparse.ArgumentParser(
        description="Bidirectional sync for ~/.claude configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["status", "push", "pull", "auto"],
        help="Sync command",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without making changes",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create timestamped backups before overwriting",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force push in auto mode (ignore conflicts)",
    )

    args = parser.parse_args()
    DRY_RUN = args.dry_run

    try:
        if args.command == "status":
            status()
        elif args.command == "push":
            push(backup=args.backup)
        elif args.command == "pull":
            pull(backup=args.backup)
        elif args.command == "auto":
            auto_sync(backup=args.backup, force=args.force)
    except KeyboardInterrupt:
        console.print("\n\n[bold red]Cancelled[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]❌ Error:[/] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
