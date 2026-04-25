"""
Simple test script for DiffManager without pytest dependency.
"""

import sys
sys.path.insert(0, '/home/sasa/Desktop/Projects/sammyai_v1')

from editing.diff_manager import DiffManager, DiffFormat, DiffConflict


def test_basic_diff():
    """Test basic diff generation and application."""
    print("Testing basic diff generation and application...")
    
    manager = DiffManager()
    
    original = """Line 1
Line 2
Line 3
Line 4
Line 5
"""
    
    modified = """Line 1
Line 2 modified
Line 3
New Line 3.5
Line 4
Line 5
"""
    
    # Generate diff
    diff = manager.generate_diff(original, modified)
    print(f"✓ Generated diff with {len(diff.hunks)} hunks")
    
    # Apply diff
    result = manager.apply_diff(original, diff)
    
    # Verify
    if result == modified:
        print("✓ Diff applied successfully - result matches modified text")
        return True
    else:
        print("✗ FAILED - result does not match modified text")
        return False


def test_diff_stats():
    """Test diff statistics."""
    print("\nTesting diff statistics...")
    
    manager = DiffManager()
    
    original = "Line 1\nLine 2\nLine 3\n"
    modified = "Line 1\nLine 2 changed\nLine 3\nLine 4\n"
    
    diff = manager.generate_diff(original, modified)
    stats = manager.get_diff_stats(diff)
    
    print(f"✓ Stats: {stats['additions']} additions, {stats['deletions']} deletions, {stats['hunks']} hunks")
    
    if stats['additions'] > 0 and stats['hunks'] > 0:
        print("✓ Statistics are correct")
        return True
    else:
        print("✗ FAILED - statistics are incorrect")
        return False


def test_history():
    """Test undo/redo history."""
    print("\nTesting undo/redo history...")
    
    manager = DiffManager()
    
    text1 = "Version 1"
    text2 = "Version 2"
    text3 = "Version 3"
    
    manager.add_to_history(text1, text2)
    manager.add_to_history(text2, text3)
    
    # Test undo
    if manager.can_undo():
        result = manager.undo()
        if result == text2:
            print("✓ Undo works correctly")
        else:
            print("✗ FAILED - undo returned wrong text")
            return False
    else:
        print("✗ FAILED - cannot undo")
        return False
    
    # Test redo
    if manager.can_redo():
        result = manager.redo()
        if result == text3:
            print("✓ Redo works correctly")
            return True
        else:
            print("✗ FAILED - redo returned wrong text")
            return False
    else:
        print("✗ FAILED - cannot redo")
        return False


def test_conflict_detection():
    """Test conflict detection."""
    print("\nTesting conflict detection...")
    
    manager = DiffManager()
    
    original = "Line 1\nLine 2\nLine 3\n"
    modified = "Line 1\nLine 2 changed\nLine 3\n"
    
    diff = manager.generate_diff(original, modified)
    
    # Try to apply to different text
    different = "Completely different\ntext\n"
    
    try:
        manager.apply_diff(different, diff, strict=True)
        print("✗ FAILED - should have raised DiffConflict")
        return False
    except DiffConflict:
        print("✓ Conflict detection works correctly")
        return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("DiffManager Test Suite")
    print("=" * 60)
    
    tests = [
        test_basic_diff,
        test_diff_stats,
        test_history,
        test_conflict_detection
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
