#!/usr/bin/env python3
"""
Comprehensive test suite for enhanced bot functionality
"""
import sys

sys.path.insert(0, '.')

import json

from db import (
    add_bank,
    add_bank_instruction,
    add_manager_group,
    check_data_uniqueness,
    conn,
    create_order_form,
    cursor,
    get_active_orders_for_group,
    get_bank_groups,
    get_bank_instructions,
    get_banks,
    record_data_usage,
    set_active_order_for_group,
    update_bank,
)


def test_bank_management():
    """Test bank management functionality"""
    print("🏦 Testing bank management...")

    # Clean up any existing test banks first
    test_banks = ["Test Bank Alpha", "Test Bank Beta"]
    for bank in test_banks:
        cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (bank,))
        cursor.execute("DELETE FROM banks WHERE name=?", (bank,))
    conn.commit()

    # Test adding banks
    assert add_bank("Test Bank Alpha", True, True), "Failed to add bank"
    assert add_bank("Test Bank Beta", True, False), "Failed to add bank with limited actions"
    assert not add_bank("Test Bank Alpha", True, True), "Should not allow duplicate banks"

    # Test updating banks
    assert update_bank("Test Bank Alpha", register_enabled=False), "Failed to update bank"

    # Test getting banks
    banks = get_banks()
    # Handle 11-column output (name, is_active, register_enabled, change_enabled, price, description, min_age, register_price, change_price, register_min_age, change_min_age)
    bank_names = [name for name, _, _, _, _, _, _, _, _, _, _ in banks]
    assert "Test Bank Alpha" in bank_names, "Bank not found in list"
    assert "Test Bank Beta" in bank_names, "Bank not found in list"

    print("✅ Bank management tests passed")

def test_instruction_management():
    """Test instruction management functionality"""
    print("📝 Testing instruction management...")

    # Add instructions
    assert add_bank_instruction("Test Bank Alpha", "register", 1, "Step 1 text", [], 18, 2), "Failed to add instruction"
    assert add_bank_instruction("Test Bank Alpha", "register", 2, "Step 2 text", [], None, 1), "Failed to add instruction"
    assert add_bank_instruction("Test Bank Alpha", "change", 1, "Change step 1", [], 21, None), "Failed to add change instruction"

    # Get instructions
    register_instructions = get_bank_instructions("Test Bank Alpha", "register")
    assert len(register_instructions) == 2, f"Expected 2 register instructions, got {len(register_instructions)}"

    change_instructions = get_bank_instructions("Test Bank Alpha", "change")
    assert len(change_instructions) == 1, f"Expected 1 change instruction, got {len(change_instructions)}"

    all_instructions = get_bank_instructions("Test Bank Alpha")
    assert len(all_instructions) == 3, f"Expected 3 total instructions, got {len(all_instructions)}"

    print("✅ Instruction management tests passed")

def test_data_uniqueness():
    """Test data uniqueness checking"""
    print("🔍 Testing data uniqueness...")

    # Clean up any existing test data first
    cursor.execute("DELETE FROM bank_data_usage WHERE phone_number='+380991234567' OR email='unique@test.com'")
    cursor.execute("DELETE FROM orders WHERE user_id=99999")
    conn.commit()

    # Create test order
    cursor.execute('INSERT INTO orders (user_id, username, bank, action, stage, status) VALUES (?, ?, ?, ?, ?, ?)',
                   (99999, 'uniquetest', 'Test Bank Alpha', 'register', 0, 'В обробці'))
    order_id = cursor.lastrowid
    conn.commit()

    # Test initial uniqueness
    phone_used, email_used = check_data_uniqueness("Test Bank Alpha", "+380991234567", "unique@test.com")
    assert not phone_used, "Phone should be unique initially"
    assert not email_used, "Email should be unique initially"

    # Record usage
    record_data_usage(order_id, "Test Bank Alpha", "+380991234567", "unique@test.com")

    # Test after recording
    phone_used, email_used = check_data_uniqueness("Test Bank Alpha", "+380991234567", "unique@test.com")
    assert phone_used, "Phone should be marked as used"
    assert email_used, "Email should be marked as used"

    # Test different bank (should be unique)
    phone_used, email_used = check_data_uniqueness("Test Bank Beta", "+380991234567", "unique@test.com")
    assert not phone_used, "Phone should be unique for different bank"
    assert not email_used, "Email should be unique for different bank"

    print("✅ Data uniqueness tests passed")

