from inspect import cleandoc
from typing import Optional, Dict, Any

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from bot.config import config
from bot.options import InvalidValueError, options
from bot.utilities.helpers import RateLimiter
from bot.utilities.pyrofilters import PyroFilters
from bot.utilities.pyrotools import HelpCmd

# Session storage for temporary state
user_sessions: Dict[int, Dict[str, Any]] = {}

BOOLEN_CONVERT = {"true": True, "false": False}

def get_settings_dict():
    """Safe way to get all settings as a dictionary"""
    return {field: getattr(options.settings, field) 
            for field in options.settings.__fields__}

@Client.on_message(
    filters.private & PyroFilters.admin() & filters.command(["option", "settings"]),
)
@RateLimiter.hybrid_limiter(func_count=1)
async def option_config_cmd(client: Client, message: Message) -> Optional[Message]:
    """Configure database options through an interactive menu."""
    try:
        settings_dict = get_settings_dict()
        
        # Generate buttons for all available settings
        buttons = []
        for field in options.settings.__fields__:
            current_value = settings_dict[field]
            display_value = str(current_value)[:20] + "..." if len(str(current_value)) > 20 else str(current_value)
            
            buttons.append(
                [InlineKeyboardButton(
                    text=f"⚙️ {field}: {display_value}",
                    callback_data=f"option_view_{field}"
                )]
            )
        
        # Add control buttons
        buttons.append([
            InlineKeyboardButton("🔄 Refresh", callback_data="option_refresh"),
            InlineKeyboardButton("❌ Close", callback_data="option_close")
        ])
        
        return await message.reply(
            text="⚙️ **Settings Menu**\n\nSelect an option to view/edit:",
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True
        )
    except Exception as e:
        await message.reply(f"❌ Error loading settings: {str(e)}")
        return None

@Client.on_callback_query(filters.regex(r"^option_(view|edit|close|save|cancel|refresh|back)_"))
async def option_callback_handler(client: Client, callback: CallbackQuery):
    try:
        action, *data = callback.data.split("_")[1:]
        user_id = callback.from_user.id
        
        if action == "close":
            await callback.message.delete()
            await callback.answer("Settings menu closed")
            return
        
        if action == "refresh":
            await callback.message.delete()
            await option_config_cmd(client, callback.message)
            await callback.answer("Menu refreshed")
            return
        
        if action == "cancel":
            user_sessions.pop(user_id, None)
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer("Cancelled")
            return
        
        if action == "back":
            await callback.message.delete()
            await option_config_cmd(client, callback.message)
            await callback.answer()
            return
        
        # Get the key safely
        if not data:
            await callback.answer("Invalid option!", show_alert=True)
            return
            
        key = data[0]
        
        # Verify the key exists in settings
        settings_dict = get_settings_dict()
        if key not in settings_dict:
            await callback.answer("This setting doesn't exist!", show_alert=True)
            return
            
        current_value = settings_dict[key]
        
        if action == "view":
            buttons = [
                [InlineKeyboardButton("✏️ Edit", callback_data=f"option_edit_{key}")],
                [InlineKeyboardButton("🔙 Back", callback_data="option_back_")]
            ]
            
            await callback.message.edit_text(
                text=f"⚙️ **{key}**\n\nCurrent value: `{current_value}`\nType: {type(current_value).__name__}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await callback.answer()
            return
        
        if action == "edit":
            user_sessions[user_id] = {"key": key, "original_value": current_value}
            
            # Handle boolean values
            if isinstance(current_value, bool):
                buttons = [
                    [
                        InlineKeyboardButton("✅ Set True", callback_data=f"option_save_{key}_True"),
                        InlineKeyboardButton("❌ Set False", callback_data=f"option_save_{key}_False")
                    ],
                    [InlineKeyboardButton("🔙 Cancel", callback_data=f"option_view_{key}")]
                ]
                
                await callback.message.edit_text(
                    text=f"✏️ Editing: {key}\nCurrent value: {current_value}",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            elif isinstance(current_value, (int, float)):
                buttons = [
                    [
                        InlineKeyboardButton("-10", callback_data=f"option_save_{key}_{current_value-10}"),
                        InlineKeyboardButton("-1", callback_data=f"option_save_{key}_{current_value-1}"),
                        InlineKeyboardButton("+1", callback_data=f"option_save_{key}_{current_value+1}"),
                        InlineKeyboardButton("+10", callback_data=f"option_save_{key}_{current_value+10}"),
                    ],
                    [InlineKeyboardButton("🔙 Cancel", callback_data=f"option_view_{key}")]
                ]
                
                await callback.message.edit_text(
                    text=f"✏️ Editing: {key}\nCurrent value: {current_value}",
                    reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await callback.message.edit_text(
                    text=f"✏️ Editing: {key}\nCurrent value: `{current_value}`\n\n"
                         "Please send me the new value for this setting.\n"
                         "Type /cancel to abort.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Cancel", callback_data=f"option_view_{key}")]
                    ])
                )
            
            await callback.answer()
            return
        
        if action == "save":
            if len(data) < 2:
                await callback.answer("Invalid data!", show_alert=True)
                return
                
            # Handle value conversion
            value_str = data[1]
            try:
                if value_str.isdigit():
                    new_value = int(value_str)
                else:
                    new_value = BOOLEN_CONVERT.get(value_str.lower(), value_str)
                
                await options.update_settings(key=key, value=new_value)
                await callback.message.edit_text(
                    text=f"✅ Successfully updated:\n**{key}** = `{new_value}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back to Menu", callback_data="option_back_")]
                    ])
                )
                user_sessions.pop(user_id, None)
                await callback.answer("Setting updated!")
            except InvalidValueError:
                await callback.answer("Invalid value for this setting!", show_alert=True)
            return
            
    except Exception as e:
        await callback.answer(f"Error: {str(e)}", show_alert=True)

