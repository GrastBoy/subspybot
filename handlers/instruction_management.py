"""
Instruction management handlers for dynamic bank instruction management
"""
import json
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from db import (
    add_bank_instruction, get_bank_instructions, get_banks, is_admin, log_action,
    get_stage_types, update_bank_instruction, delete_bank_instruction, 
    reorder_bank_instructions, get_next_step_number, get_instruction_by_id,
    get_instruction_by_step
)

logger = logging.getLogger(__name__)

def _iter_banks_basic():
    """Helper to yield (name, is_active, register_enabled, change_enabled) from get_banks()"""
    banks = get_banks()
    for bank_row in banks:
        # get_banks() returns (name, is_active, register_enabled, change_enabled, price, description, min_age)
        # We only need the first 4 columns
        yield bank_row[:4]

# Conversation states for enhanced instruction management
INSTR_BANK_SELECT, INSTR_ACTION_SELECT, INSTR_STAGE_TYPE_SELECT, INSTR_STAGE_CONFIG, INSTR_TEXT_INPUT = range(10, 15)
INSTR_EDIT_SELECT, INSTR_EDIT_FIELD, INSTR_REORDER_SELECT = range(15, 18)

async def instructions_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all instructions for all banks with enhanced stage information"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    banks = list(_iter_banks_basic())

    if not banks:
        text = "📝 <b>Інструкції банків</b>\n\n❌ Немає зареєстрованих банків"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="instructions_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return

    text = "📝 <b>Інструкції банків</b>\n\n"
    stage_types = get_stage_types()

    for bank_name, is_active, register_enabled, change_enabled in banks:
        text += f"🏦 <b>{bank_name}</b>\n"

        # Get instructions for this bank
        register_instructions = get_bank_instructions(bank_name, "register")
        change_instructions = get_bank_instructions(bank_name, "change")

        if register_enabled and register_instructions:
            text += f"   📝 <b>Реєстрація:</b> {len(register_instructions)} етапів\n"
            # Show first 3 stages with types
            for i, instr in enumerate(register_instructions[:3]):
                step_number, instruction_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
                stage_name = stage_types.get(step_type, {}).get('name', step_type)
                text += f"      {step_order}. {stage_name}\n"
            if len(register_instructions) > 3:
                text += f"      ... та ще {len(register_instructions) - 3} етапів\n"
        elif register_enabled:
            text += "   📝 <b>Реєстрація:</b> ❌ Немає етапів\n"

        if change_enabled and change_instructions:
            text += f"   🔄 <b>Перев'язка:</b> {len(change_instructions)} етапів\n"
            # Show first 3 stages with types
            for i, instr in enumerate(change_instructions[:3]):
                step_number, instruction_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
                stage_name = stage_types.get(step_type, {}).get('name', step_type)
                text += f"      {step_order}. {stage_name}\n"
            if len(change_instructions) > 3:
                text += f"      ... та ще {len(change_instructions) - 3} етапів\n"
        elif change_enabled:
            text += "   🔄 <b>Перев'язка:</b> ❌ Немає етапів\n"

        text += "\n"

    keyboard = [
        [InlineKeyboardButton("➕ Додати етап", callback_data="instructions_add")],
        [InlineKeyboardButton("✏️ Редагувати етапи", callback_data="instructions_edit")],
        [InlineKeyboardButton("🔄 Змінити порядок", callback_data="instructions_reorder")],
        [InlineKeyboardButton("🔙 Назад", callback_data="instructions_menu")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def instructions_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding instruction stage conversation"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    banks = list(_iter_banks_basic())

    if not banks:
        text = "❌ Спочатку потрібно додати банки"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="instructions_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    text = "🏦 <b>Виберіть банк для додавання етапу:</b>\n\n"
    keyboard = []

    for bank_name, is_active, register_enabled, change_enabled in banks:
        if is_active:
            keyboard.append([InlineKeyboardButton(bank_name, callback_data=f"instr_bank_{bank_name}")])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="instructions_menu")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return INSTR_BANK_SELECT

async def instruction_bank_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bank selection for instruction"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("instr_bank_"):
        return ConversationHandler.END

    bank_name = data[11:]  # Remove "instr_bank_" prefix
    context.user_data['instr_bank'] = bank_name

    text = f"🔄 <b>Виберіть тип операції для '{bank_name}':</b>\n\n"
    keyboard = [
        [InlineKeyboardButton("📝 Реєстрація", callback_data="instr_action_register")],
        [InlineKeyboardButton("🔄 Перев'язка", callback_data="instr_action_change")],
        [InlineKeyboardButton("🔙 Назад", callback_data="instructions_add")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return INSTR_ACTION_SELECT

async def instruction_action_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle action selection and move to stage type selection"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("instr_action_"):
        return ConversationHandler.END

    action = data[13:]  # Remove "instr_action_" prefix
    bank_name = context.user_data.get('instr_bank')

    if not bank_name:
        await query.edit_message_text("❌ Помилка: банк не вибрано")
        return ConversationHandler.END

    context.user_data['instr_action'] = action

    # Get next step number
    next_step = get_next_step_number(bank_name, action)
    context.user_data['instr_step'] = next_step

    action_text = "Реєстрації" if action == "register" else "Перев'язки"
    
    # Show stage type selection
    stage_types = get_stage_types()
    
    text = "🎭 <b>Оберіть тип етапу</b>\n\n"
    text += f"🏦 Банк: {bank_name}\n"
    text += f"🔄 Тип операції: {action_text}\n"
    text += f"📋 Етап: {next_step}\n\n"
    text += "Доступні типи етапів:\n\n"

    keyboard = []
    for stage_type, info in stage_types.items():
        text += f"<b>{info['name']}</b>\n{info['description']}\n\n"
        keyboard.append([InlineKeyboardButton(info['name'], callback_data=f"stage_type_{stage_type}")])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="instr_bank_" + bank_name)])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return INSTR_STAGE_TYPE_SELECT

