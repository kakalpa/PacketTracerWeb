"""
Markdown AST Parser and Extraction Engine for Proposal Verification.
Provides pure standard library AST parsing with code fence immunity,
finding/proposal extraction, table/codeblock query methods, and 5x5 matrix retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class ComponentID(str, Enum):
    C1 = "C1"  # Virtualized Desktop Container
    C2 = "C2"  # Apache Guacamole Stack
    C3 = "C3"  # Nginx Edge Gateway
    C4 = "C4"  # Flask/Gunicorn Management Service
    C5 = "C5"  # Deployment & Orchestration Harness

    @classmethod
    def normalize(cls, val: str | int) -> str:
        s = str(val).strip().upper()
        if not s.startswith("C"):
            s = f"C{s}"
        return s


class DomainCode(str, Enum):
    SEC = "SEC"      # Security & Hardening
    PERF = "PERF"    # Performance & Scaling
    REL = "REL"      # High Availability & Reliability (alias HA)
    HA = "HA"        # Alias for REL
    USE = "USE"      # Usability
    MAINT = "MAINT"  # Maintainability

    @classmethod
    def normalize(cls, val: str) -> str:
        s = str(val).strip().upper()
        if s == "HA":
            return "REL"
        return s


@dataclass
class HeadingNode:
    level: int
    title: str
    line_start: int
    line_end: int = 0
    path: str = ""
    parent: Optional[HeadingNode] = None
    children: List[HeadingNode] = field(default_factory=list)
    raw_content: str = ""

    def get_full_content(self) -> str:
        """Returns the full text contained in this section including children."""
        return self.raw_content


@dataclass
class TableNode:
    headers: List[str]
    rows: List[Dict[str, str]]
    raw_rows: List[List[str]]
    line_start: int
    line_end: int
    section_path: str = ""


@dataclass
class CodeBlockNode:
    language: str
    code: str
    line_start: int
    line_end: int
    section_path: str = ""


@dataclass
class FindingNode:
    finding_id: str
    component_id: str
    domain_code: str
    item_num: int
    title: str
    target_files: List[str] = field(default_factory=list)
    line_numbers: List[str] = field(default_factory=list)
    limitation_description: str = ""
    reproduction_command: str = ""
    operational_impact: str = ""
    recommended_direction: str = ""
    raw_text: str = ""
    line_start: int = 0
    line_end: int = 0
    section_path: str = ""


@dataclass
class ProposalNode:
    proposal_id: str
    component_id: str
    domain_code: Optional[str]
    item_num: int
    title: str
    mapped_findings: List[str] = field(default_factory=list)
    current_state_risk: str = ""
    proposed_solution: str = ""
    impact_on_stability: str = ""
    implementation_complexity: str = ""
    migration_risk: str = ""
    affected_files: List[str] = field(default_factory=list)
    raw_text: str = ""
    line_start: int = 0
    line_end: int = 0
    section_path: str = ""


@dataclass
class ParsedDocument:
    raw_text: str
    lines: List[str]
    headings: List[HeadingNode]
    heading_tree: List[HeadingNode]
    tables: List[TableNode]
    code_blocks: List[CodeBlockNode]
    findings: List[FindingNode]
    proposals: List[ProposalNode]
    findings_by_id: Dict[str, FindingNode] = field(default_factory=dict)
    proposals_by_id: Dict[str, ProposalNode] = field(default_factory=dict)

    def find_sections_by_title(self, pattern: str, regex: bool = True) -> List[HeadingNode]:
        """Lookup sections whose title matches the given pattern."""
        flags = re.IGNORECASE
        results: List[HeadingNode] = []
        for h in self.headings:
            if regex:
                if re.search(pattern, h.title, flags):
                    results.append(h)
            else:
                if pattern.lower() in h.title.lower():
                    results.append(h)
        return results

    def get_section_content(self, pattern: str) -> str:
        """Finds the first section matching pattern and returns its raw content."""
        sections = self.find_sections_by_title(pattern)
        if not sections:
            return ""
        return sections[0].raw_content

    def get_findings_by_component(self, comp: str | int) -> List[FindingNode]:
        """Returns all findings belonging to a component (e.g. 'C1' or 1)."""
        comp_norm = ComponentID.normalize(comp)
        return [f for f in self.findings if f.component_id == comp_norm]

    def get_findings_by_domain(self, domain: str) -> List[FindingNode]:
        """Returns all findings belonging to a domain (e.g. 'SEC', 'REL', 'HA')."""
        dom_norm = DomainCode.normalize(domain)
        return [f for f in self.findings if DomainCode.normalize(f.domain_code) == dom_norm]

    def get_findings_matrix(self) -> Dict[Tuple[str, str], List[FindingNode]]:
        """Returns a 5x5 matrix mapping (ComponentID, DomainCode) -> List[FindingNode]."""
        matrix: Dict[Tuple[str, str], List[FindingNode]] = {}
        comps = ["C1", "C2", "C3", "C4", "C5"]
        doms = ["SEC", "PERF", "REL", "USE", "MAINT"]
        for c in comps:
            for d in doms:
                matrix[(c, d)] = []

        for f in self.findings:
            c = ComponentID.normalize(f.component_id)
            d = DomainCode.normalize(f.domain_code)
            if (c, d) in matrix:
                matrix[(c, d)].append(f)
        return matrix

    def get_proposals_by_component(self, comp: str | int) -> List[ProposalNode]:
        """Returns all proposals belonging to a component."""
        comp_norm = ComponentID.normalize(comp)
        return [p for p in self.proposals if p.component_id == comp_norm]

    def get_proposals_by_domain(self, domain: str) -> List[ProposalNode]:
        """Returns all proposals belonging to an operational domain."""
        dom_norm = DomainCode.normalize(domain)
        results: List[ProposalNode] = []
        for p in self.proposals:
            if p.domain_code and DomainCode.normalize(p.domain_code) == dom_norm:
                results.append(p)
                continue
            # Check mapped findings domain if proposal domain is not explicit
            for f_id in p.mapped_findings:
                if f_id in self.findings_by_id:
                    f = self.findings_by_id[f_id]
                    if DomainCode.normalize(f.domain_code) == dom_norm:
                        results.append(p)
                        break
        return results

    def find_tables_with_headers(self, *required_headers: str) -> List[TableNode]:
        """Finds tables that contain all specified headers (case-insensitive substring match)."""
        matching: List[TableNode] = []
        for t in self.tables:
            header_strs = [h.strip().lower() for h in t.headers]
            all_found = True
            for req in required_headers:
                req_lower = req.strip().lower()
                if not any(req_lower in h for h in header_strs):
                    all_found = False
                    break
            if all_found:
                matching.append(t)
        return matching

    def search_code_blocks(self, pattern: str, language: Optional[str] = None) -> List[CodeBlockNode]:
        """Searches code blocks matching code pattern and optional language filter."""
        results: List[CodeBlockNode] = []
        flags = re.IGNORECASE
        for cb in self.code_blocks:
            if language is not None and cb.language.lower() != language.lower():
                continue
            if re.search(pattern, cb.code, flags):
                results.append(cb)
        return results

    def search_text(self, regex_pattern: str, flags: int = re.IGNORECASE) -> List[str]:
        """Finds all non-overlapping matches of regex pattern in document text."""
        return re.findall(regex_pattern, self.raw_text, flags)


class MarkdownParser:
    """Pure Python Standard Library line-scanning Markdown AST parser."""

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
    _FENCE_RE = re.compile(r"^(```|~~~)(.*)$")
    _TABLE_DELIM_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
    _FINDING_RE = re.compile(
        r"\[?(FINDING-C([1-5])-([A-Z]{2,5})-([0-9]{1,3}))\]?\s*:?\s*(.*)",
        re.IGNORECASE,
    )
    _PROPOSAL_RE = re.compile(
        r"\[?(PROP-C([1-5])(?:-([A-Z]{2,5}))?-([0-9]{1,3}))\]?\s*:?\s*(.*)",
        re.IGNORECASE,
    )

    @classmethod
    def parse_file(cls, path: str | Path) -> ParsedDocument:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Markdown file not found: {p.resolve()}")
        content = p.read_text(encoding="utf-8", errors="replace")
        return cls.parse_string(content)

    @classmethod
    def parse_string(cls, content: str) -> ParsedDocument:
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        lines = content.splitlines()
        headings: List[HeadingNode] = []
        heading_tree: List[HeadingNode] = []
        tables: List[TableNode] = []
        code_blocks: List[CodeBlockNode] = []

        # Pass 1: Parse code blocks and headings with code fence immunity
        in_code_block = False
        fence_char = ""
        cb_lang = ""
        cb_start = 0
        cb_lines: List[str] = []

        heading_stack: List[HeadingNode] = []

        for idx, line in enumerate(lines):
            fence_match = cls._FENCE_RE.match(line.strip())
            if fence_match:
                marker = fence_match.group(1)
                info = fence_match.group(2).strip()
                if not in_code_block:
                    in_code_block = True
                    fence_char = marker
                    cb_lang = info
                    cb_start = idx
                    cb_lines = []
                    continue
                elif marker == fence_char:
                    # Closing fence
                    in_code_block = False
                    code_text = "\n".join(cb_lines)
                    sec_path = " > ".join(h.title for h in heading_stack)
                    code_blocks.append(
                        CodeBlockNode(
                            language=cb_lang,
                            code=code_text,
                            line_start=cb_start + 1,
                            line_end=idx + 1,
                            section_path=sec_path,
                        )
                    )
                    continue

            if in_code_block:
                cb_lines.append(line)
                continue

            # Heading detection (outside code blocks)
            h_match = cls._HEADING_RE.match(line)
            if h_match:
                level = len(h_match.group(1))
                title = h_match.group(2).strip()

                # Adjust heading stack
                while heading_stack and heading_stack[-1].level >= level:
                    popped = heading_stack.pop()
                    popped.line_end = idx

                parent = heading_stack[-1] if heading_stack else None
                node_path = (
                    " > ".join([h.title for h in heading_stack] + [title])
                    if heading_stack
                    else title
                )
                node = HeadingNode(
                    level=level,
                    title=title,
                    line_start=idx + 1,
                    path=node_path,
                    parent=parent,
                )
                if parent:
                    parent.children.append(node)
                else:
                    heading_tree.append(node)

                heading_stack.append(node)
                headings.append(node)

        # Close any open headings
        for h in heading_stack:
            h.line_end = len(lines)

        # Populate raw_content for each heading
        for h in headings:
            start_i = h.line_start - 1
            end_i = h.line_end if h.line_end > 0 else len(lines)
            h.raw_content = "\n".join(lines[start_i:end_i])

        # Pass 2: Parse tables (outside code blocks)
        tables = cls._extract_tables(lines, headings)

        # Pass 3 & 4: Extract findings and proposals
        findings, proposals = cls._extract_findings_and_proposals(content, lines, headings)

        findings_by_id = {f.finding_id: f for f in findings}
        proposals_by_id = {p.proposal_id: p for p in proposals}

        return ParsedDocument(
            raw_text=content,
            lines=lines,
            headings=headings,
            heading_tree=heading_tree,
            tables=tables,
            code_blocks=code_blocks,
            findings=findings,
            proposals=proposals,
            findings_by_id=findings_by_id,
            proposals_by_id=proposals_by_id,
        )

    @classmethod
    def _mask_code_blocks(cls, lines: List[str]) -> str:
        """
        Replaces lines inside fenced code blocks and fence delimiters with
        whitespace of identical length, preserving line counts and character offsets.
        """
        in_code_block = False
        fence_char = ""
        masked_lines: List[str] = []
        for line in lines:
            fence_match = cls._FENCE_RE.match(line.strip())
            if fence_match:
                marker = fence_match.group(1)
                if not in_code_block:
                    in_code_block = True
                    fence_char = marker
                    masked_lines.append(" " * len(line))
                    continue
                elif marker == fence_char:
                    in_code_block = False
                    fence_char = ""
                    masked_lines.append(" " * len(line))
                    continue
            if in_code_block:
                masked_lines.append(" " * len(line))
            else:
                masked_lines.append(line)
        return "\n".join(masked_lines)

    @classmethod
    def _extract_tables(cls, lines: List[str], headings: List[HeadingNode]) -> List[TableNode]:
        tables: List[TableNode] = []
        in_code_block = False
        fence_char = ""
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i].strip()
            fence_match = cls._FENCE_RE.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if not in_code_block:
                    in_code_block = True
                    fence_char = marker
                    i += 1
                    continue
                elif marker == fence_char:
                    in_code_block = False
                    fence_char = ""
                    i += 1
                    continue

            if in_code_block or not line.startswith("|") or not line.endswith("|"):
                i += 1
                continue

            # Check if line i is table header and line i+1 is table delimiter
            if i + 1 < n and cls._TABLE_DELIM_RE.match(lines[i + 1].strip()):
                table_start = i
                raw_headers = [c.strip() for c in lines[i].strip().split("|")[1:-1]]
                i += 2  # Skip header and delimiter

                rows: List[Dict[str, str]] = []
                raw_rows: List[List[str]] = []

                while i < n:
                    row_line = lines[i].strip()
                    if not (row_line.startswith("|") and row_line.endswith("|")):
                        break
                    cells = [c.strip() for c in row_line.split("|")[1:-1]]
                    raw_rows.append(cells)
                    row_dict: Dict[str, str] = {}
                    for h_idx, header in enumerate(raw_headers):
                        val = cells[h_idx] if h_idx < len(cells) else ""
                        row_dict[header] = val
                    rows.append(row_dict)
                    i += 1

                table_end = i
                # Locate enclosing heading
                sec_path = ""
                for h in headings:
                    if h.line_start <= table_start + 1 <= h.line_end:
                        sec_path = h.path

                tables.append(
                    TableNode(
                        headers=raw_headers,
                        rows=rows,
                        raw_rows=raw_rows,
                        line_start=table_start + 1,
                        line_end=table_end,
                        section_path=sec_path,
                    )
                )
            else:
                i += 1

        return tables

    @classmethod
    def _extract_findings_and_proposals(
        cls,
        full_content: str,
        lines: List[str],
        headings: List[HeadingNode],
    ) -> Tuple[List[FindingNode], List[ProposalNode]]:
        findings: List[FindingNode] = []
        proposals: List[ProposalNode] = []

        seen_finding_ids: Set[str] = set()
        seen_proposal_ids: Set[str] = set()

        masked_content = cls._mask_code_blocks(lines)

        # Step A: Scan for finding blocks across the text
        # Patterns can be headings, bold text, or table rows
        # 1. Regex search for finding headers
        finding_matches = list(
            re.finditer(
                r"(?m)^(?:#{1,6}\s+|[\*\-]\s+|\*\*)?\[?(FINDING-C([1-5])-([A-Z]{2,5})-([0-9]{1,3}))\]?\s*:?\s*([^\n]*)",
                masked_content,
                re.IGNORECASE,
            )
        )

        for idx, match in enumerate(finding_matches):
            finding_id = match.group(1).upper()
            if finding_id in seen_finding_ids:
                continue
            seen_finding_ids.add(finding_id)

            comp_id = f"C{match.group(2)}"
            raw_dom = match.group(3).upper()
            dom_code = DomainCode.normalize(raw_dom)
            item_num = int(match.group(4))
            title = match.group(5).strip().strip("*").strip()

            block_start = match.start()
            block_end = (
                finding_matches[idx + 1].start()
                if idx + 1 < len(finding_matches)
                else len(full_content)
            )

            # Check if a proposal or high-level heading starts earlier
            next_heading = re.search(r"\n#{1,3}\s+", masked_content[block_start + 1 : block_end])
            if next_heading:
                block_end = block_start + 1 + next_heading.start()

            block_text = full_content[block_start:block_end]

            # Parse finding attributes from block_text
            target_files = cls._extract_field_list(
                block_text, [r"Target Files?", r"Target Component / Files?", r"File"]
            )
            line_numbers = cls._extract_field_list(
                block_text, [r"Exact Code Reference / Line Numbers?", r"Line Numbers?", r"Code Reference"]
            )
            limitation = cls._extract_field_text(
                block_text,
                [
                    r"Limitation / Vulnerability Description",
                    r"Limitation Description",
                    r"Vulnerability Description",
                    r"Description",
                ],
            )
            reproduction = cls._extract_field_text(
                block_text,
                [
                    r"Empirical Evidence / Reproduction Command",
                    r"Reproduction Command",
                    r"Empirical Evidence",
                    r"Reproduction",
                ],
            )
            impact = cls._extract_field_text(
                block_text,
                [
                    r"Current Operational Impact",
                    r"Operational Impact",
                    r"Current Impact",
                    r"Impact",
                ],
            )
            recommendation = cls._extract_field_text(
                block_text,
                [
                    r"Recommended Direction",
                    r"Recommendation",
                    r"Proposed Direction",
                ],
            )

            # Determine line number
            line_num = full_content[:block_start].count("\n") + 1

            sec_path = ""
            for h in headings:
                if h.line_start <= line_num <= h.line_end:
                    sec_path = h.path

            findings.append(
                FindingNode(
                    finding_id=finding_id,
                    component_id=comp_id,
                    domain_code=dom_code,
                    item_num=item_num,
                    title=title,
                    target_files=target_files,
                    line_numbers=line_numbers,
                    limitation_description=limitation or title,
                    reproduction_command=reproduction,
                    operational_impact=impact,
                    recommended_direction=recommendation,
                    raw_text=block_text,
                    line_start=line_num,
                    section_path=sec_path,
                )
            )

        # Step B: Scan for proposal blocks across the text
        proposal_matches = list(
            re.finditer(
                r"(?m)^(?:#{1,6}\s+|[\*\-]\s+|\*\*)?\[?(PROP-C([1-5])(?:-([A-Z]{2,5}))?-([0-9]{1,3}))\]?\s*:?\s*([^\n]*)",
                masked_content,
                re.IGNORECASE,
            )
        )

        for idx, match in enumerate(proposal_matches):
            prop_id = match.group(1).upper()
            if prop_id in seen_proposal_ids:
                continue
            seen_proposal_ids.add(prop_id)

            comp_id = f"C{match.group(2)}"
            raw_dom = match.group(3).upper() if match.group(3) else None
            dom_code = DomainCode.normalize(raw_dom) if raw_dom else None
            item_num = int(match.group(4))
            title = match.group(5).strip().strip("*").strip()

            block_start = match.start()
            block_end = (
                proposal_matches[idx + 1].start()
                if idx + 1 < len(proposal_matches)
                else len(full_content)
            )

            next_heading = re.search(r"\n#{1,3}\s+", masked_content[block_start + 1 : block_end])
            if next_heading:
                block_end = block_start + 1 + next_heading.start()

            block_text = full_content[block_start:block_end]

            mapped_findings = re.findall(
                r"FINDING-C[1-5]-[A-Z]{2,5}-[0-9]{1,3}", block_text, re.IGNORECASE
            )
            mapped_findings = [f.upper() for f in mapped_findings]

            current_state = cls._extract_field_text(
                block_text,
                [r"Current State & Risk", r"Current State and Identified Limitation or Risk", r"Current State", r"Risk"],
            )
            solution = cls._extract_field_text(
                block_text,
                [
                    r"Proposed Solution & Technical Approach",
                    r"Proposed Solution and Technical Approach",
                    r"Proposed Solution",
                    r"Technical Approach",
                ],
            )
            stability = cls._extract_field_text(
                block_text,
                [
                    r"Impact on Production Stability",
                    r"Expected Impact on Production Readiness and Operational Stability",
                    r"Impact on Stability",
                    r"Operational Impact",
                ],
            )
            complexity = cls._extract_field_text(
                block_text,
                [
                    r"Implementation Feasibility & Complexity",
                    r"Implementation Complexity",
                    r"Feasibility",
                    r"Complexity",
                ],
            )
            migration = cls._extract_field_text(
                block_text,
                [
                    r"Migration Steps / Rollback",
                    r"Implementation Feasibility, Risk Assessment, and Migration Steps",
                    r"Migration Steps",
                    r"Migration & Rollback",
                    r"Migration Risk",
                ],
            )
            affected_files = cls._extract_field_list(
                block_text,
                [r"Affected Components & Files", r"Affected Files", r"Target Files?"],
            )

            # Determine line number
            line_num = full_content[:block_start].count("\n") + 1

            sec_path = ""
            for h in headings:
                if h.line_start <= line_num <= h.line_end:
                    sec_path = h.path

            proposals.append(
                ProposalNode(
                    proposal_id=prop_id,
                    component_id=comp_id,
                    domain_code=dom_code,
                    item_num=item_num,
                    title=title,
                    mapped_findings=mapped_findings,
                    current_state_risk=current_state or title,
                    proposed_solution=solution,
                    impact_on_stability=stability,
                    implementation_complexity=complexity,
                    migration_risk=migration,
                    affected_files=affected_files,
                    raw_text=block_text,
                    line_start=line_num,
                    section_path=sec_path,
                )
            )

        return findings, proposals

    @classmethod
    def _extract_field_text(cls, block: str, labels: List[str]) -> str:
        for lbl in labels:
            pattern = (
                r"(?:^|\n)[\*\-]?\s*\*{0,2}"
                + lbl
                + r"\*{0,2}\s*:?\s*([^\n]+(?:\n(?!\s*[\*\-]?\s*\*{0,2}[A-Z][a-zA-Z\s/&]+(?:\*{1,2})?:)[^\n]+)*)"
            )
            m = re.search(pattern, block, re.IGNORECASE)
            if m:
                text = m.group(1).strip()
                return text
        return ""

    @classmethod
    def _extract_field_list(cls, block: str, labels: List[str]) -> List[str]:
        raw = cls._extract_field_text(block, labels)
        if not raw:
            return []
        # Split on commas, newlines, or backticks
        items: List[str] = []
        for part in re.split(r"[,;\n`]", raw):
            cleaned = part.strip().strip("-*•").strip()
            if cleaned and len(cleaned) > 1 and not cleaned.lower().startswith("line"):
                items.append(cleaned)
        return items
