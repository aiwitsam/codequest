"""README parsing module for CodeQuest.

Parses markdown README files into structured sections for display
and summarization.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReadmeInfo:
    """Structured representation of a parsed README file."""

    title: str = ""
    description: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    quick_start_steps: list[str] = field(default_factory=list)
    install_instructions: str = ""
    usage: str = ""
    raw: str = ""


def parse_readme(content: str) -> ReadmeInfo:
    """Parse markdown README content into a ReadmeInfo structure.

    Extracts title, description, sections by heading, and identifies
    special sections like install instructions, quick start steps,
    and usage information.

    Args:
        content: Raw markdown string.

    Returns:
        Populated ReadmeInfo dataclass.
    """
    info = ReadmeInfo(raw=content)

    if not content.strip():
        return info

    lines = content.strip().split("\n")

    # Extract title from first # heading (h1)
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match:
        info.title = title_match.group(1).strip()

    # Extract description: text between title (or start) and first ## heading
    # Find where the first ## heading is
    first_h2_match = re.search(r"^##\s+", content, re.MULTILINE)
    if first_h2_match:
        preamble_end = first_h2_match.start()
    else:
        preamble_end = len(content)

    # Preamble is everything before the first ## heading
    preamble = content[:preamble_end]

    # Remove the title line from the preamble to get description
    if title_match:
        preamble = preamble[: title_match.start()] + preamble[title_match.end() :]

    # Remove badges, blank lines, and extract meaningful text
    desc_lines = []
    for line in preamble.split("\n"):
        stripped = line.strip()
        # Skip blank lines, badge images, and horizontal rules
        if not stripped:
            continue
        if re.match(r"^\[?!\[", stripped):
            continue
        if re.match(r"^---+$|^===+$|^\*\*\*+$", stripped):
            continue
        desc_lines.append(stripped)

    info.description = " ".join(desc_lines).strip()

    # Split content into sections by ## headings
    section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    section_matches = list(section_pattern.finditer(content))

    for i, match in enumerate(section_matches):
        heading = match.group(1).strip()
        start = match.end()
        if i + 1 < len(section_matches):
            end = section_matches[i + 1].start()
        else:
            end = len(content)

        section_content = content[start:end].strip()
        info.sections[heading] = section_content

    # Identify special sections by pattern matching on heading names
    install_pattern = re.compile(r"^(install|setup|getting[\s_-]*started).*$", re.IGNORECASE)
    quick_start_pattern = re.compile(r"^(quick[\s_-]*start|getting[\s_-]*started).*$", re.IGNORECASE)
    usage_pattern = re.compile(r"^(usage|how[\s_-]*to[\s_-]*use).*$", re.IGNORECASE)

    for heading, section_content in info.sections.items():
        if install_pattern.match(heading) and not info.install_instructions:
            info.install_instructions = section_content

        if usage_pattern.match(heading) and not info.usage:
            info.usage = section_content

    # Extract quick start steps from quick start, getting started, or install sections
    step_source_content = ""
    for heading, section_content in info.sections.items():
        if quick_start_pattern.match(heading):
            step_source_content = section_content
            break

    # Fall back to install section if no quick start section found
    if not step_source_content:
        for heading, section_content in info.sections.items():
            if install_pattern.match(heading):
                step_source_content = section_content
                break

    if step_source_content:
        info.quick_start_steps = _extract_steps(step_source_content)

    return info


def _extract_steps(content: str) -> list[str]:
    """Extract numbered or bulleted list items from markdown content.

    Looks for ordered lists (1. 2. 3.) first, then falls back to
    unordered bullet lists (- or *).

    Args:
        content: Markdown section content.

    Returns:
        List of step strings with list markers removed.
    """
    # Try numbered lists first
    numbered = re.findall(r"^\s*\d+\.\s+(.+)$", content, re.MULTILINE)
    if numbered:
        return [step.strip() for step in numbered]

    # Fall back to bullet lists
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", content, re.MULTILINE)
    if bullets:
        return [step.strip() for step in bullets]

    return []


def get_summary_card(info: ReadmeInfo) -> str:
    """Generate a plain-text summary card from a ReadmeInfo.

    Produces a formatted text block with the project name, description,
    quick start steps, and usage. Sections with no content are omitted.

    Args:
        info: Parsed ReadmeInfo dataclass.

    Returns:
        Formatted plain-text summary string.
    """
    parts: list[str] = []

    # Title
    title = info.title or "Untitled Project"
    parts.append(title)
    parts.append("=" * len(title))

    # Description
    if info.description:
        parts.append(info.description)

    # Quick start steps
    if info.quick_start_steps:
        parts.append("")
        parts.append("Quick Start:")
        for i, step in enumerate(info.quick_start_steps, 1):
            parts.append(f"  {i}. {step}")

    # Usage
    if info.usage:
        parts.append("")
        parts.append(f"Usage: {info.usage}")

    return "\n".join(parts)


def parse_project_readme(readme_path: Path) -> ReadmeInfo:
    """Read a README file from disk and parse it.

    Args:
        readme_path: Path to the README markdown file.

    Returns:
        Populated ReadmeInfo, or empty ReadmeInfo if the file
        cannot be read or does not exist.
    """
    try:
        content = readme_path.read_text(encoding="utf-8")
        return parse_readme(content)
    except (OSError, UnicodeDecodeError):
        return ReadmeInfo()