async def stage_type_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stage type selection and show appropriate configuration"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("stage_type_"):
        return ConversationHandler.END

    stage_type = data[11:]  # Remove "stage_type_" prefix
    
    bank_name = context.user_data.get('instr_bank')
    action = context.user_data.get('instr_action')
    step = context.user_data.get('instr_step')

    if not all([bank_name, action, step]):
        await query.edit_message_text("❌ Помилка: відсутні дані. Почніть заново.")
        return ConversationHandler.END

    context.user_data['instr_stage_type'] = stage_type
    
    stage_types = get_stage_types()
    stage_info = stage_types.get(stage_type, {})
    
    action_text = "Реєстрації" if action == "register" else "Перев'язки"

    # Configure stage based on type
    if stage_type == 'text_screenshots':
        text = "📝 <b>Налаштування етапу 'Текст + скріни'</b>\n\n"
        text += f"🏦 Банк: {bank_name}\n"
        text += f"🔄 Операція: {action_text}\n"
        text += f"📋 Етап: {step}\n\n"
        text += "Введіть текст інструкції для користувача:"
        
        await query.edit_message_text(text, parse_mode='HTML')
        return INSTR_TEXT_INPUT
        
    elif stage_type == 'data_delivery':
        # Create default data delivery stage
        step_data = {
            'phone_required': True,
            'email_required': True,
            'template_text': 'Запросіть у менеджера номер телефону та email для отримання кодів.'
        }
        
        success = add_bank_instruction(
            bank_name=bank_name,
            action=action,
            step_number=step,
            instruction_text=step_data['template_text'],
            step_type=stage_type,
            step_data=step_data
        )
        
        if success:
            text = "✅ <b>Етап 'Видача даних' створено!</b>\n\n"
            text += f"🏦 Банк: {bank_name}\n"
            text += f"🔄 Операція: {action_text}\n"
            text += f"📋 Етап: {step}\n\n"
            text += "Етап налаштовано для:\n"
            text += "• ✅ Запит номеру телефону\n"
            text += "• ✅ Запит email\n"
            text += "• 🤖 Автоматична координація з менеджером\n\n"
            
            log_action(0, f"admin_{update.effective_user.id}", "add_stage",
                      f"{bank_name}:{action}:{step}:{stage_type}")
        else:
            text = "❌ Помилка при створенні етапу"
            
        keyboard = [
            [InlineKeyboardButton("➕ Додати ще етап", callback_data="instr_add_another")],
            [InlineKeyboardButton("✅ Завершити", callback_data="instructions_menu")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return ConversationHandler.END
        
    elif stage_type == 'user_data_request':
        text = "📋 <b>Налаштування етапу 'Запит даних'</b>\n\n"
        text += f"🏦 Банк: {bank_name}\n"
        text += f"🔄 Операція: {action_text}\n"
        text += f"📋 Етап: {step}\n\n"
        text += "Оберіть дані, які потрібно зібрати від користувача:\n\n"
        
        keyboard = [
            [InlineKeyboardButton("📱 Телефон", callback_data="data_field_phone"),
             InlineKeyboardButton("📧 Email", callback_data="data_field_email")],
            [InlineKeyboardButton("👤 ПІБ", callback_data="data_field_fullname"),
             InlineKeyboardButton("💬 Нік Telegram", callback_data="data_field_telegram")],
            [InlineKeyboardButton("✅ Завершити вибір", callback_data="data_fields_done")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"instr_action_{action}")]
        ]
        
        # Initialize data fields selection
        context.user_data['selected_data_fields'] = []
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return INSTR_STAGE_CONFIG
    
    return ConversationHandler.END

async def stage_config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stage configuration for user data request"""
    query = update.callback_query
    await query.answer()

    data = query.data
    bank_name = context.user_data.get('instr_bank')
    action = context.user_data.get('instr_action')
    step = context.user_data.get('instr_step')
    stage_type = context.user_data.get('instr_stage_type')
    selected_fields = context.user_data.get('selected_data_fields', [])

    if data.startswith("data_field_"):
        field_type = data[11:]  # Remove "data_field_" prefix
        
        if field_type in selected_fields:
            selected_fields.remove(field_type)
        else:
            selected_fields.append(field_type)
        
        context.user_data['selected_data_fields'] = selected_fields
        
        # Update display
        action_text = "Реєстрації" if action == "register" else "Перев'язки"
        
        text = "📋 <b>Налаштування етапу 'Запит даних'</b>\n\n"
        text += f"🏦 Банк: {bank_name}\n"
        text += f"🔄 Операція: {action_text}\n"
        text += f"📋 Етап: {step}\n\n"
        text += "Оберіть дані, які потрібно зібрати від користувача:\n\n"
        
        if selected_fields:
            text += "Обрані поля:\n"
            field_names = {
                'phone': '📱 Телефон',
                'email': '📧 Email', 
                'fullname': '👤 ПІБ',
                'telegram': '💬 Нік Telegram'
            }
            for field in selected_fields:
                text += f"• {field_names.get(field, field)}\n"
            text += "\n"
        
        keyboard = [
            [InlineKeyboardButton(f"{'✅' if 'phone' in selected_fields else '📱'} Телефон", callback_data="data_field_phone"),
             InlineKeyboardButton(f"{'✅' if 'email' in selected_fields else '📧'} Email", callback_data="data_field_email")],
            [InlineKeyboardButton(f"{'✅' if 'fullname' in selected_fields else '👤'} ПІБ", callback_data="data_field_fullname"),
             InlineKeyboardButton(f"{'✅' if 'telegram' in selected_fields else '💬'} Нік Telegram", callback_data="data_field_telegram")],
            [InlineKeyboardButton("✅ Завершити вибір", callback_data="data_fields_done")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"instr_action_{action}")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return INSTR_STAGE_CONFIG
        
    elif data == "data_fields_done":
        if not selected_fields:
            await query.answer("❌ Оберіть хоча б одне поле", show_alert=True)
            return INSTR_STAGE_CONFIG
            
        # Create user data request stage
        step_data = {
            'data_fields': selected_fields,
            'field_config': {field: {'required': True} for field in selected_fields}
        }
        
        # Generate instruction text based on selected fields
        field_names = {
            'phone': 'номер телефону',
            'email': 'email адресу', 
            'fullname': 'ПІБ (повне ім\'я)',
            'telegram': 'нік в Telegram'
        }
        
        field_text = ', '.join([field_names.get(field, field) for field in selected_fields])
        instruction_text = f"Будь ласка, надайте наступні дані: {field_text}."
        
        success = add_bank_instruction(
            bank_name=bank_name,
            action=action,
            step_number=step,
            instruction_text=instruction_text,
            step_type=stage_type,
            step_data=step_data
        )
        
        if success:
            action_text = "Реєстрації" if action == "register" else "Перев'язки"
            
            text = "✅ <b>Етап 'Запит даних' створено!</b>\n\n"
            text += f"🏦 Банк: {bank_name}\n"
            text += f"🔄 Операція: {action_text}\n"
            text += f"📋 Етап: {step}\n\n"
            text += "Збиратимуться наступні дані:\n"
            for field in selected_fields:
                text += f"• {field_names.get(field, field)}\n"
            
            log_action(0, f"admin_{update.effective_user.id}", "add_stage",
                      f"{bank_name}:{action}:{step}:{stage_type}")
        else:
            text = "❌ Помилка при створенні етапу"
            
        keyboard = [
            [InlineKeyboardButton("➕ Додати ще етап", callback_data="instr_add_another")],
            [InlineKeyboardButton("✅ Завершити", callback_data="instructions_menu")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return ConversationHandler.END
    
    return INSTR_STAGE_CONFIG

async def instruction_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle instruction text input for text+screenshots stages"""
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text("❌ Текст інструкції не може бути пустим. Спробуйте ще раз:")
        return INSTR_TEXT_INPUT

    bank_name = context.user_data.get('instr_bank')
    action = context.user_data.get('instr_action')
    step = context.user_data.get('instr_step')
    stage_type = context.user_data.get('instr_stage_type', 'text_screenshots')

    if not all([bank_name, action, step]):
        await update.message.reply_text("❌ Помилка: відсутні дані. Почніть заново.")
        return ConversationHandler.END

    # Create stage data for text+screenshots
    step_data = {
        'text': text,
        'example_images': [],
        'required_photos': 1
    }

    # Save instruction with enhanced stage support
    success = add_bank_instruction(
        bank_name=bank_name,
        action=action,
        step_number=step,
        instruction_text=text,
        step_type=stage_type,
        step_data=step_data
    )

    if success:
        log_action(0, f"admin_{update.effective_user.id}", "add_stage",
                  f"{bank_name}:{action}:{step}:{stage_type}")

        action_text = "Реєстрації" if action == "register" else "Перев'язки"

        keyboard = [
            [InlineKeyboardButton("➕ Додати ще етап", callback_data="instr_add_another")],
            [InlineKeyboardButton("✅ Завершити", callback_data="instructions_menu")]
        ]

        text_response = "✅ <b>Етап 'Текст + скріни' створено!</b>\n\n"
        text_response += f"🏦 Банк: {bank_name}\n"
        text_response += f"🔄 Тип: {action_text}\n"
        text_response += f"📋 Етап: {step}\n\n"
        text_response += "Що далі?"

        await update.message.reply_text(text_response,
                                      reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Помилка при збереженні етапу")

    # Clear user data
    context.user_data.pop('instr_bank', None)
    context.user_data.pop('instr_action', None)
    context.user_data.pop('instr_step', None)
    context.user_data.pop('instr_stage_type', None)

    return ConversationHandler.END

async def instruction_add_another_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding another instruction step"""
    query = update.callback_query
    await query.answer()

    # Restart the instruction adding process
    await instructions_add_handler(update, context)
    return INSTR_BANK_SELECT

async def instructions_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start editing instruction stages"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    banks = list(_iter_banks_basic())

    if not banks:
        text = "❌ Спочатку потрібно додати банки"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="instructions_list")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    text = "✏️ <b>Редагування етапів</b>\n\nВиберіть банк для редагування етапів:"
    keyboard = []

    for bank_name, is_active, register_enabled, change_enabled in banks:
        if is_active:
            # Check if bank has any instructions
            register_instructions = get_bank_instructions(bank_name, "register")
            change_instructions = get_bank_instructions(bank_name, "change")
            
            if register_instructions or change_instructions:
                total_stages = len(register_instructions) + len(change_instructions)
                keyboard.append([InlineKeyboardButton(f"{bank_name} ({total_stages} етапів)", callback_data=f"edit_bank_stages_{bank_name}")])

    if not keyboard:
        text = "❌ Немає банків з етапами для редагування"
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="instructions_list")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def edit_bank_stages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show stages for a specific bank for editing"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    bank_name = query.data.replace("edit_bank_stages_", "")
    
    register_instructions = get_bank_instructions(bank_name, "register")
    change_instructions = get_bank_instructions(bank_name, "change")
    stage_types = get_stage_types()

    text = f"✏️ <b>Редагування етапів '{bank_name}'</b>\n\n"
    keyboard = []

    if register_instructions:
        text += "📝 <b>Реєстрація:</b>\n"
        for instr in register_instructions:
            step_number, instruction_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
            stage_name = stage_types.get(step_type, {}).get('name', step_type)
            text += f"  {step_order}. {stage_name} - {instruction_text[:40]}...\n"
            keyboard.append([InlineKeyboardButton(f"✏️ Етап {step_order} (Реєстрація)", callback_data=f"edit_stage_{bank_name}_register_{step_number}")])
        text += "\n"

    if change_instructions:
        text += "🔄 <b>Перев'язка:</b>\n"
        for instr in change_instructions:
            step_number, instruction_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
            stage_name = stage_types.get(step_type, {}).get('name', step_type)
            text += f"  {step_order}. {stage_name} - {instruction_text[:40]}...\n"
            keyboard.append([InlineKeyboardButton(f"✏️ Етап {step_order} (Перев'язка)", callback_data=f"edit_stage_{bank_name}_change_{step_number}")])

    keyboard.extend([
        [InlineKeyboardButton("🔄 Змінити порядок", callback_data=f"reorder_stages_{bank_name}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="instructions_edit")]
    ])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def edit_stage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle editing individual instruction stage"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")
    
    query = update.callback_query
    await query.answer()
    
    # Parse callback data: edit_stage_{bank_name}_{action}_{step_number}
    try:
        parts = query.data.split("_", 3)
        if len(parts) < 4:
            await query.edit_message_text("❌ Некоректні дані")
            return
            
        bank_name = parts[2]
        action_step = parts[3]
        
        # Split action and step_number
        if "_" in action_step:
            action, step_number_str = action_step.rsplit("_", 1)
            step_number = int(step_number_str)
        else:
            await query.edit_message_text("❌ Некоректний формат даних")
            return
            
    except (ValueError, IndexError) as e:
        await query.edit_message_text("❌ Помилка парсингу даних")
        return
    
    # Get the instruction
    instruction = get_instruction_by_step(bank_name, action, step_number)
    if not instruction:
        await query.edit_message_text("❌ Етап не знайдено")
        return
    
    # Parse instruction data
    (instr_id, bank, act, step_num, text, images_json, age_req, 
     req_photos, step_type, step_data, step_order) = instruction
    
    import json
    images = json.loads(images_json) if images_json else []
    stage_data = json.loads(step_data) if step_data else {}
    
    # Get stage types for display
    stage_types = get_stage_types()
    stage_name = stage_types.get(step_type, {}).get('name', step_type)
    
    # Build the edit interface
    text_display = f"✏️ <b>Редагування етапу</b>\n\n"
    text_display += f"🏦 Банк: {bank_name}\n"
    text_display += f"🔄 Дія: {'Реєстрація' if action == 'register' else 'Перевʼязка'}\n"
    text_display += f"📋 Тип етапу: {stage_name}\n"
    text_display += f"📊 Порядок: {step_order}\n\n"
    
    if text:
        text_display += f"📝 <b>Текст:</b>\n{text[:200]}{'...' if len(text) > 200 else ''}\n\n"
    
    if images:
        text_display += f"🖼️ Зображень: {len(images)}\n\n"
    
    if age_req:
        text_display += f"🔞 Віковi вимоги: {age_req} років\n"
    
    if req_photos:
        text_display += f"📷 Потрібно фото: {req_photos}\n"
    
    # Create edit options
    keyboard = [
        [InlineKeyboardButton("📝 Змінити текст", callback_data=f"edit_field_text_{bank_name}_{action}_{step_number}")],
        [InlineKeyboardButton("🖼️ Змінити зображення", callback_data=f"edit_field_images_{bank_name}_{action}_{step_number}")],
        [InlineKeyboardButton("🔞 Змінити вікові вимоги", callback_data=f"edit_field_age_{bank_name}_{action}_{step_number}")],
        [InlineKeyboardButton("📷 Змінити к-сть фото", callback_data=f"edit_field_photos_{bank_name}_{action}_{step_number}")],
        [InlineKeyboardButton("🗑️ Очистити текст і зображення", callback_data=f"clear_stage_content_{bank_name}_{action}_{step_number}")],
        [InlineKeyboardButton("❌ Видалити етап", callback_data=f"delete_stage_{bank_name}_{action}_{step_number}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"edit_bank_stages_{bank_name}")]
    ]
    
    await query.edit_message_text(text_display, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def clear_stage_content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle clearing text and images from stage"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")
    
    query = update.callback_query
    await query.answer()
    
    # Parse callback data: clear_stage_content_{bank_name}_{action}_{step_number}
    try:
        parts = query.data.split("_", 4)
        if len(parts) < 5:
            await query.edit_message_text("❌ Некоректні дані")
            return
            
        bank_name = parts[3]
        action_step = parts[4]
        
        # Split action and step_number
        if "_" in action_step:
            action, step_number_str = action_step.rsplit("_", 1)
            step_number = int(step_number_str)
        else:
            await query.edit_message_text("❌ Некоректний формат даних")
            return
            
    except (ValueError, IndexError) as e:
        await query.edit_message_text("❌ Помилка парсингу даних")
        return
    
    # Clear text and images
    success = update_bank_instruction(
        bank_name, action, step_number,
        instruction_text="",
        instruction_images=[]
    )
    
    if success:
        log_action(0, f"admin_{update.effective_user.id}", "clear_stage_content", 
                  f"{bank_name}_{action}_{step_number}")
        await query.edit_message_text(
            f"✅ Текст і зображення етапу очищено!\n\n"
            f"🏦 Банк: {bank_name}\n"
            f"🔄 Дія: {'Реєстрація' if action == 'register' else 'Перевʼязка'}\n"
            f"📋 Етап: {step_number}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад до етапу", callback_data=f"edit_stage_{bank_name}_{action}_{step_number}")],
                [InlineKeyboardButton("🔙 До списку етапів", callback_data=f"edit_bank_stages_{bank_name}")]
            ])
        )
    else:
        await query.edit_message_text("❌ Помилка при очищенні етапу")

async def instructions_reorder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start reordering instruction stages"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    banks = list(_iter_banks_basic())

    if not banks:
        text = "❌ Спочатку потрібно додати банки"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="instructions_list")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    text = "🔄 <b>Зміна порядку етапів</b>\n\nВиберіть банк для зміни порядку етапів:"
    keyboard = []

    for bank_name, is_active, register_enabled, change_enabled in banks:
        if is_active:
            # Check if bank has multiple instructions
            register_instructions = get_bank_instructions(bank_name, "register")
            change_instructions = get_bank_instructions(bank_name, "change")
            
            if len(register_instructions) > 1 or len(change_instructions) > 1:
                total_stages = len(register_instructions) + len(change_instructions)
                keyboard.append([InlineKeyboardButton(f"{bank_name} ({total_stages} етапів)", callback_data=f"reorder_bank_{bank_name}")])

    if not keyboard:
        text = "❌ Немає банків з достатньою кількістю етапів для зміни порядку"
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="instructions_list")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def reorder_bank_stages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reordering interface for a specific bank"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")

    query = update.callback_query
    await query.answer()

    bank_name = query.data.replace("reorder_bank_", "").replace("reorder_stages_", "")
    
    register_instructions = get_bank_instructions(bank_name, "register")
    change_instructions = get_bank_instructions(bank_name, "change")
    stage_types = get_stage_types()

    text = f"🔄 <b>Зміна порядку етапів '{bank_name}'</b>\n\n"
    text += "Використовуйте кнопки ⬆️ та ⬇️ для зміни порядку етапів:\n\n"
    
    keyboard = []

    if register_instructions and len(register_instructions) > 1:
        text += "📝 <b>Реєстрація:</b>\n"
        for i, instr in enumerate(register_instructions):
            step_number, instruction_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
            stage_name = stage_types.get(step_type, {}).get('name', step_type)
            text += f"  {i+1}. {stage_name}\n"
            
            buttons = []
            if i > 0:
                buttons.append(InlineKeyboardButton("⬆️", callback_data=f"move_up_{bank_name}_register_{step_number}"))
            if i < len(register_instructions) - 1:
                buttons.append(InlineKeyboardButton("⬇️", callback_data=f"move_down_{bank_name}_register_{step_number}"))
            
            if buttons:
                buttons.append(InlineKeyboardButton(f"Етап {i+1}", callback_data="noop"))
                keyboard.append(buttons)
        text += "\n"

    if change_instructions and len(change_instructions) > 1:
        text += "🔄 <b>Перев'язка:</b>\n"
        for i, instr in enumerate(change_instructions):
            step_number, instruction_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
            stage_name = stage_types.get(step_type, {}).get('name', step_type)
            text += f"  {i+1}. {stage_name}\n"
            
            buttons = []
            if i > 0:
                buttons.append(InlineKeyboardButton("⬆️", callback_data=f"move_up_{bank_name}_change_{step_number}"))
            if i < len(change_instructions) - 1:
                buttons.append(InlineKeyboardButton("⬇️", callback_data=f"move_down_{bank_name}_change_{step_number}"))
                
            if buttons:
                buttons.append(InlineKeyboardButton(f"Етап {i+1}", callback_data="noop"))
                keyboard.append(buttons)

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"edit_bank_stages_{bank_name}")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def manage_bank_instructions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to manage bank instructions"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    if not context.args:
        # Show usage and available banks
        banks = list(_iter_banks_basic())
        text = "📝 <b>Управління інструкціями банків</b>\n\n"
        text += "Використання: /manage_instructions <назва_банку>\n\n"
        text += "Доступні банки:\n"

        for bank_name, is_active, register_enabled, change_enabled in banks:
            status = "✅" if is_active else "❌"
            text += f"{status} {bank_name}\n"

        await update.message.reply_text(text, parse_mode='HTML')
        return

    bank_name = " ".join(context.args).strip()

    # Check if bank exists
    banks = {name for name, _, _, _ in _iter_banks_basic()}
    if bank_name not in banks:
        await update.message.reply_text(f"❌ Банк '{bank_name}' не знайдено")
        return

    # Show instructions for this bank
    register_instructions = get_bank_instructions(bank_name, "register")
    change_instructions = get_bank_instructions(bank_name, "change")

    text = f"📝 <b>Інструкції для '{bank_name}'</b>\n\n"

    if register_instructions:
        text += "📝 <b>Реєстрація:</b>\n"
        for instr in register_instructions:
            step_num, instr_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
            stage_types = get_stage_types()
            stage_name = stage_types.get(step_type, {}).get('name', step_type)
            text += f"  {step_order}. {stage_name}: {instr_text[:50]}{'...' if len(instr_text) > 50 else ''}\n"
        text += "\n"
    else:
        text += "📝 <b>Реєстрація:</b> ❌ Немає інструкцій\n\n"

    if change_instructions:
        text += "🔄 <b>Перев'язка:</b>\n"
        for instr in change_instructions:
            step_num, instr_text, images_json, age_req, req_photos, step_type, step_data, step_order = instr
            stage_types = get_stage_types()
            stage_name = stage_types.get(step_type, {}).get('name', step_type)
            text += f"  {step_order}. {stage_name}: {instr_text[:50]}{'...' if len(instr_text) > 50 else ''}\n"
    else:
        text += "🔄 <b>Перев'язка:</b> ❌ Немає інструкцій\n"

    await update.message.reply_text(text, parse_mode='HTML')

async def sync_instructions_to_file_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sync database instructions to instructions.py file"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    try:
        # Get all banks and their instructions
        banks = list(_iter_banks_basic())
        instructions_data = {}

        for bank_name, is_active, register_enabled, change_enabled in banks:
            if not is_active:
                continue

            bank_instructions = {}

            if register_enabled:
                register_instructions = get_bank_instructions(bank_name, "register")
                if register_instructions:
                    bank_instructions["register"] = []
                    for instr in register_instructions:
                        step_num, instr_text, images_json, age_req, req_photos, step_type, step_data_json, step_order = instr
                        step_data = {"text": instr_text}
                        if images_json:
                            try:
                                step_data["images"] = json.loads(images_json)
                            except (json.JSONDecodeError, ValueError):
                                step_data["images"] = []
                        else:
                            step_data["images"] = []
                        if age_req:
                            step_data["age"] = age_req
                        if req_photos:
                            step_data["required_photos"] = req_photos
                        # Add stage type information for enhanced compatibility
                        step_data["stage_type"] = step_type
                        if step_data_json:
                            try:
                                enhanced_data = json.loads(step_data_json)
                                step_data["stage_config"] = enhanced_data
                            except (json.JSONDecodeError, ValueError):
                                pass
                        bank_instructions["register"].append(step_data)

            if change_enabled:
                change_instructions = get_bank_instructions(bank_name, "change")
                if change_instructions:
                    bank_instructions["change"] = []
                    for instr in change_instructions:
                        step_num, instr_text, images_json, age_req, req_photos, step_type, step_data_json, step_order = instr
                        step_data = {"text": instr_text}
                        if images_json:
                            try:
                                step_data["images"] = json.loads(images_json)
                            except (json.JSONDecodeError, ValueError):
                                step_data["images"] = []
                        else:
                            step_data["images"] = []
                        if age_req:
                            step_data["age"] = age_req
                        if req_photos:
                            step_data["required_photos"] = req_photos
                        # Add stage type information for enhanced compatibility
                        step_data["stage_type"] = step_type
                        if step_data_json:
                            try:
                                enhanced_data = json.loads(step_data_json)
                                step_data["stage_config"] = enhanced_data
                            except (json.JSONDecodeError, ValueError):
                                pass
                        bank_instructions["change"].append(step_data)

            if bank_instructions:
                instructions_data[bank_name] = bank_instructions

        # Generate instructions.py content
        content = '"""\nДинамічно згенеровані інструкції з бази даних\n"""\n\n'
        content += f"INSTRUCTIONS = {json.dumps(instructions_data, ensure_ascii=False, indent=4)}\n"

        # Write to file
        with open("instructions_generated.py", "w", encoding="utf-8") as f:
            f.write(content)

        log_action(0, f"admin_{update.effective_user.id}", "sync_instructions",
                  f"Synced {len(instructions_data)} banks")

        await update.message.reply_text(
            f"✅ Інструкції синхронізовано!\n\n"
            f"📁 Файл: instructions_generated.py\n"
            f"🏦 Банків: {len(instructions_data)}\n\n"
            f"Щоб використати, замініть imports в коді:\n"
            f"<code>from instructions_generated import INSTRUCTIONS</code>",
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"Error syncing instructions: {e}")
        await update.message.reply_text(f"❌ Помилка при синхронізації: {e}")

# Conversation handler helper
async def cancel_instruction_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel instruction management conversation"""
    await update.message.reply_text("❌ Управління інструкціями скасовано")
    return ConversationHandler.END

async def migrate_instructions_from_file_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Migrate instructions from instructions.py to database"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")

    try:
        from instructions import INSTRUCTIONS
        from db import add_bank, cursor, conn
        
        migrated_banks = 0
        migrated_instructions = 0
        
        await update.message.reply_text("🔄 Починаю міграцію з instructions.py...")
        
        for bank_name, actions in INSTRUCTIONS.items():
            # First, ensure the bank exists in the database
            cursor.execute("SELECT name FROM banks WHERE name=?", (bank_name,))
            if not cursor.fetchone():
                # Determine which actions are available for the bank
                has_register = 'register' in actions
                has_change = 'change' in actions
                
                # Add the bank with default settings
                if add_bank(bank_name, has_register, has_change, None, f"Мігровано з файлу інструкцій"):
                    migrated_banks += 1
                    logger.info(f"Added bank {bank_name}")
            
            # Migrate instructions for each action
            for action, instructions_list in actions.items():
                for step_num, instruction in enumerate(instructions_list, 1):
                    instruction_text = instruction.get('text', '')
                    instruction_images = instruction.get('images', [])
                    age_requirement = instruction.get('age')
                    
                    # Add instruction to database
                    if add_bank_instruction(
                        bank_name=bank_name,
                        action=action,
                        step_number=step_num,
                        instruction_text=instruction_text,
                        instruction_images=instruction_images,
                        age_requirement=age_requirement,
                        required_photos=1  # Default value
                    ):
                        migrated_instructions += 1
                        logger.info(f"Added instruction {bank_name} {action} step {step_num}")
        
        # Log the migration
        log_action(0, f"admin_{update.effective_user.id}", "migrate_instructions", 
                  f"{migrated_banks} banks, {migrated_instructions} instructions")
        
        text = "✅ <b>Міграція завершена!</b>\n\n"
        text += f"🏦 Банків додано: {migrated_banks}\n"
        text += f"📝 Інструкцій мігровано: {migrated_instructions}\n\n"
        text += "Тепер ви можете керувати всіма банками та інструкціями через адмін панель!\n\n"
        text += "💡 <i>Рекомендується зробити резервну копію instructions.py перед його видаленням.</i>"
        
        await update.message.reply_text(text, parse_mode='HTML')
        
    except ImportError:
        await update.message.reply_text("❌ Файл instructions.py не знайдено")
    except Exception as e:
        logger.error(f"Migration error: {e}")
        await update.message.reply_text(f"❌ Помилка при міграції: {e}")
