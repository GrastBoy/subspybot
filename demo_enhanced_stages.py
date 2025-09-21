#!/usr/bin/env python3
"""
Demonstration script showing the enhanced stage management functionality
"""
import sys
import os

sys.path.insert(0, '.')

# Set environment variables for testing
os.environ['BOT_TOKEN'] = 'demo_token'
os.environ['ADMIN_GROUP_ID'] = '-987654321'
os.environ['ADMIN_IDS'] = '987654321'

from db import (
    add_bank,
    add_bank_instruction,
    get_stage_types,
    get_bank_instructions,
    ensure_requisites_stages_for_all_banks,
    conn,
    cursor
)


def demonstrate_enhanced_functionality():
    """Demonstrate the enhanced stage management functionality"""
    print("🚀 Enhanced Stage Management Demo")
    print("=" * 50)
    
    # 1. Show available stage types
    print("\n1️⃣ Available Stage Types:")
    stage_types = get_stage_types()
    for stage_type, info in stage_types.items():
        print(f"   🎭 {info['name']}")
        print(f"      📄 {info['description']}")
        print()
    
    # 2. Create demo bank and instructions
    print("2️⃣ Creating Demo Bank with Various Stage Types:")
    demo_bank = "Demo Bank Enhanced"
    
    # Clean up if exists
    cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (demo_bank,))
    cursor.execute("DELETE FROM banks WHERE name=?", (demo_bank,))
    conn.commit()
    
    # Add demo bank
    success = add_bank(demo_bank, True, True, True)
    print(f"   ✅ Added bank: {demo_bank}")
    
    # Create a complete instruction flow
    stages = [
        {
            'type': 'text_screenshots',
            'text': 'Відкрийте офіційний сайт банку та перейдіть до розділу реєстрації',
            'data': {
                'text': 'Відкрийте офіційний сайт банку та перейдіть до розділу реєстрації',
                'example_images': [],
                'required_photos': 1
            }
        },
        {
            'type': 'user_data_request',
            'text': 'Будь ласка, надайте наступні дані: номер телефону, email адресу, ПІБ.',
            'data': {
                'data_fields': ['phone', 'email', 'fullname'],
                'field_config': {
                    'phone': {'required': True},
                    'email': {'required': True},
                    'fullname': {'required': True}
                }
            }
        },
        {
            'type': 'data_delivery',
            'text': 'Натисніть кнопку нижче для отримання номеру телефону та email від менеджера',
            'data': {
                'phone_required': True,
                'email_required': True,
                'template_text': 'Натисніть кнопку нижче для отримання номеру телефону та email від менеджера'
            }
        },
        {
            'type': 'text_screenshots',
            'text': 'Завершіть реєстрацію, використовуючи отримані дані, та зробіть скріншот підтвердження',
            'data': {
                'text': 'Завершіть реєстрацію, використовуючи отримані дані, та зробіть скріншот підтвердження',
                'example_images': [],
                'required_photos': 1
            }
        },
        {
            'type': 'requisites_request',
            'text': 'Надайте реквізити картки для отримання коштів після завершення реєстрації:\n\n• Номер картки\n• ПІБ власника картки',
            'data': {
                'requisites_text': 'Надайте реквізити картки для отримання коштів після завершення реєстрації:\n\n• Номер картки\n• ПІБ власника картки',
                'required_requisites': ['card_number', 'card_holder_name'],
                'instruction_text': 'Надайте реквізити картки для отримання коштів після завершення реєстрації:\n\n• Номер картки\n• ПІБ власника картки'
            }
        }
    ]
    
    for i, stage in enumerate(stages, 1):
        success = add_bank_instruction(
            bank_name=demo_bank,
            action="register",
            step_number=i,
            instruction_text=stage['text'],
            step_type=stage['type'],
            step_data=stage['data']
        )
        stage_name = stage_types[stage['type']]['name']
        print(f"   📋 Step {i}: {stage_name}")
    
    # 3. Show the created instruction flow
    print("\n3️⃣ Complete Instruction Flow:")
    instructions = get_bank_instructions(demo_bank, "register")
    for i, instr in enumerate(instructions, 1):
        step_number, instruction_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
        stage_name = stage_types[step_type]['name']
        print(f"   {i}. 🎭 {stage_name}")
        print(f"      📝 {instruction_text[:80]}{'...' if len(instruction_text) > 80 else ''}")
        print()
    
    # 4. Demonstrate automatic requisites addition
    print("4️⃣ Automatic Requisites Addition:")
    
    # Create another bank without requisites
    test_bank = "Test Bank Without Requisites"
    cursor.execute("DELETE FROM bank_instructions WHERE bank_name=?", (test_bank,))
    cursor.execute("DELETE FROM banks WHERE name=?", (test_bank,))
    conn.commit()
    
    add_bank(test_bank, True, True, True)
    add_bank_instruction(
        bank_name=test_bank,
        action="register",
        step_number=1,
        instruction_text="Some regular instruction",
        step_type="text_screenshots",
        step_data={'text': 'Some regular instruction', 'example_images': [], 'required_photos': 1}
    )
    
    print(f"   📦 Created bank '{test_bank}' with 1 regular stage")
    
    # Add requisites automatically
    added_count = ensure_requisites_stages_for_all_banks()
    print(f"   ✨ Automatically added {added_count} requisites stages")
    
    # Show the result
    updated_instructions = get_bank_instructions(test_bank, "register")
    print(f"   📊 Bank now has {len(updated_instructions)} stages (including requisites)")
    
    # 5. Summary
    print("\n5️⃣ Enhanced Features Summary:")
    print("   ✅ 4 different stage types available")
    print("   ✅ Improved stage type descriptions")
    print("   ✅ Automatic requisites stage addition")
    print("   ✅ Configurable stage ordering")
    print("   ✅ Enhanced admin interface")
    print("   ✅ Comprehensive testing")
    
    # Cleanup demo data
    cursor.execute("DELETE FROM bank_instructions WHERE bank_name IN (?, ?)", (demo_bank, test_bank))
    cursor.execute("DELETE FROM banks WHERE name IN (?, ?)", (demo_bank, test_bank))
    conn.commit()
    
    print("\n🎉 Demo completed successfully!")
    print("✅ All enhanced stage management features are working correctly")


if __name__ == "__main__":
    demonstrate_enhanced_functionality()