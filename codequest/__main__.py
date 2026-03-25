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
    parser.add_argument(
        "--deps", action="store_true",
        help="Show dependency report from latest scan",
    )
    parser.add_argument(
        "--severity", type=str, default=None,
        choices=["major", "minor", "patch"],
        help="Filter by severity (use with --deps, --plan, --fix)",
    )
    # Dependency engine flags
    parser.add_argument(
        "--plan", metavar="PROJECT",
        help="Show update plan for PROJECT (what would be updated)",
    )
    parser.add_argument(
        "--fix", metavar="PROJECT",
        help="Fix outdated dependencies for PROJECT",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be updated without executing (use with --fix)",
    )
    parser.add_argument(
        "--lock", metavar="PROJECT",
        help="Generate lock file for PROJECT (or 'all')",
    )
    parser.add_argument(
        "--health", metavar="PROJECT",
        help="Show health score for PROJECT (or 'all')",
    )
    parser.add_argument(
        "--system", action="store_true",
        help="Show Linux system update report",
    )
    parser.add_argument(
        "--github", action="store_true",
        help="Show GitHub repos report (cross-referenced with local projects)",
    )

    args = parser.parse_args()

    # --- Dependency report ---
    if args.deps:
        from codequest.deps import load_cache, generate_report, save_report
        cache = load_cache()
        if not cache:
            print("No dependency data cached. Run a scan first:")
            print("  codequest --web  (then click Scan on /dependencies)")
            print("  Or use the API: curl -X POST localhost:8080/api/deps/scan")
            return
        report = generate_report(cache, severity_filter=args.severity)
        print(report)
        save_report(cache)
        return

    # --- Update plan ---
    if args.plan:
        from codequest.deps import load_cache, plan_updates
        cache = load_cache()
        if not cache:
            print("No dependency data cached. Run a scan first.")
            return
        if args.plan not in cache:
            print(f"Project '{args.plan}' not found in cache.")
            print(f"Available: {', '.join(sorted(cache.keys()))}")
            return
        plan = plan_updates(args.plan, cache, severity_filter=args.severity)
        updates = plan.get("updates", [])
        if not updates:
            print(f"No updates planned for {args.plan}" +
                  (f" at {args.severity} severity" if args.severity else ""))
            return
        s = plan["summary"]
        print(f"Update plan for {args.plan} ({plan['project_type']})")
        print(f"  {s['total']} packages: {s['auto_safe']} safe, "
              f"{s['needs_review']} review, {s['breaking_risk']} breaking")
        print()
        print(f"{'Package':<30s} {'Current':<15s} {'Latest':<15s} {'Risk':<15s}")
        print("-" * 75)
        for u in updates:
            risk_display = u["risk"].upper() if u["risk"] == "breaking-risk" else u["risk"]
            print(f"{u['name']:<30s} {u['current']:<15s} {u['latest']:<15s} {risk_display:<15s}")
        print()
        print("Commands that would run:")
        for u in updates:
            print(f"  {u['command']}")
        return

    # --- Fix dependencies ---
    if args.fix:
        from codequest.deps import load_cache, execute_updates
        cache = load_cache()
        if not cache:
            print("No dependency data cached. Run a scan first.")
            return
        if args.fix not in cache:
            print(f"Project '{args.fix}' not found in cache.")
            print(f"Available: {', '.join(sorted(cache.keys()))}")
            return
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Updating {args.fix}" +
              (f" ({args.severity} only)" if args.severity else " (all severities)") + "...")
        result = execute_updates(
            args.fix, cache,
            severity_filter=args.severity,
            dry_run=args.dry_run,
        )
        print()
        for r in result.get("results", []):
            icon = "+" if r["status"] == "success" else \
                   "~" if r["status"] == "dry-run" else "x"
            print(f"  [{icon}] {r['name']} {r['from_version']} -> {r['to_version']} "
                  f"({r['risk']}) [{r['status']}]")
            if r["status"] == "failed" and r.get("output"):
                print(f"      Error: {r['output'][:120]}")
        print()
        print(f"Summary: {result.get('summary', '')}")
        if result.get("lock_file"):
            lf = result["lock_file"]
            print(f"Lock file: {lf.get('status', '?')} ({lf.get('package_count', 0)} packages)")
        if result.get("tests"):
            t = result["tests"]
            if t["available"]:
                print(f"Tests: {'PASSED' if t['passed'] else 'FAILED'}")
            else:
                print("Tests: no test suite detected")
        return

    # --- Generate lock file ---
    if args.lock:
        from codequest.deps import generate_lock_file
        from codequest.scanner import load_index
        projects = load_index()
        if args.lock.lower() == "all":
            for p in projects:
                if p.project_type in ("Python", "Node"):
                    result = generate_lock_file(str(p.path), p.project_type)
                    icon = "+" if result["status"] in ("created", "updated") else "x"
                    count = f" ({result['package_count']} pkgs)" if result["package_count"] else ""
                    print(f"  [{icon}] {p.name:30s} {result['status']}{count}")
                    if result.get("error"):
                        print(f"      {result['error']}")
        else:
            proj = next((p for p in projects if p.name == args.lock), None)
            if not proj:
                print(f"Project '{args.lock}' not found.")
                return
            result = generate_lock_file(str(proj.path), proj.project_type)
            print(f"{result['status']}: {result.get('lock_file', '')}")
            if result["package_count"]:
                print(f"  {result['package_count']} packages frozen")
            if result.get("error"):
                print(f"  Error: {result['error']}")
        return

    # --- Health score ---
    if args.health:
        from codequest.deps import load_cache, calculate_health_score
        from codequest.scanner import load_index
        cache = load_cache()
        projects = load_index()
        if args.health.lower() == "all":
            scores = []
            for p in projects:
                if p.project_type in ("Python", "Node"):
                    score = calculate_health_score(
                        p.name, str(p.path), p.project_type, cache
                    )
                    scores.append(score)
            scores.sort(key=lambda s: s["score"])
            print(f"{'Project':<35s} {'Grade':<7s} {'Score':<7s} {'Issues'}")
            print("-" * 80)
            for s in scores:
                issues = [f["detail"] for f in s["factors"].values() if f["score"] < f["max"]]
                issue_str = "; ".join(issues) if issues else "All clear"
                print(f"{s['project']:<35s} {s['grade']:<7s} {s['score']:<7d} {issue_str}")
            print()
            avg = sum(s["score"] for s in scores) / len(scores) if scores else 0
            print(f"Portfolio average: {avg:.0f}/100")
        else:
            proj = next((p for p in projects if p.name == args.health), None)
            if not proj:
                print(f"Project '{args.health}' not found.")
                return
            score = calculate_health_score(
                proj.name, str(proj.path), proj.project_type, cache
            )
            print(f"Health: {score['project']} — {score['grade']} ({score['score']}/100)")
            print()
            for key, f in score["factors"].items():
                bar = "=" * f["score"] + "." * (f["max"] - f["score"])
                icon = "+" if f["score"] == f["max"] else "-"
                print(f"  [{icon}] {bar} {f['score']}/{f['max']}  {f['detail']}")
        return

    # --- System updates ---
    if args.system:
        from codequest.ops.system import scan_all as sys_scan, save_cache as sys_save, generate_report as sys_report
        print("Scanning system... (this may take a moment)")
        data = sys_scan()
        sys_save(data)
        report = sys_report(data)
        print(report)
        return

    # --- GitHub repos ---
    if args.github:
        from codequest.ops.github import scan_repos, cross_reference_local, save_cache as gh_save, generate_report as gh_report
        from codequest.scanner import load_index
        print("Scanning GitHub repos...")
        data = scan_repos()
        if data.get("error"):
            print(f"Error: {data['error']}")
            return
        gh_save(data)
        projects = load_index()
        enriched = cross_reference_local(data, projects)
        report = gh_report(enriched)
        print(report)
        return

    # --- Project scan ---
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
