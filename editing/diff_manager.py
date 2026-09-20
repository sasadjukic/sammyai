"""
Diff-based editing manager for the text editor.

This module provides functionality for generating, parsing, and applying
text diffs in various formats (unified, context, etc.).
"""

import difflib
import re
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from enum import Enum


class DiffFormat(Enum):
    """Supported diff formats."""
    UNIFIED = "unified"
    CONTEXT = "context"
    NDIFF = "ndiff"


class DiffConflict(Exception):
    """Exception raised when a diff cannot be applied due to conflicts."""
    pass


@dataclass
class DiffHunk:
    """Represents a single hunk (change block) in a diff."""
    original_start: int  # Line number in original file (1-indexed)
    original_count: int  # Number of lines in original
    modified_start: int  # Line number in modified file (1-indexed)
    modified_count: int  # Number of lines in modified
    lines: List[str]     # Diff lines (with +, -, or space prefix)
    header: str          # Hunk header line (e.g., @@ -1,4 +1,5 @@)
    
    def __str__(self):
        if self.header.startswith('@@'):
            body = []
            for line in self.lines:
                body.append(line)
                if not line.endswith(('\n', '\r')):
                    body.append('\n\\ No newline at end of file\n')
            return self.header.rstrip('\r\n') + '\n' + ''.join(body)
        return f"{self.header}\n" + "\n".join(self.lines)


@dataclass
class Diff:
    """Represents a complete diff between two texts."""
    original_name: str
    modified_name: str
    hunks: List[DiffHunk]
    format: DiffFormat
    
    def __str__(self):
        """Convert diff to string representation."""
        result = []
        if self.format == DiffFormat.UNIFIED:
            return (f"--- {self.original_name}\n+++ {self.modified_name}\n"
                    + ''.join(str(hunk) for hunk in self.hunks))
        
        for hunk in self.hunks:
            result.append(str(hunk))
        
        return "\n".join(result)


