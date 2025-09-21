#!/usr/bin/env python3
"""
Test suite for enhanced stage management functionality
"""
import sys
import os

sys.path.insert(0, '.')

from db import (
    add_bank,
    add_bank_instruction,
    get_stage_types,
    get_bank_instructions,
    get_next_step_number,
    reorder_bank_instructions,
    delete_bank_instruction,
    conn,
    cursor
)


def test_stage_types():
    """Test the new stage types including requisites"""
    print("🎭 Testing stage types...")
    
    stage_types = get_stage_types()
    
    # Check all required stage types exist
    required_types = ['text_screenshots', 'data_delivery', 'user_data_request', 'requisites_request']
    for stage_type in required_types:
        assert stage_type in stage_types, f"Missing stage type: {stage_type}"
        assert 'name' in stage_types[stage_type], f"Stage type {stage_type} missing name"
        assert 'description' in stage_types[stage_type], f"Stage type {stage_type} missing description"
        assert 'fields' in stage_types[stage_type], f"Stage type {stage_type} missing fields"
    
    # Check the new requisites stage specifically
    requisites = stage_types['requisites_request']
    assert 'реквізитів' in requisites['name'].lower(), "Requisites stage name incorrect"
    assert 'фінальний' in requisites['description'].lower(), "Requisites stage description should mention it's final"
    
    print("✅ Stage types test passed")


def test_stage_creation():
    """Test creating stages of different types"""
    print("📝 Testing stage creation...")
    
    # Create test bank if it doesn't exist
    test_bank = "Test Stage Bank"
    cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (test_bank,))
    cursor.execute("DELETE FROM banks WHERE name=?", (test_bank,))
    conn.commit()
    
    # Add test bank
    success = add_bank(test_bank, True, True, True)
    assert success, "Failed to add test bank"
    
    # Test creating different stage types
    test_cases = [
        {
            'type': 'text_screenshots',
            'text': 'Зробіть скріншот головної сторінки',
            'data': {'text': 'Зробіть скріншот головної сторінки', 'example_images': [], 'required_photos': 1}
        },
        {
            'type': 'data_delivery',
            'text': 'Запросіть у менеджера номер телефону та email для отримання кодів.',
            'data': {'phone_required': True, 'email_required': True, 'template_text': 'Запросіть у менеджера номер телефону та email для отримання кодів.'}
        },
        {
            'type': 'user_data_request',
            'text': 'Будь ласка, надайте наступні дані: номер телефону, email адресу.',
            'data': {'data_fields': ['phone', 'email'], 'field_config': {'phone': {'required': True}, 'email': {'required': True}}}
        },
        {
            'type': 'requisites_request',
            'text': 'Надайте реквізити карти для отримання коштів після реєстрації',
            'data': {'requisites_text': 'Надайте реквізити карти для отримання коштів після реєстрації', 'required_requisites': ['card_number', 'card_holder_name'], 'instruction_text': 'Надайте реквізити карти для отримання коштів після реєстрації'}
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        success = add_bank_instruction(
            bank_name=test_bank,
            action="register",
            step_number=i,
            instruction_text=test_case['text'],
            step_type=test_case['type'],
            step_data=test_case['data']
        )
        assert success, f"Failed to create {test_case['type']} stage"
    
    # Verify stages were created
    instructions = get_bank_instructions(test_bank, "register")
    assert len(instructions) == 4, f"Expected 4 instructions, got {len(instructions)}"
    
    print("✅ Stage creation test passed")


def test_stage_ordering():
    """Test stage reordering functionality"""
    print("🔄 Testing stage ordering...")
    
    test_bank = "Test Stage Bank"
    
    # Get current instructions
    instructions = get_bank_instructions(test_bank, "register")
    assert len(instructions) >= 3, "Need at least 3 stages to test reordering"
    
    # Extract step numbers in current order
    original_order = [instr[0] for instr in instructions]  # step_number is first element
    
    # Create new order (reverse the first 3)
    if len(original_order) >= 3:
        new_order = [original_order[2], original_order[1], original_order[0]] + original_order[3:]
    else:
        new_order = list(reversed(original_order))
    
    # Reorder stages
    success = reorder_bank_instructions(test_bank, "register", new_order)
    assert success, "Failed to reorder instructions"
    
    # Verify new order
    reordered_instructions = get_bank_instructions(test_bank, "register")
    reordered_step_numbers = [instr[0] for instr in reordered_instructions]
    
    assert reordered_step_numbers == new_order, f"Reordering failed: expected {new_order}, got {reordered_step_numbers}"
    
    print("✅ Stage ordering test passed")


def test_next_step_number():
    """Test getting next step number"""
    print("🔢 Testing next step number generation...")
    
    test_bank = "Test Stage Bank"
    
    # Get next step number
    next_step = get_next_step_number(test_bank, "register")
    
    # Should be higher than current max
    instructions = get_bank_instructions(test_bank, "register")
    if instructions:
        max_step = max(instr[0] for instr in instructions)  # step_number is first element
        assert next_step > max_step, f"Next step {next_step} should be > max step {max_step}"
    else:
        assert next_step == 1, f"Next step should be 1 for empty bank, got {next_step}"
    
    print("✅ Next step number test passed")


def test_stage_requisites_logic():
    """Test that requisites stage can be used as final stage"""
    print("💰 Testing requisites stage logic...")
    
    test_bank = "Test Requisites Bank"
    cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (test_bank,))
    cursor.execute("DELETE FROM banks WHERE name=?", (test_bank,))
    conn.commit()
    
    # Add test bank
    success = add_bank(test_bank, True, True, True)
    assert success, "Failed to add test bank"
    
    # Create a typical instruction flow with requisites as final stage
    stages = [
        {'type': 'text_screenshots', 'text': 'Перейдіть на сайт банку'},
        {'type': 'user_data_request', 'text': 'Введіть ваші дані'},
        {'type': 'data_delivery', 'text': 'Отримайте коди від менеджера'},
        {'type': 'text_screenshots', 'text': 'Завершіть реєстрацію'},
        {'type': 'requisites_request', 'text': 'Надайте реквізити для переказу коштів'}
    ]
    
    for i, stage in enumerate(stages, 1):
        step_data = {}
        if stage['type'] == 'requisites_request':
            step_data = {
                'requisites_text': stage['text'],
                'required_requisites': ['card_number', 'card_holder_name'],
                'instruction_text': stage['text']
            }
        elif stage['type'] == 'user_data_request':
            step_data = {
                'data_fields': ['phone', 'email'],
                'field_config': {'phone': {'required': True}, 'email': {'required': True}}
            }
        elif stage['type'] == 'data_delivery':
            step_data = {
                'phone_required': True,
                'email_required': True,
                'template_text': stage['text']
            }
        else:  # text_screenshots
            step_data = {
                'text': stage['text'],
                'example_images': [],
                'required_photos': 1
            }
        
        success = add_bank_instruction(
            bank_name=test_bank,
            action="register",
            step_number=i,
            instruction_text=stage['text'],
            step_type=stage['type'],
            step_data=step_data
        )
        assert success, f"Failed to create stage {i}: {stage['type']}"
    
    # Verify all stages were created
    instructions = get_bank_instructions(test_bank, "register")
    assert len(instructions) == 5, f"Expected 5 instructions, got {len(instructions)}"
    
    # Verify last stage is requisites
    last_instruction = instructions[-1]
    assert last_instruction[5] == 'requisites_request', "Last stage should be requisites_request"
    
    print("✅ Requisites stage logic test passed")


def cleanup_test_data():
    """Clean up test data"""
    print("🧹 Cleaning up test data...")
    
    test_banks = ["Test Stage Bank", "Test Requisites Bank"]
    for bank in test_banks:
        cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (bank,))
        cursor.execute("DELETE FROM banks WHERE name=?", (bank,))
    
    conn.commit()
    print("✅ Cleanup completed")


