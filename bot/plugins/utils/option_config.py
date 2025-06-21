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

@Client.on_message(
    filters.private & PyroFilters.admin() & filters.command(["option", "settings"]),
)
@RateLimiter.hybrid_limiter(func_count=1)
async def option_config_cmd(client: Client, message: Message) -> Optional[Message]:
    """Configure database options through an interactive menu."""
    try:
        # Get current settings safely
        options_configs = options.settings.model_dump()
        
        # Generate buttons for all available settings
        buttons = []
        keys = list(options_configs.keys())
        
        # Organize buttons in two columns
        for i in range(0, len(keys), 2):
            row = []
            if i < len(keys):
                row.append(InlineKeyboardButton(
                    text=f"⚙️ {keys[i]}",
                    callback_data=f"option_view_{keys[i]}"
                ))
            if i + 1 < len(keys):
                row.append(InlineKeyboardButton(
                    text=f"⚙️ {keys[i+1]}",
                    callback_data=f"option_view_{keys[i+1]}"
                ))
            if row:
                buttons.append(row)
        
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

@Client.on_callback_query(filters.regex(r"^option_(view|edit|close|save|cancel|refresh|back|custom)_"))
async def option_callback_handler(client: Client, callback: CallbackQuery):
    try:
        action, *data = callback.data.split("_")[1:]
        user_id = callback.from_user.id
        
        if action == "close":
            await callback.message.delete()
            await callback.answer("Settings menu closed")
            return
        
        if action == "refresh":
            await option_config_cmd(client, callback.message)
            await callback.answer("Menu refreshed")
            return
        
        if action == "cancel":
            user_sessions.pop(user_id, None)
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer("Cancelled")
            return
        
        if action == "back":
            await option_config_cmd(client, callback.message)
            await callback.answer()
            return
        
        # Get the key safely
        if not data:
            await callback.answer("Invalid option!", show_alert=True)
            return
            
        key = data[0]
        
        # Verify the key exists in settings
        if not hasattr(options.settings, key):
            await callback.answer("This setting doesn't exist!", show_alert=True)
            return
            
        current_value = getattr(options.settings, key)
        
        if action == "view":
            buttons = [
                [InlineKeyboardButton("✏️ Edit", callback_data=f"option_edit_{key}")],
                [InlineKeyboardButton("🔙 Back", callback_data="option_back_")]
            ]
            
            await callback.message.edit_text(
                text=f"⚙️ **{key}**\n\nCurrent value: `{current_value}`\n\nType: {type(current_value).__name__}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await callback.answer()
            return
        
        if action == "edit":
            user_sessions[user_id] = {"key": key, "original_value": current_value}
            
            if isinstance(current_value, bool):
                buttons = [
                    [
                        InlineKeyboardButton("✅ True", callback_data=f"option_save_{key}_True"),
                        InlineKeyboardButton("❌ False", callback_data=f"option_save_{key}_False")
                    ],
                    [InlineKeyboardButton("🔙 Back", callback_data=f"option_view_{key}")]
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
                    [InlineKeyboardButton("✏️ Custom Value", callback_data=f"option_custom_{key}")],
                    [InlineKeyboardButton("🔙 Back", callback_data=f"option_view_{key}")]
                ]
                await callback.message.edit_text(
                    text=f"✏️ Editing: {key}\nCurrent value: {current_value}",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            else:
                await callback.message.edit_text(
                    text=f"✏️ Editing: {key}\nCurrent value: `{current_value}`\n\n"
                         "Please send me the new value for this setting.\n"
                         "Type /cancel to abort.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data=f"option_view_{key}")]
                    ])
                )
            await callback.answer()
            return
        
        if action == "save":
            if len(data) < 2:
                await callback.answer("Invalid data!", show_alert=True)
                return
                
            new_value = eval(data[1])  # Safe because we control the values
            
            try:
                await options.update_settings(key=key, value=new_value)
                await callback.message.edit_text(
                    text=f"✅ Updated: **{key}** = `{new_value}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back to Menu", callback_data="option_back_")]
                    ])
                )
                user_sessions.pop(user_id, None)
                await callback.answer("Setting updated!")
            except InvalidValueError:
                await callback.answer("Invalid value for this setting!", show_alert=True)
            return
            
        if action == "custom":
            user_sessions[user_id] = {"key": key, "original_value": current_value}
            await callback.message.edit_text(
                text=f"✏️ Custom value for: {key}\nCurrent value: {current_value}\n\n"
                     "Please send me the new numeric value.\n"
                     "Type /cancel to abort.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data=f"option_view_{key}")]
                ])
            )
            await callback.answer()
            
    except Exception as e:
        await callback.answer(f"Error: {str(e)}", show_alert=True)
        raise

@Client.on_message(
    filters.private & PyroFilters.admin() & ~filters.command(["option", "settings", "cancel"])
)
async def option_value_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        return
    
    if message.text and message.text.startswith("/cancel"):
        await message.reply("❌ Setting update cancelled.")
        user_sessions.pop(user_id, None)
        return
    
    session = user_sessions[user_id]
    key = session["key"]
    current_value = session["original_value"]
    new_value = message.text
    
    try:
        # Convert to appropriate type
        if isinstance(current_value, bool):
            new_value = new_value.lower() in ("true", "yes", "1", "on")
        elif isinstance(current_value, (int, float)):
            new_value = type(current_value)(new_value)
        # For strings, keep as-is
        
        await options.update_settings(key=key, value=new_value)
        await message.reply(
            text=f"✅ Updated: **{key}** = `{new_value}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="option_back_")]
            ]),
            quote=True
        )
        user_sessions.pop(user_id, None)
    except (ValueError, InvalidValueError):
        await message.reply(
            text="❌ Invalid value! Please try again or /cancel",
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
