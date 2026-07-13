"""Page-text hygiene (D9): strip per-page boilerplate; detect section headings.

Heading detection is used for TAGGING metadata only — never for chunk
boundaries (D9). A missed heading degrades one citation label, nothing more.
"""

import re

# Boilerplate the manual repeats on every page (D9 corpus findings).
# pypdf extracts the "WE ARE YOUR EVERLASTING COMPANY" logo as standalone
# lines (EVERLASTING / WE / COMPANY / AREYOUR), twice per page.
_BOILERPLATE = (
    re.compile(r"^.*EVERLASTING\s+COMPANY.*$", re.MULTILINE),
    re.compile(r"^\s*(?:EVERLASTING|WE|COMPANY|AREYOUR)\s*$", re.MULTILINE),
    re.compile(r"^.*BBK-V\.\d+_ENG.*$", re.MULTILINE),
    re.compile(r"^.*People First.*$", re.MULTILINE),
)

# One pattern covering the manual's four numbering formats:
# "1.SAFETY", "2. GENERAL", "3-INSTALLATION", "2.2.1 Canopy", "1.2.1.Using",
# "5.11. General ...". Title must start with an uppercase letter (cuts table
# rows and numeric limits); length cap cuts prose sentences.
_HEADING = re.compile(r"^(\d+(?:\.\d+)*)[.\-]?\s*([A-Z][^\n]{1,59}?)\s*$")

# Headings in this manual are Title Case or ALL CAPS; a lowercase word (other
# than a connector) means the line is prose that happens to start with a number.
_CONNECTORS = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}


def clean_page_text(text: str) -> str:
    for pattern in _BOILERPLATE:
        text = pattern.sub("", text)
    # collapse the blank lines the removals leave behind
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def detect_heading(line: str) -> str | None:
    match = _HEADING.match(line.strip())
    if not match:
        return None
    number, title = match.groups()
    title = title.strip()
    words = title.split()
    if not all(w[0].isupper() or w.lower() in _CONNECTORS for w in words):
        return None
    return f"{number} {title}"
