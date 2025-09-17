#!/usr/bin/env python3
"""
Test suite for dynamic instruction functionality
"""
import sys
import os
import tempfile
import sqlite3

sys.path.insert(0, '.')

def test_dynamic_instructions():
    """Test the dynamic instruction service"""
    print("🧪 Testing dynamic instruction service...")
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
        test_db_path = tmp_db.name
    
    # Set the test database
    os.environ['DB_FILE'] = test_db_path
    
    try:
        # Import after setting the environment variable
        from db import add_bank, add_bank_instruction, ensure_schema
        from services.instructions import get_instructions, find_age_requirement, get_required_photos, get_banks_for_action
        from states import get_instructions as states_get_instructions, get_banks_for_action as states_get_banks
        
        # Initialize test database
        ensure_schema()
        
        # Test 1: Empty database
        print("  ✓ Testing empty database...")
        instructions = get_instructions()
        assert len(instructions) == 0, "Empty database should return empty instructions"
        assert get_banks_for_action("register") == [], "Empty database should return no banks"
        
        # Test 2: Add test data
        print("  ✓ Adding test data...")
        assert add_bank("Test Bank", True, True, "100", "Test description"), "Should add bank successfully"
        assert add_bank("Inactive Bank", True, True, "100", "Inactive bank") and True, "Should add inactive bank"
        
        # Make one bank inactive
        from db import update_bank
        assert update_bank("Inactive Bank", is_active=False), "Should deactivate bank"
        
        # Add instructions
        assert add_bank_instruction("Test Bank", "register", 1, "Step 1 text", ["img1.jpg"], 18, 2), "Should add register instruction"
        assert add_bank_instruction("Test Bank", "register", 2, "Step 2 text", [], None, 1), "Should add second register instruction"
        assert add_bank_instruction("Test Bank", "change", 1, "Change step 1", ["img2.jpg"], 21, 3), "Should add change instruction"
        assert add_bank_instruction("Inactive Bank", "register", 1, "Inactive step", [], 18, 1), "Should add instruction to inactive bank"
        
        # Test 3: Get instructions
        print("  ✓ Testing instruction retrieval...")
        instructions = get_instructions()
        assert len(instructions) == 1, f"Should return 1 active bank, got {len(instructions)}"
        assert "Test Bank" in instructions, "Should include Test Bank"
        assert "Inactive Bank" not in instructions, "Should not include inactive bank"
        
        # Test bank actions
        test_bank = instructions["Test Bank"]
        assert "register" in test_bank, "Should have register action"
        assert "change" in test_bank, "Should have change action"
        assert len(test_bank["register"]) == 2, "Should have 2 register steps"
        assert len(test_bank["change"]) == 1, "Should have 1 change step"
        
        # Test step content
        register_step1 = test_bank["register"][0]
        assert register_step1["text"] == "Step 1 text", "Should have correct text"
        assert register_step1["images"] == ["img1.jpg"], "Should have correct images"
        assert register_step1["age"] == 18, "Should have correct age"
        assert register_step1["required_photos"] == 2, "Should have correct required_photos"
        
        # Test 4: Helper functions
        print("  ✓ Testing helper functions...")
        assert get_banks_for_action("register") == ["Test Bank"], "Should return banks for register"
        assert get_banks_for_action("change") == ["Test Bank"], "Should return banks for change"
        assert get_banks_for_action("nonexistent") == [], "Should return empty for nonexistent action"
        
        assert find_age_requirement("Test Bank", "register") == 18, "Should find register age requirement"
        assert find_age_requirement("Test Bank", "change") == 21, "Should find change age requirement"
        assert find_age_requirement("Nonexistent Bank", "register") is None, "Should return None for nonexistent bank"
        
        assert get_required_photos("Test Bank", "register", 0) == 2, "Should get required photos for step 0"
        assert get_required_photos("Test Bank", "register", 1) == 1, "Should get required photos for step 1"
        assert get_required_photos("Test Bank", "register", 2) is None, "Should return None for nonexistent step"
        
        # Test 5: States module integration
        print("  ✓ Testing states module integration...")
        states_instructions = states_get_instructions()
        assert len(states_instructions) == 1, "States should return same instructions"
        assert states_get_banks("register") == ["Test Bank"], "States should return same banks"
        
        print("✅ All dynamic instruction tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up test database
        try:
            os.unlink(test_db_path)
        except:
            pass
    
    return True

def test_backward_compatibility():
    """Test fallback to static instructions.py"""
    print("🧪 Testing backward compatibility...")
    
    try:
        # Temporarily move services to simulate missing module
        import shutil
        if os.path.exists('services'):
            shutil.move('services', 'services_temp')
        
        # Clear module cache
        if 'states' in sys.modules:
            del sys.modules['states']
        if 'services.instructions' in sys.modules:
            del sys.modules['services.instructions']
        
        # Import states which should fallback to static instructions
        from states import get_instructions, get_banks_for_action, find_age_requirement
        
        # Test fallback functionality
        instructions = get_instructions()
        assert len(instructions) > 0, "Should fallback to static instructions"
        
        banks_register = get_banks_for_action("register")
        assert len(banks_register) > 0, "Should return banks from static file"
        
        # Test specific banks from static file
        assert "ПУМБ" in instructions, "Should include ПУМБ from static file"
        age_req = find_age_requirement("ПУМБ", "register")
        assert age_req == 18, f"Should find ПУМБ age requirement, got {age_req}"
        
        print("✅ Backward compatibility test passed!")
        
    except Exception as e:
        print(f"❌ Backward compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Restore services directory
        if os.path.exists('services_temp'):
            if os.path.exists('services'):
                shutil.rmtree('services')
            shutil.move('services_temp', 'services')
    
    return True

if __name__ == "__main__":
    print("🚀 Testing dynamic instruction refactor...")
    
    success = True
    success &= test_dynamic_instructions()
    success &= test_backward_compatibility()
    
    if success:
        print("\n🎉 All tests passed! Dynamic instruction refactor is working correctly.")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)