def test_group_management():
    """Test manager group management"""
    print("👥 Testing group management...")

    # Clean up any existing test groups first
    test_group_ids = [-1001111111111, -1001111111112, -1001111111113]
    for group_id in test_group_ids:
        cursor.execute("DELETE FROM manager_groups WHERE group_id=?", (group_id,))
    conn.commit()

    # Add different types of groups
    assert add_manager_group(-1001111111111, "Alpha Bank Group", "Test Bank Alpha", False), "Failed to add bank group"
    assert add_manager_group(-1001111111112, "Beta Bank Group", "Test Bank Beta", False), "Failed to add bank group"
    assert add_manager_group(-1001111111113, "Admin Group", None, True), "Failed to add admin group"

    # Test getting groups
    alpha_groups = get_bank_groups("Test Bank Alpha")
    assert len(alpha_groups) >= 1, "Should have at least one group for Alpha bank"

    all_groups = get_bank_groups()
    assert len(all_groups) >= 3, "Should have at least 3 groups total"

    print("✅ Group management tests passed")

def test_multi_order_management():
    """Test multi-order management"""
    print("📋 Testing multi-order management...")

    # Create test orders
    cursor.execute('INSERT INTO orders (user_id, username, bank, action, stage, status) VALUES (?, ?, ?, ?, ?, ?)',
                   (88888, 'multitest1', 'Test Bank Alpha', 'register', 0, 'В обробці'))
    order_id1 = cursor.lastrowid

    cursor.execute('INSERT INTO orders (user_id, username, bank, action, stage, status) VALUES (?, ?, ?, ?, ?, ?)',
                   (88889, 'multitest2', 'Test Bank Alpha', 'change', 0, 'В обробці'))
    order_id2 = cursor.lastrowid

    conn.commit()

    group_id = -1001111111111

    # Set active orders
    set_active_order_for_group(group_id, order_id1, True)  # Primary
    set_active_order_for_group(group_id, order_id2, False)  # Secondary

    # Get active orders
    active_orders = get_active_orders_for_group(group_id)
    assert len(active_orders) == 2, f"Expected 2 active orders, got {len(active_orders)}"

    # Check primary order
    primary_orders = [order for order in active_orders if order[1] == 1]  # is_primary = 1
    assert len(primary_orders) == 1, "Should have exactly one primary order"
    assert primary_orders[0][0] == order_id1, "Wrong primary order"

    print("✅ Multi-order management tests passed")

def test_order_forms():
    """Test order form generation"""
    print("📄 Testing order form generation...")

    # Create test order
    cursor.execute('INSERT INTO orders (user_id, username, bank, action, stage, status) VALUES (?, ?, ?, ?, ?, ?)',
                   (77777, 'formtest', 'Test Bank Alpha', 'register', 0, 'Завершено'))
    order_id = cursor.lastrowid
    conn.commit()

    # Create form data
    form_data = {
        "order_id": order_id,
        "user_data": {"user_id": 77777, "username": "formtest"},
        "bank": "Test Bank Alpha",
        "action": "register",
        "manager_data": {"phone_number": "+380501111111", "email": "form@test.com"},
        "photos": [{"stage": 0, "file_id": "test_file_id"}],
        "status": "Завершено"
    }

    # Create order form
    create_order_form(order_id, form_data)

    # Verify form was created
    cursor.execute("SELECT form_data FROM order_forms WHERE order_id = ?", (order_id,))
    result = cursor.fetchone()
    assert result, "Order form was not created"

    stored_data = json.loads(result[0])
    assert stored_data["order_id"] == order_id, "Order ID mismatch in form"
    assert stored_data["bank"] == "Test Bank Alpha", "Bank mismatch in form"

    print("✅ Order form tests passed")