@Client.on_message(
    filters.private & PyroFilters.admin() & ~filters.command(["option", "settings", "cancel"])
)
async def option_value_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        return
    
    if message.text and message.text.startswith("/cancel"):
        await message.reply("Setting update cancelled.")
        user_sessions.pop(user_id, None)
        return
    
    session = user_sessions[user_id]
    key = session["key"]
    current_value = session["original_value"]
    new_value = message.text
    
    try:
        # Handle message reply case
        if message.reply_to_message:
            values = message.reply_to_message.text.markdown if message.reply_to_message.text is not None else None
            if not values or not values.isdigit():
                copyied_mssg = await message.reply_to_message.copy(chat_id=config.BACKUP_CHANNEL)
                values = str(copyied_mssg.id if isinstance(copyied_mssg, Message) else values)
            change_value = values
        else:
            # Handle value conversion
            if isinstance(current_value, bool):
                change_value = new_value.lower() in ("true", "yes", "1", "on")
            elif isinstance(current_value, (int, float)):
                try:
                    change_value = type(current_value)(new_value)
                except ValueError:
                    await message.reply("Please enter a valid number", quote=True)
                    return
            else:
                change_value = new_value
        
        await options.update_settings(key=key, value=change_value)
        updated_value = get_settings_dict()[key]
        
        await message.reply(
            text=f"✅ Successfully updated:\n**{key}** = `{updated_value}`",
            quote=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="option_back_")]
            ])
        )
        user_sessions.pop(user_id, None)
    except InvalidValueError:
        await message.reply(
            text="Invalid value for this setting type!",
            quote=True
        )
    except Exception as e:
        await message.reply(
            text=f"❌ Error: {str(e)}",
            quote=True
        )

HelpCmd.set_help(
    command="option",
    description=option_config_cmd.__doc__,
    allow_global=False,
    allow_non_admin=False,
    alias=["settings"],
)
