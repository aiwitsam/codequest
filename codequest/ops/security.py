"""Multi-source security aggregator."""

import json
import sqlite3
from pathlib import Path


def _query_turnstone():
    """Read findings from turnstone DB (read-only)."""
    db_path = Path.home() / ".turnstone" / "turnstone.db"
    if not db_path.is_file():
        return {"findings": [], "scans": [], "engagements": []}

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # Findings
        findings = []
        try:
            cursor = conn.execute(
                "SELECT title, severity, status, plugin_name, created_at, target "
                "FROM findings ORDER BY created_at DESC LIMIT 100"
            )
            findings = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            pass

        # Scans
        scans = []
        try:
            cursor = conn.execute(
                "SELECT id, target, status, started_at, finished_at, plugin_count "
                "FROM scans ORDER BY started_at DESC LIMIT 20"
            )
            scans = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            pass

        # Engagements
        engagements = []
        try:
            cursor = conn.execute(
                "SELECT id, name, target, status, created_at "
                "FROM engagements ORDER BY created_at DESC LIMIT 10"
            )
            engagements = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            pass

        conn.close()
        return {"findings": findings, "scans": scans, "engagements": engagements}

    except (sqlite3.Error, OSError):
        return {"findings": [], "scans": [], "engagements": []}


def _get_severity_breakdown(findings):
    """Count findings by severity."""
    breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = (f.get("severity") or "info").lower()
        if sev in breakdown:
            breakdown[sev] += 1
        else:
            breakdown["info"] += 1
    return breakdown


def _get_status_breakdown(findings):
    """Count findings by status."""
    breakdown = {}
    for f in findings:
        status = f.get("status", "new")
        breakdown[status] = breakdown.get(status, 0) + 1
    return breakdown


def _list_security_reports():
    """List report files from ~/security-reports/."""
    reports_dir = Path.home() / "security-reports"
    reports = []
    if not reports_dir.is_dir():
        return reports

    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        reports.append({
            "filename": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        })

    # Also check for HTML reports
    for f in sorted(reports_dir.glob("*.html"), reverse=True):
        reports.append({
            "filename": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        })

    reports.sort(key=lambda r: r["modified"], reverse=True)
    return reports[:20]


def _check_tool_outputs():
    """Check for output files from security tools."""
    tools = {}

    # WordPRESSED
    wp_dir = Path.home() / "wordPRESSED"
    if wp_dir.is_dir():
        outputs = list(wp_dir.glob("reports/*")) + list(wp_dir.glob("output/*"))
        tools["wordPRESSED"] = {
            "installed": True,
            "output_count": len(outputs),
            "path": str(wp_dir),
        }

    # HIPAA Scanner
    hipaa_dir = Path.home() / "hipaa-scanner"
    if hipaa_dir.is_dir():
        outputs = list(hipaa_dir.glob("reports/*")) + list(hipaa_dir.glob("output/*"))
        tools["hipaa-scanner"] = {
            "installed": True,
            "output_count": len(outputs),
            "path": str(hipaa_dir),
        }

    # SSL Manager
    ssl_dir = Path.home() / "ssl-manager-cpanel"
    if ssl_dir.is_dir():
        tools["ssl-manager"] = {
            "installed": True,
            "output_count": 0,
            "path": str(ssl_dir),
        }

    # Turnstone
    turnstone_dir = Path.home() / "turnstone"
    if turnstone_dir.is_dir():
        tools["turnstone"] = {
            "installed": True,
            "output_count": 0,
            "path": str(turnstone_dir),
        }

    return tools


def get_security_overview():
    """Aggregate security data from all sources."""
    turnstone = _query_turnstone()
    findings = turnstone["findings"]

    return {
        "findings": findings,
        "severity_breakdown": _get_severity_breakdown(findings),
        "status_breakdown": _get_status_breakdown(findings),
        "recent_scans": turnstone["scans"],
        "engagements": turnstone["engagements"],
        "reports": _list_security_reports(),
        "tools": _check_tool_outputs(),
        "total_findings": len(findings),
    }


def get_findings(severity=None, status=None, limit=100):
    """Get filtered findings."""
    turnstone = _query_turnstone()
    findings = turnstone["findings"]

    if severity:
        findings = [f for f in findings if (f.get("severity") or "").lower() == severity.lower()]
    if status:
        findings = [f for f in findings if f.get("status") == status]

    return findings[:limit]
