"""
Unit tests for the DiffManager class.
"""

import pytest
from editing.diff_manager import (
    DiffManager, DiffFormat, DiffConflict, Diff, DiffHunk
)


class TestDiffManager:
    """Test suite for DiffManager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DiffManager()
        
        self.original_text = """Line 1
Line 2
Line 3
Line 4
Line 5
"""
        
        self.modified_text = """Line 1
Line 2 modified
Line 3
New Line 3.5
Line 4
Line 5
"""
    
    def test_generate_unified_diff(self):
        """Test generating a unified diff."""
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text,
            format=DiffFormat.UNIFIED
        )
        
        assert diff.format == DiffFormat.UNIFIED
        assert len(diff.hunks) > 0
        assert diff.original_name == "original"
        assert diff.modified_name == "modified"
    
    def test_generate_diff_with_custom_names(self):
        """Test generating diff with custom file names."""
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text,
            original_name="file_v1.txt",
            modified_name="file_v2.txt"
        )
        
        assert diff.original_name == "file_v1.txt"
        assert diff.modified_name == "file_v2.txt"
    
    def test_diff_to_string(self):
        """Test converting diff to string."""
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text
        )
        
        diff_str = str(diff)
        assert "---" in diff_str
        assert "+++" in diff_str
        assert "@@" in diff_str
    
    def test_apply_diff_simple(self):
        """Test applying a simple diff."""
        # Generate diff
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text
        )
        
        # Apply diff
        result = self.manager.apply_diff(self.original_text, diff)
        
        # Result should match modified text
        assert result == self.modified_text
    
    def test_apply_diff_with_additions(self):
        """Test applying diff with only additions."""
        original = "Line 1\nLine 2\n"
        modified = "Line 1\nLine 2\nLine 3\n"
        
        diff = self.manager.generate_diff(original, modified)
        result = self.manager.apply_diff(original, diff)
        
        assert result == modified
    
    def test_apply_diff_with_deletions(self):
        """Test applying diff with only deletions."""
        original = "Line 1\nLine 2\nLine 3\n"
        modified = "Line 1\nLine 3\n"
        
        diff = self.manager.generate_diff(original, modified)
        result = self.manager.apply_diff(original, diff)
        
        assert result == modified
    
    def test_apply_diff_conflict_strict(self):
        """Test that applying diff with conflicts raises exception in strict mode."""
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text
        )
        
        # Try to apply to different text
        different_text = "Completely different\ntext content\n"
        
        with pytest.raises(DiffConflict):
            self.manager.apply_diff(different_text, diff, strict=True)
    
    def test_apply_diff_conflict_non_strict(self):
        """Test that applying diff with conflicts doesn't raise in non-strict mode."""
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text
        )
        
        # Try to apply to different text
        different_text = "Completely different\ntext content\n"
        
        # Should not raise exception
        result = self.manager.apply_diff(different_text, diff, strict=False)
        assert result is not None
    
    def test_get_diff_stats(self):
        """Test getting diff statistics."""
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text
        )
        
        stats = self.manager.get_diff_stats(diff)
        
        assert 'additions' in stats
        assert 'deletions' in stats
        assert 'hunks' in stats
        assert 'changes' in stats
        assert stats['additions'] > 0
        assert stats['hunks'] > 0
    
    def test_parse_diff_string(self):
        """Test parsing a diff string."""
        # Generate a diff
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text
        )
        
        # Convert to string
        diff_str = str(diff)
        
        # Parse it back
        parsed_diff = self.manager.parse_diff_string(diff_str)
        
        assert parsed_diff.format == DiffFormat.UNIFIED
        assert len(parsed_diff.hunks) > 0
    
    def test_history_add(self):
        """Test adding to history."""
        self.manager.add_to_history(self.original_text, self.modified_text)
        
        assert len(self.manager._history) == 1
        assert self.manager._current_index == 0
    
    def test_undo_redo(self):
        """Test undo and redo functionality."""
        # Add some history
        text1 = "Version 1"
        text2 = "Version 2"
        text3 = "Version 3"
        
        self.manager.add_to_history(text1, text2)
        self.manager.add_to_history(text2, text3)
        
        # Test undo
        assert self.manager.can_undo()
        result = self.manager.undo()
        assert result == text2
        
        # Test redo
        assert self.manager.can_redo()
        result = self.manager.redo()
        assert result == text3
    
    def test_cannot_undo_at_start(self):
        """Test that undo is not available at start."""
        assert not self.manager.can_undo()
        assert self.manager.undo() is None
    
    def test_cannot_redo_at_end(self):
        """Test that redo is not available at end."""
        self.manager.add_to_history("v1", "v2")
        assert not self.manager.can_redo()
        assert self.manager.redo() is None
    
    def test_clear_history(self):
        """Test clearing history."""
        self.manager.add_to_history("v1", "v2")
        self.manager.add_to_history("v2", "v3")
        
        self.manager.clear_history()
        
        assert len(self.manager._history) == 0
        assert self.manager._current_index == -1
        assert not self.manager.can_undo()
        assert not self.manager.can_redo()
    
    def test_ndiff_format(self):
        """Test generating ndiff format."""
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text,
            format=DiffFormat.NDIFF
        )
        
        assert diff.format == DiffFormat.NDIFF
        assert len(diff.hunks) > 0
    
    def test_context_diff_format(self):
        """Test generating context diff format."""
        diff = self.manager.generate_diff(
            self.original_text,
            self.modified_text,
            format=DiffFormat.CONTEXT
        )
        
        assert diff.format == DiffFormat.CONTEXT
        assert len(diff.hunks) > 0
    
    def test_empty_diff(self):
        """Test generating diff for identical texts."""
        text = "Same text\n"
        
        diff = self.manager.generate_diff(text, text)
        
        # Should have no hunks for identical texts
        assert len(diff.hunks) == 0
    
    def test_multiline_changes(self):
        """Test diff with multiple separate changes."""
        original = """Line 1
Line 2
Line 3
Line 4
Line 5
Line 6
Line 7
Line 8
Line 9
Line 10
"""
        
        modified = """Line 1 changed
Line 2
Line 3
Line 4
Line 5 changed
Line 6
Line 7
Line 8
Line 9 changed
Line 10
"""
        
        diff = self.manager.generate_diff(original, modified)
        result = self.manager.apply_diff(original, diff)
        
        assert result == modified


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
