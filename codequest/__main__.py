"""CodeQuest CLI entry point."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="codequest",
        description="CodeQuest - Your Project Command Center",
    )
    parser.add_argument(
        "--web", action="store_true",
        help="Launch web dashboard only (localhost:8080)",
    )
    parser.add_argument(
        "--scan", action="store_true",
        help="Re-scan and rebuild project index",
    )
    parser.add_argument(
        "--config", action="store_true",
        help="Open config file in default editor",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port for web dashboard (default: 8080)",
    )

    args = parser.parse_args()

    if args.scan:
        from codequest.scanner import scan_all, save_index
        print("Scanning for projects...")
        projects = scan_all()
        save_index(projects)
        print(f"Found {len(projects)} projects. Index saved.")
        for p in projects:
            badges = []
            if p.is_git_repo:
                badges.append("GIT")
            if p.has_github:
                badges.append("GITHUB")
            if p.is_claude_made:
                badges.append("CLAUDE")
            print(f"  {p.project_type:8s} {p.name:30s} {' '.join(f'[{b}]' for b in badges)}")
        return

    if args.config:
        import os
        import subprocess
        from codequest.config import USER_CONFIG_FILE, PROJECT_CONFIG_FILE
        config_file = USER_CONFIG_FILE if USER_CONFIG_FILE.exists() else PROJECT_CONFIG_FILE
        editor = os.environ.get("EDITOR", "nano")
        subprocess.run([editor, str(config_file)])
        return

    if args.web:
        from codequest.web.server import run_server
        port = args.port or 8080
        print(f"Starting CodeQuest web dashboard on http://localhost:{port}")
        run_server(port=port)
        return

    # Default: launch TUI
    from codequest.app import run_tui
    run_tui()


if __name__ == "__main__":
    main()