class DiffManager:
    """Manager for diff-based editing operations."""
    
    def __init__(self):
        """Initialize the diff manager."""
        self._history: List[Tuple[str, str]] = []  # History of (original, modified) pairs
        self._current_index: int = -1
    
    def generate_diff(
        self,
        original: str,
        modified: str,
        original_name: str = "original",
        modified_name: str = "modified",
        format: DiffFormat = DiffFormat.UNIFIED,
        context_lines: int = 3
    ) -> Diff:
        """
        Generate a diff between two texts.
        
        Args:
            original: Original text content
            modified: Modified text content
            original_name: Name/label for original text
            modified_name: Name/label for modified text
            format: Diff format to use
            context_lines: Number of context lines to include
            
        Returns:
            Diff object containing the differences
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        
        if format == DiffFormat.UNIFIED:
            return self._generate_unified_diff(
                original_lines, modified_lines,
                original_name, modified_name,
                context_lines
            )
        elif format == DiffFormat.CONTEXT:
            return self._generate_context_diff(
                original_lines, modified_lines,
                original_name, modified_name,
                context_lines
            )
        elif format == DiffFormat.NDIFF:
            return self._generate_ndiff(
                original_lines, modified_lines,
                original_name, modified_name
            )
        else:
            raise ValueError(f"Unsupported diff format: {format}")
    
    def _generate_unified_diff(
        self,
        original_lines: List[str],
        modified_lines: List[str],
        original_name: str,
        modified_name: str,
        context_lines: int
    ) -> Diff:
        """Generate a unified diff."""
        diff_lines = list(difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=original_name,
            tofile=modified_name,
            lineterm='',
            n=context_lines
        ))
        
        # Parse the unified diff into hunks
        hunks = self._parse_unified_diff(diff_lines)
        
        return Diff(
            original_name=original_name,
            modified_name=modified_name,
            hunks=hunks,
            format=DiffFormat.UNIFIED
        )
    
    def _generate_context_diff(
        self,
        original_lines: List[str],
        modified_lines: List[str],
        original_name: str,
        modified_name: str,
        context_lines: int
    ) -> Diff:
        """Generate a context diff."""
        diff_lines = list(difflib.context_diff(
            original_lines,
            modified_lines,
            fromfile=original_name,
            tofile=modified_name,
            lineterm='',
            n=context_lines
        ))
        
        # For context diff, we'll store it as a single hunk
        # since parsing context diff is more complex
        hunks = [DiffHunk(
            original_start=1,
            original_count=len(original_lines),
            modified_start=1,
            modified_count=len(modified_lines),
            lines=diff_lines[2:] if len(diff_lines) > 2 else [],
            header="Context Diff"
        )]
        
        return Diff(
            original_name=original_name,
            modified_name=modified_name,
            hunks=hunks,
            format=DiffFormat.CONTEXT
        )
    
    def _generate_ndiff(
        self,
        original_lines: List[str],
        modified_lines: List[str],
        original_name: str,
        modified_name: str
    ) -> Diff:
        """Generate an ndiff (detailed line-by-line diff)."""
        diff_lines = list(difflib.ndiff(original_lines, modified_lines))
        
        # Store as a single hunk
        hunks = [DiffHunk(
            original_start=1,
            original_count=len(original_lines),
            modified_start=1,
            modified_count=len(modified_lines),
            lines=diff_lines,
            header="NDiff"
        )]
        
        return Diff(
            original_name=original_name,
            modified_name=modified_name,
            hunks=hunks,
            format=DiffFormat.NDIFF
        )
    
    def _parse_unified_diff(self, diff_lines: List[str]) -> List[DiffHunk]:
        """
        Parse unified diff output into DiffHunk objects.
        
        Args:
            diff_lines: Lines from unified_diff output
            
        Returns:
            List of DiffHunk objects
        """
        hunks = []
        current_hunk = None
        hunk_pattern = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
        
        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            
            # Skip header lines (---, +++)
            if current_hunk is None and (line.startswith('---') or line.startswith('+++')):
                i += 1
                continue
            
            # Check for hunk header
            match = hunk_pattern.match(line)
            if match:
                # Save previous hunk if exists
                if current_hunk:
                    hunks.append(current_hunk)
                
                # Parse hunk header
                orig_start = int(match.group(1))
                orig_count = int(match.group(2)) if match.group(2) else 1
                mod_start = int(match.group(3))
                mod_count = int(match.group(4)) if match.group(4) else 1
                
                current_hunk = DiffHunk(
                    original_start=orig_start,
                    original_count=orig_count,
                    modified_start=mod_start,
                    modified_count=mod_count,
                    lines=[],
                    header=line.rstrip('\r\n')
                )
            elif line.startswith('\\ No newline at end of file'):
                if current_hunk is None or not current_hunk.lines:
                    raise DiffConflict("No-newline marker has no preceding diff line")
                current_hunk.lines[-1] = current_hunk.lines[-1].removesuffix('\n').removesuffix('\r')
            elif current_hunk is not None:
                # Add line to current hunk
                current_hunk.lines.append(line)
            
            i += 1
        
        # Add the last hunk
        if current_hunk:
            hunks.append(current_hunk)
        
        return hunks
    
    def apply_diff(
        self,
        original: str,
        diff: Diff,
        strict: bool = True
    ) -> str:
        """
        Apply a diff to the original text.
        
        Args:
            original: Original text content
            diff: Diff object to apply
            strict: If True, raise exception on conflicts; if False, apply best effort
            
        Returns:
            Modified text after applying diff
            
        Raises:
            DiffConflict: If strict=True and diff cannot be applied cleanly
        """
        if diff.format != DiffFormat.UNIFIED:
            raise ValueError("Only unified diff format is supported for application")
        
        original_lines = original.splitlines(keepends=True)
        result_lines = original_lines.copy()
        
        # Apply hunks in reverse order to maintain line numbers
        for hunk in reversed(diff.hunks):
            try:
                result_lines = self._apply_hunk(result_lines, hunk, strict)
            except DiffConflict as e:
                if strict:
                    raise
                else:
                    # Log the conflict but continue
                    print(f"Warning: Skipping conflicting hunk: {e}")
        
        return ''.join(result_lines)
    
    def _apply_hunk(
        self,
        lines: List[str],
        hunk: DiffHunk,
        strict: bool
    ) -> List[str]:
        """
        Apply a single hunk to the text.
        
        Args:
            lines: Current text lines
            hunk: Hunk to apply
            strict: Whether to enforce strict matching
            
        Returns:
            Modified lines after applying hunk
        """
        # Convert to 0-indexed
        start_line = hunk.original_start if hunk.original_count == 0 else hunk.original_start - 1
        
        # Extract expected original lines from hunk
        expected_lines = []
        new_lines = []
        
        for line in hunk.lines:
            if line.startswith(' '):
                # Context line (should match in both)
                expected_lines.append(line[1:])
                new_lines.append(line[1:])
            elif line.startswith('-'):
                # Line to be removed
                expected_lines.append(line[1:])
            elif line.startswith('+'):
                # Line to be added
                new_lines.append(line[1:])
        
        # Verify that the original lines match
        end_line = start_line + len(expected_lines)

        if strict and (len(expected_lines) != hunk.original_count or len(new_lines) != hunk.modified_count):
            raise DiffConflict("Hunk line counts do not match its header")
        if start_line < 0 or start_line > len(lines):
            raise DiffConflict("Hunk starts outside the original file")
        
        if end_line > len(lines):
            raise DiffConflict(
                f"Hunk extends beyond file end: expected {end_line} lines, "
                f"but file has only {len(lines)} lines"
            )
        
        actual_lines = lines[start_line:end_line]
        
        if strict:
            # Strict matching: lines must match exactly
            for i, (expected, actual) in enumerate(zip(expected_lines, actual_lines)):
                if expected != actual:
                    raise DiffConflict(
                        f"Line {start_line + i + 1} does not match expected content.\n"
                        f"Expected: {expected.rstrip()}\n"
                        f"Actual: {actual.rstrip()}"
                    )
        
        # Apply the change
        result = lines[:start_line] + new_lines + lines[end_line:]
        return result
    
    def parse_diff_string(self, diff_string: str) -> Diff:
        """
        Parse a diff string into a Diff object.
        
        Args:
            diff_string: String containing diff content
            
        Returns:
            Parsed Diff object
        """
        lines = diff_string.splitlines(keepends=True)
        
        # Detect format
        if any(line.startswith('@@') for line in lines):
            format = DiffFormat.UNIFIED
        elif any(line.startswith('***') for line in lines):
            format = DiffFormat.CONTEXT
        else:
            format = DiffFormat.NDIFF
        
        # Extract file names
        original_name = "original"
        modified_name = "modified"
        
        for line in lines[:10]:  # Check first 10 lines for headers
            if line.startswith('---'):
                original_name = line[4:].strip()
            elif line.startswith('+++'):
                modified_name = line[4:].strip()
        
        if format == DiffFormat.UNIFIED:
            hunks = self._parse_unified_diff(lines)
        else:
            # For other formats, store as single hunk
            hunks = [DiffHunk(
                original_start=1,
                original_count=0,
                modified_start=1,
                modified_count=0,
                lines=lines,
                header="Parsed Diff"
            )]
        
        return Diff(
            original_name=original_name,
            modified_name=modified_name,
            hunks=hunks,
            format=format
        )
    
    def get_diff_stats(self, diff: Diff) -> Dict[str, int]:
        """
        Get statistics about a diff.
        
        Args:
            diff: Diff object to analyze
            
        Returns:
            Dictionary with statistics (additions, deletions, changes)
        """
        additions = 0
        deletions = 0
        
        for hunk in diff.hunks:
            for line in hunk.lines:
                if line.startswith('+') and not line.startswith('+++'):
                    additions += 1
                elif line.startswith('-') and not line.startswith('---'):
                    deletions += 1
        
        return {
            'additions': additions,
            'deletions': deletions,
            'hunks': len(diff.hunks),
            'changes': additions + deletions
        }
    
    def add_to_history(self, original: str, modified: str):
        """
        Add a diff operation to history for undo/redo.
        
        Args:
            original: Original text
            modified: Modified text
        """
        # Remove any history after current index
        self._history = self._history[:self._current_index + 1]
        
        # Add new entry
        self._history.append((original, modified))
        self._current_index = len(self._history) - 1
    
    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self._current_index > 0
    
    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self._current_index < len(self._history) - 1
    
    def undo(self) -> Optional[str]:
        """
        Undo the last diff operation.
        
        Returns:
            The previous text state, or None if cannot undo
        """
        if not self.can_undo():
            return None
        
        self._current_index -= 1
        return self._history[self._current_index][1]
    
    def redo(self) -> Optional[str]:
        """
        Redo the next diff operation.
        
        Returns:
            The next text state, or None if cannot redo
        """
        if not self.can_redo():
            return None
        
        self._current_index += 1
        return self._history[self._current_index][1]
    
    def clear_history(self):
        """Clear the undo/redo history."""
        self._history.clear()
        self._current_index = -1
