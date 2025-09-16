"""
Instruction management handlers for dynamic bank instruction management
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from db import (
    is_admin, get_banks, add_bank_instruction, get_bank_instructions,
    delete_bank, cursor, conn, log_action
)
import json
import logging

logger = logging.getLogger(__name__)

# Conversation states for instruction management
INSTR_BANK_SELECT, INSTR_ACTION_SELECT, INSTR_STEP_INPUT, INSTR_TEXT_INPUT = range(10, 14)

async def instructions_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all instructions for all banks"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")
    
    query = update.callback_query
    await query.answer()
    
    banks = get_banks()
    
    if not banks:
        text = "📝 <b>Інструкції банків</b>\n\n❌ Немає зареєстрованих банків"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="instructions_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return
    
    text = "📝 <b>Інструкції банків</b>\n\n"
    
    for bank_name, is_active, register_enabled, change_enabled in banks:
        text += f"🏦 <b>{bank_name}</b>\n"
        
        # Get instructions for this bank
        register_instructions = get_bank_instructions(bank_name, "register")
        change_instructions = get_bank_instructions(bank_name, "change")
        
        if register_enabled and register_instructions:
            text += f"   📝 Реєстрація: {len(register_instructions)} кроків\n"
        elif register_enabled:
            text += f"   📝 Реєстрація: ❌ Немає інструкцій\n"
            
        if change_enabled and change_instructions:
            text += f"   🔄 Перев'язка: {len(change_instructions)} кроків\n"
        elif change_enabled:
            text += f"   🔄 Перев'язка: ❌ Немає інструкцій\n"
        
        text += "\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Додати інструкцію", callback_data="instructions_add")],
        [InlineKeyboardButton("🔙 Назад", callback_data="instructions_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def instructions_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding instruction conversation"""
    if not is_admin(update.effective_user.id):
        return await update.callback_query.answer("⛔ Немає доступу")
    
    query = update.callback_query
    await query.answer()
    
    banks = get_banks()
    
    if not banks:
        text = "❌ Спочатку потрібно додати банки"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="instructions_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    text = "🏦 <b>Виберіть банк для додавання інструкції:</b>\n\n"
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
    """Handle action selection for instruction"""
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
    
    # Get existing steps count
    existing_instructions = get_bank_instructions(bank_name, action)
    next_step = len(existing_instructions) + 1
    
    context.user_data['instr_step'] = next_step
    
    action_text = "Реєстрації" if action == "register" else "Перев'язки"
    
    text = f"📝 <b>Додавання інструкції</b>\n\n"
    text += f"🏦 Банк: {bank_name}\n"
    text += f"🔄 Тип: {action_text}\n"
    text += f"📋 Крок: {next_step}\n\n"
    text += f"Введіть текст інструкції для кроку {next_step}:"
    
    await query.edit_message_text(text, parse_mode='HTML')
    return INSTR_TEXT_INPUT

async def instruction_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle instruction text input"""
    text = update.message.text.strip()
    
    if not text:
        await update.message.reply_text("❌ Текст інструкції не може бути пустим. Спробуйте ще раз:")
        return INSTR_TEXT_INPUT
    
    bank_name = context.user_data.get('instr_bank')
    action = context.user_data.get('instr_action')
    step = context.user_data.get('instr_step')
    
    if not all([bank_name, action, step]):
        await update.message.reply_text("❌ Помилка: відсутні дані. Почніть заново.")
        return ConversationHandler.END
    
    # Save instruction
    success = add_bank_instruction(bank_name, action, step, text)
    
    if success:
        log_action(0, f"admin_{update.effective_user.id}", "add_instruction", 
                  f"{bank_name}:{action}:{step}")
        
        action_text = "Реєстрації" if action == "register" else "Перев'язки"
        
        keyboard = [
            [InlineKeyboardButton("➕ Додати ще крок", callback_data="instr_add_another")],
            [InlineKeyboardButton("✅ Завершити", callback_data="instructions_menu")]
        ]
        
        text_response = f"✅ <b>Інструкція додана!</b>\n\n"
        text_response += f"🏦 Банк: {bank_name}\n"
        text_response += f"🔄 Тип: {action_text}\n"
        text_response += f"📋 Крок: {step}\n\n"
        text_response += f"Що далі?"
        
        await update.message.reply_text(text_response, 
                                      reply_markup=InlineKeyboardMarkup(keyboard), 
                                      parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Помилка при збереженні інструкції")
    
    # Clear user data
    context.user_data.pop('instr_bank', None)
    context.user_data.pop('instr_action', None) 
    context.user_data.pop('instr_step', None)
    
    return ConversationHandler.END

async def instruction_add_another_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding another instruction step"""
    query = update.callback_query
    await query.answer()
    
    # Restart the instruction adding process
    await instructions_add_handler(update, context)
    return INSTR_BANK_SELECT

