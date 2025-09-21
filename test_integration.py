#!/usr/bin/env python3
"""
Integration test for bot startup and basic functionality
"""
import sys
import os
import asyncio

sys.path.insert(0, '.')

# Set environment variables for testing
os.environ['BOT_TOKEN'] = 'test_token'
os.environ['ADMIN_GROUP_ID'] = '-123456789'
os.environ['ADMIN_IDS'] = '123456789'

from db import get_stage_types, ensure_requisites_stages_for_all_banks, get_banks
from handlers.instruction_management import stage_type_select_handler
from handlers.admin_handlers import add_requisites_cmd


def test_imports():
    """Test that all modules can be imported without errors"""
    print("📦 Testing imports...")
    
    try:
        # Test main bot imports
        from client_bot import main
        print("✅ Main bot imports successful")
        
        # Test instruction management
        from handlers.instruction_management import (
            instructions_list_handler,
            instructions_add_handler,
            stage_type_select_handler,
            instruction_text_input_handler
        )
        print("✅ Instruction management imports successful")
        
        # Test admin handlers
        from handlers.admin_handlers import add_requisites_cmd
        print("✅ Admin handlers imports successful")
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    
    return True


def test_stage_types_consistency():
    """Test that stage types are consistent and complete"""
    print("🎭 Testing stage types consistency...")
    
    stage_types = get_stage_types()
    
    # Check all required fields
    required_fields = ['name', 'description', 'fields']
    for stage_type, info in stage_types.items():
        for field in required_fields:
            assert field in info, f"Stage type {stage_type} missing field {field}"
    
    # Check specific stage types exist
    required_types = ['text_screenshots', 'data_delivery', 'user_data_request', 'requisites_request']
    for req_type in required_types:
        assert req_type in stage_types, f"Missing required stage type: {req_type}"
    
    # Check new requisites type specifically
    requisites = stage_types['requisites_request']
    assert 'реквізитів' in requisites['name'].lower() or 'requisites' in requisites['name'].lower()
    assert len(requisites['description']) > 50, "Requisites description should be detailed"
    
    print("✅ Stage types consistency test passed")
    return True


def test_database_functions():
    """Test database functions work correctly"""
    print("🗄️ Testing database functions...")
    
    try:
        # Test stage types
        stage_types = get_stage_types()
        assert len(stage_types) >= 4, "Should have at least 4 stage types"
        
        # Test banks function
        banks = get_banks()
        print(f"Found {len(banks)} banks in database")
        
        # Test requisites addition (should not fail)
        added_count = ensure_requisites_stages_for_all_banks()
        print(f"Added {added_count} requisites stages")
        
        print("✅ Database functions test passed")
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


def test_ui_improvements():
    """Test that UI improvements are properly implemented"""
    print("🖥️ Testing UI improvements...")
    
    stage_types = get_stage_types()
    
    # Check improved descriptions
    for stage_type, info in stage_types.items():
        desc = info['description']
        assert len(desc) > 30, f"Stage {stage_type} description too short: {desc}"
        
        # Check that descriptions are more detailed
        if stage_type == 'requisites_request':
            assert 'фінальний' in desc.lower() or 'final' in desc.lower(), "Requisites should mention it's final"
        elif stage_type == 'data_delivery':
            assert 'менеджер' in desc.lower() or 'manager' in desc.lower(), "Data delivery should mention manager"
        elif stage_type == 'user_data_request':
            assert 'збор' in desc.lower() or 'збират' in desc.lower() or 'збір' in desc.lower(), f"User data request should mention collecting data, got: {desc}"
    
    print("✅ UI improvements test passed")
    return True


def run_integration_tests():
    """Run all integration tests"""
    print("🚀 Starting integration tests...\n")
    
    tests = [
        test_imports,
        test_stage_types_consistency,
        test_database_functions,
        test_ui_improvements,
    ]
    
    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ Test {test.__name__} failed")
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print(f"\n📊 Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All integration tests passed!")
        print("✅ Bot should start and work correctly")
        return True
    else:
        print("❌ Some integration tests failed")
        return False


if __name__ == "__main__":
    success = run_integration_tests()
    sys.exit(0 if success else 1)