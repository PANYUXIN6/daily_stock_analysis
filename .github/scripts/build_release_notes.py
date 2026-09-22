"""Build concise GitHub Release notes from CHANGELOG entries."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"


def _run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def _section_for(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    pattern = re.compile(rf"^## \[{re.escape(version)}\].*?$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    next_match = re.search(r"^## \[", text[match.end() :], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(text)
    return text[match.end() : end].strip()


def _highlights(section: str) -> list[str]:
    release_highlights = re.search(
        r"^### 发布亮点\s*(.*?)(?=^### |\Z)",
        section,
        re.MULTILINE | re.DOTALL,
    )
    source = release_highlights.group(1) if release_highlights else section
    bullets = []
    for line in source.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        item = re.sub(r"^(feat|fix|docs|test|chore|ci|refactor):\s*", "", item, flags=re.I)
        bullets.append(item)
        if len(bullets) >= 6:
            break
    return bullets


def _previous_tag(tag: str) -> str:
    tags = _run_git("tag", "--sort=-v:refname").splitlines()
    semver_tags = [t for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    for current, previous in zip(semver_tags, semver_tags[1:]):
        if current == tag:
            return previous
    return semver_tags[1] if len(semver_tags) > 1 else ""


def build(tag: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise SystemExit(f"Unsupported release tag: {tag}")
    version = tag[1:]
    section = _section_for(version)
    previous_tag = _previous_tag(tag)
    highlights = _highlights(section)

    lines = [f"## {tag}", "", "### Highlights"]
    if highlights:
        lines.extend(f"- {item}" for item in highlights)
    else:
        lines.append("- See the changelog for release details.")

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if repository:
        compare_from = previous_tag or tag
        lines.extend(
            [
                "",
                "### Full changelog",
                f"https://github.com/{repository}/compare/{compare_from}...{tag}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    tag = os.environ.get("RELEASE_TAG") or os.environ.get("GITHUB_REF_NAME") or ""
    body = build(tag)
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/release_body.md")
    output.write_text(body, encoding="utf-8")


if __name__ == "__main__":
    main()