def test_edge_cases():
    """Test edge cases and error handling"""
    print("⚠️ Testing edge cases...")

    # Test non-existent bank
    phone_used, email_used = check_data_uniqueness("Non Existent Bank", "+380999999999", "fake@test.com")
    assert not phone_used and not email_used, "Non-existent bank should return False for uniqueness"

    # Test empty data
    phone_used, email_used = check_data_uniqueness("Test Bank Alpha", None, None)
    assert not phone_used and not email_used, "Empty data should return False"

    # Test invalid group operations
    active_orders = get_active_orders_for_group(-999999999)
    assert len(active_orders) == 0, "Non-existent group should return empty list"

    print("✅ Edge case tests passed")

def test_admin_interface():
    """Test unified admin interface functionality"""
    print("🔧 Testing unified admin interface...")

    try:
        from handlers.admin_interface import admin_interface_callback, admin_interface_menu
        print("✅ Admin interface modules imported successfully")

        # Test that interface has proper structure
        assert admin_interface_menu.__doc__ is not None, "admin_interface_menu should have documentation"
        assert admin_interface_callback.__doc__ is not None, "admin_interface_callback should have documentation"

        print("✅ Admin interface structure tests passed")

    except Exception as e:
        print(f"❌ Admin interface test failed: {e}")
        raise

def run_all_tests():
    """Run all tests"""
    print("🚀 Starting comprehensive test suite...\n")

    try:
        test_bank_management()
        test_instruction_management()
        test_data_uniqueness()
        test_group_management()
        test_multi_order_management()
        test_order_forms()
        test_edge_cases()
        test_admin_interface()

        # Cleanup test data
        cleanup_test_data()

        print("\n🎉 All tests passed successfully!")
        print("✅ Enhanced bot functionality is working correctly")
        print("✅ Unified admin interface is properly integrated")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        # Cleanup on failure too
        cleanup_test_data()


def cleanup_test_data():
    """Clean up all test data"""
    test_banks = ["Test Bank Alpha", "Test Bank Beta"]
    for bank in test_banks:
        cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (bank,))
        cursor.execute("DELETE FROM banks WHERE name=?", (bank,))
    
    # Clean up test orders and related data
    test_user_ids = [77777, 88888, 88889, 99999]
    for user_id in test_user_ids:
        cursor.execute("DELETE FROM orders WHERE user_id=?", (user_id,))
        cursor.execute("DELETE FROM bank_data_usage WHERE order_id IN (SELECT id FROM orders WHERE user_id=?)", (user_id,))
    
    # Clean up test data usage
    cursor.execute("DELETE FROM bank_data_usage WHERE phone_number IN ('+380501234567', '+380991234567') OR email IN ('test@example.com', 'unique@test.com')")
    
    # Clean up test groups
    test_group_ids = [-1001111111111, -1001111111112, -1001111111113]
    for group_id in test_group_ids:
        cursor.execute("DELETE FROM manager_groups WHERE group_id=?", (group_id,))
    
    conn.commit()


def run_all_tests():
    """Run all tests"""
    try:
        test_bank_management()
        test_instruction_management()
        test_data_uniqueness()
        test_group_management()
        test_multi_order_management()
        test_order_forms()
        test_edge_cases()
        test_admin_interface()

        # Cleanup test data
        cleanup_test_data()

        print("\n🎉 All tests passed successfully!")
        print("✅ Enhanced bot functionality is working correctly")
        print("✅ Unified admin interface is properly integrated")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        # Cleanup on failure too
        cleanup_test_data()
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
