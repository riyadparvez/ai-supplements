#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""
Bidirectional sync for ~/.claude configuration files to/from git repo.

Syncs:
- keybindings.json
- settings.json, settings.local.json
- CLAUDE.md, AGENTS.md
- agents/ directory (custom agents)
- rules/ directory (custom rules)
- hooks.json, launch.json

Usage:
  python claude-sync.py [status|push|pull|auto] [--backup] [--dry-run] [--force]

Commands:
  status    - Show what would be synced
  push      - Sync ~/.claude → repo (git tracked files)
  pull      - Sync repo → ~/.claude
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
    "dirs": ["agents", "rules"],
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
    print(f"  Backed up: {backup.name}")
    return backup

def get_mtime(path: Path) -> float:
    """Get modification time, return 0 if doesn't exist."""
    return path.stat().st_mtime if path.exists() else 0

def is_newer(src: Path, dst: Path) -> bool:
    """Check if src is newer than dst."""
    return get_mtime(src) > get_mtime(dst)

def sync_file(src: Path, dst: Path, backup: bool = False, direction: str = "->") -> bool:
    """Sync single file. Return True if changed."""
    if not src.exists():
        if dst.exists():
            print(f"  Remove: {dst.relative_to(dst.parent.parent)}")
            if not DRY_RUN:
                if backup:
                    backup_file(dst)
                dst.unlink()
            return True
        return False

    if not dst.exists() or is_newer(src, dst):
        print(f"  Sync: {src.name} {direction} {dst.relative_to(dst.parent.parent)}")
        if not DRY_RUN:
            if dst.exists() and backup:
                backup_file(dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return True

    return False

def sync_dir(src: Path, dst: Path, backup: bool = False, direction: str = "->") -> bool:
    """Sync directory recursively. Return True if any changes."""
    changed = False
    if not src.exists():
        return False

    if not DRY_RUN:
        dst.mkdir(parents=True, exist_ok=True)

    # Sync files in src → dst
    for src_file in src.rglob("*"):
        if src_file.is_file():
            rel_path = src_file.relative_to(src)
            dst_file = dst / rel_path
            if sync_file(src_file, dst_file, backup, direction):
                changed = True

    # Remove files in dst that don't exist in src
    for dst_file in list(dst.rglob("*")):
        if dst_file.is_file():
            rel_path = dst_file.relative_to(dst)
            src_file = src / rel_path
            if not src_file.exists():
                print(f"  Remove: {dst_file.relative_to(SYNC_DIR.parent)}")
                if not DRY_RUN:
                    if backup:
                        backup_file(dst_file)
                    dst_file.unlink()
                changed = True

    return changed

def status() -> None:
    """Show sync status."""
    ensure_sync_dir()
    print("\n📋 Claude Configuration Sync Status\n")
    print(f"  ~/.claude:  {CLAUDE_HOME}")
    print(f"  Git repo:   {SYNC_DIR}\n")

    print("Files:")
    for fname in SYNC_CONFIG["files"]:
        claude_file = CLAUDE_HOME / fname
        repo_file = SYNC_DIR / fname
        status_str = "✓" if claude_file.exists() else "✗"

        mtime_diff = get_mtime(claude_file) - get_mtime(repo_file)
        if mtime_diff > 0:
            direction = "→ (newer in ~/.claude)"
        elif mtime_diff < 0:
            direction = "← (newer in repo)"
        else:
            direction = "= (synced)"

        print(f"  {status_str} {fname:25} {direction}")

    print("\nDirectories:")
    for dname in SYNC_CONFIG["dirs"]:
        claude_dir = CLAUDE_HOME / dname
        status_str = "✓" if claude_dir.exists() else "✗"
        print(f"  {status_str} {dname}/")

def push(backup: bool = False, force: bool = False) -> None:
    """Sync ~/.claude → repo."""
    ensure_sync_dir()
    dry = "[DRY-RUN] " if DRY_RUN else ""
    print(f"\n📤 {dry}Pushing ~/.claude → repo\n")

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
        print(f"\n✅ {dry}Push complete")
    else:
        print("\n✓ Already synced")

def pull(backup: bool = False, force: bool = False) -> None:
    """Sync repo → ~/.claude."""
    ensure_sync_dir()
    dry = "[DRY-RUN] " if DRY_RUN else ""
    print(f"\n📥 {dry}Pulling repo → ~/.claude\n")

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
        msg = "Restart Claude Code for changes to take effect." if not DRY_RUN else ""
        print(f"\n✅ {dry}Pull complete. {msg}")
    else:
        print("\n✓ Already synced")

def auto_sync(backup: bool = False, force: bool = False) -> None:
    """Auto-detect direction based on modification times."""
    ensure_sync_dir()
    dry = "[DRY-RUN] " if DRY_RUN else ""
    print(f"\n🔄 {dry}Auto-syncing (latest modtime wins)\n")

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
        print("→ Detected changes in ~/.claude, pushing...\n")
        push(backup)
    elif repo_newer and not claude_newer:
        print("← Detected changes in repo, pulling...\n")
        pull(backup)
    elif claude_newer and repo_newer:
        if force:
            print("⚠️  Conflict: both sides have newer files")
            print("   --force used, pushing ~/.claude...\n")
            push(backup)
        else:
            print("⚠️  Conflict: both sides have newer files")
            print("   Run with --force to push, or manually resolve")
            sys.exit(1)
    else:
        print("✓ Both sides already synced")

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
            print(f"\n  [DRY-RUN] Would commit: {message}")
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
        print(f"\n  Committed: {message}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ⚠️  Git commit failed: {e}")
        return False
    except Exception as e:
        print(f"  ⚠️  Git error: {e}")
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
        print("\n\nCancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