def test_auto_requisites_addition():
    """Test automatic addition of requisites stages to all banks"""
    print("🏦 Testing automatic requisites addition...")
    
    # Create test banks without requisites
    test_banks = ["Auto Test Bank 1", "Auto Test Bank 2"]
    
    for bank in test_banks:
        cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (bank,))
        cursor.execute("DELETE FROM banks WHERE name=?", (bank,))
        conn.commit()
        
        # Add test bank
        success = add_bank(bank, True, True, True)
        assert success, f"Failed to add test bank {bank}"
        
        # Add a regular stage first
        success = add_bank_instruction(
            bank_name=bank,
            action="register",
            step_number=1,
            instruction_text="Test instruction",
            step_type="text_screenshots",
            step_data={'text': 'Test instruction', 'example_images': [], 'required_photos': 1}
        )
        assert success, f"Failed to add instruction to {bank}"
    
    # Now test the automatic requisites addition
    from db import ensure_requisites_stages_for_all_banks
    added_count = ensure_requisites_stages_for_all_banks()
    
    # Should have added requisites for each bank (register action)
    assert added_count >= 2, f"Expected at least 2 requisites stages added, got {added_count}"
    
    # Verify each bank now has requisites stage
    for bank in test_banks:
        instructions = get_bank_instructions(bank, "register")
        requisites_stages = [instr for instr in instructions if instr[5] == 'requisites_request']  # step_type is index 5
        assert len(requisites_stages) > 0, f"Bank {bank} should have requisites stage"
    
    # Test that running it again doesn't duplicate
    added_count_2 = ensure_requisites_stages_for_all_banks()
    assert added_count_2 == 0, f"Second run should add 0 stages, got {added_count_2}"
    
    # Cleanup
    for bank in test_banks:
        cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (bank,))
        cursor.execute("DELETE FROM banks WHERE name=?", (bank,))
    conn.commit()
    
    print("✅ Automatic requisites addition test passed")


def run_all_tests():
    """Run all stage management tests"""
    try:
        test_stage_types()
        test_stage_creation()
        test_stage_ordering()
        test_next_step_number()
        test_stage_requisites_logic()
        test_auto_requisites_addition()
        cleanup_test_data()
        
        print("\n🎉 All stage management tests passed!")
        print("✅ Enhanced stage management functionality is working correctly")
        return True
    
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        cleanup_test_data()
        return False


if __name__ == "__main__":
    print("🚀 Starting stage management test suite...\n")
    success = run_all_tests()
    sys.exit(0 if success else 1)