async def manage_bank_instructions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to manage bank instructions"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    
    if not context.args:
        # Show usage and available banks
        banks = get_banks()
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
    banks = {name for name, _, _, _ in get_banks()}
    if bank_name not in banks:
        await update.message.reply_text(f"❌ Банк '{bank_name}' не знайдено")
        return
    
    # Show instructions for this bank
    register_instructions = get_bank_instructions(bank_name, "register")
    change_instructions = get_bank_instructions(bank_name, "change")
    
    text = f"📝 <b>Інструкції для '{bank_name}'</b>\n\n"
    
    if register_instructions:
        text += f"📝 <b>Реєстрація:</b>\n"
        for step_num, instr_text, images, age_req, req_photos in register_instructions:
            text += f"  {step_num}. {instr_text[:50]}{'...' if len(instr_text) > 50 else ''}\n"
        text += "\n"
    else:
        text += f"📝 <b>Реєстрація:</b> ❌ Немає інструкцій\n\n"
    
    if change_instructions:
        text += f"🔄 <b>Перев'язка:</b>\n"
        for step_num, instr_text, images, age_req, req_photos in change_instructions:
            text += f"  {step_num}. {instr_text[:50]}{'...' if len(instr_text) > 50 else ''}\n"
    else:
        text += f"🔄 <b>Перев'язка:</b> ❌ Немає інструкцій\n"
    
    await update.message.reply_text(text, parse_mode='HTML')

async def sync_instructions_to_file_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sync database instructions to instructions.py file"""
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу")
    
    try:
        # Get all banks and their instructions
        banks = get_banks()
        instructions_data = {}
        
        for bank_name, is_active, register_enabled, change_enabled in banks:
            if not is_active:
                continue
                
            bank_instructions = {}
            
            if register_enabled:
                register_instructions = get_bank_instructions(bank_name, "register")
                if register_instructions:
                    bank_instructions["register"] = []
                    for step_num, instr_text, images_json, age_req, req_photos in register_instructions:
                        step_data = {"text": instr_text}
                        if images_json:
                            try:
                                step_data["images"] = json.loads(images_json)
                            except:
                                step_data["images"] = []
                        else:
                            step_data["images"] = []
                        if age_req:
                            step_data["age"] = age_req
                        if req_photos:
                            step_data["required_photos"] = req_photos
                        bank_instructions["register"].append(step_data)
            
            if change_enabled:
                change_instructions = get_bank_instructions(bank_name, "change")
                if change_instructions:
                    bank_instructions["change"] = []
                    for step_num, instr_text, images_json, age_req, req_photos in change_instructions:
                        step_data = {"text": instr_text}
                        if images_json:
                            try:
                                step_data["images"] = json.loads(images_json)
                            except:
                                step_data["images"] = []
                        else:
                            step_data["images"] = []
                        if age_req:
                            step_data["age"] = age_req
                        if req_photos:
                            step_data["required_photos"] = req_photos
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