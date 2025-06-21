from inspect import cleandoc
from typing import Optional

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
user_sessions = {}

@Client.on_message(
    filters.private & PyroFilters.admin() & filters.command(["option", "settings"]),
)
@RateLimiter.hybrid_limiter(func_count=1)
async def option_config_cmd(client: Client, message: Message) -> Optional[Message]:
    """Configure database options through an interactive menu.
    
    **Usage:** Just send /option or /settings to see available options.
    """
    # Generate buttons for all settings (show only keys initially)
    buttons = []
    options_configs = options.settings.model_dump()
    
    # Organize buttons in two columns for better layout
    keys = list(options_configs.keys())
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
    
    # Add navigation buttons
    buttons.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="option_refresh"),
        InlineKeyboardButton("❌ Close", callback_data="option_close")
    ])
    
    return await message.reply(
        text="⚙️ **Settings Menu**\n\nSelect an option to view/edit:",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )

@Client.on_callback_query(filters.regex(r"^option_(view|edit|close|save|cancel|refresh|back)_"))
async def option_callback_handler(client: Client, callback: CallbackQuery):
    action, *data = callback.data.split("_")[1:]
    user_id = callback.from_user.id
    
    if action == "close":
        await callback.message.delete()
        await callback.answer("Settings menu closed")
        return
    
    if action == "refresh":
        # Regenerate the main menu
        await option_config_cmd(client, callback.message)
        await callback.answer("Menu refreshed")
        return
    
    if action == "cancel":
        if user_id in user_sessions:
            del user_sessions[user_id]
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Cancelled")
        return
    
    if action == "back":
        # Return to main menu
        await option_config_cmd(client, callback.message)
        await callback.answer()
        return
    
    if action == "view":
        key = data[0]
        current_value = getattr(options.settings, key)
        
        # Create buttons for this specific option
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
        key = data[0]
        current_value = getattr(options.settings, key)
        
        # Store the editing state
        user_sessions[user_id] = {"key": key, "original_value": current_value}
        
        # Create appropriate edit interface based on value type
        if isinstance(current_value, bool):
            buttons = [
                [
                    InlineKeyboardButton("✅ Set True", callback_data=f"option_save_{key}_True"),
                    InlineKeyboardButton("❌ Set False", callback_data=f"option_save_{key}_False")
                ],
                [InlineKeyboardButton("🔙 Cancel", callback_data=f"option_view_{key}")]
            ]
            
            await callback.message.edit_text(
                text=f"✏️ Editing: {key}\nCurrent value: {current_value}\n\nSelect new value:",
                reply_markup=InlineKeyboardMarkup(buttons))
            
        elif isinstance(current_value, int):
            # Suggest common increments for numbers
            buttons = [
                [
                    InlineKeyboardButton("-10", callback_data=f"option_save_{key}_{current_value-10}"),
                    InlineKeyboardButton("-1", callback_data=f"option_save_{key}_{current_value-1}"),
                    InlineKeyboardButton("+1", callback_data=f"option_save_{key}_{current_value+1}"),
                    InlineKeyboardButton("+10", callback_data=f"option_save_{key}_{current_value+10}"),
                ],
                [InlineKeyboardButton("✏️ Custom Value", callback_data=f"option_custom_{key}")],
                [InlineKeyboardButton("🔙 Cancel", callback_data=f"option_view_{key}")]
            ]
            
            await callback.message.edit_text(
                text=f"✏️ Editing: {key}\nCurrent value: {current_value}\n\nSelect adjustment:",
                reply_markup=InlineKeyboardMarkup(buttons))
            
        else:  # String or other types
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
        key = data[0]
        new_value = eval(data[1])  # Safe here because we control the possible values
        
        try:
            await options.update_settings(key=key, value=new_value)
            await callback.message.edit_text(
                text=f"✅ Successfully updated:\n**{key}** = `{new_value}`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Menu", callback_data="option_back_")]
                ])
            )
            if user_id in user_sessions:
                del user_sessions[user_id]
            await callback.answer("Setting updated!")
        except InvalidValueError:
            await callback.answer("Invalid value for this setting!", show_alert=True)
        return
    
    if action == "custom":
        key = data[0]
        current_value = getattr(options.settings, key)
        user_sessions[user_id] = {"key": key, "original_value": current_value}
        
        await callback.message.edit_text(
            text=f"✏️ Editing: {key}\nCurrent value: {current_value}\n\n"
                 "Please send me the new numeric value for this setting.\n"
                 "Type /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Cancel", callback_data=f"option_view_{key}")]
            ])
        )
        await callback.answer()

@Client.on_message(
    filters.private & PyroFilters.admin() & ~filters.command(["option", "settings", "cancel"])
)
async def option_value_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        return
    
    if message.text and message.text.startswith("/cancel"):
        await message.reply("Setting update cancelled.")
        if user_id in user_sessions:
            del user_sessions[user_id]
        return
    
    session = user_sessions[user_id]
    key = session["key"]
    new_value = message.text
    
    # Try to convert to appropriate type
    try:
        if isinstance(getattr(options.settings, key), bool):
            new_value = new_value.lower() in ("true", "yes", "1")
        elif isinstance(getattr(options.settings, key), int):
            new_value = int(new_value)
        # For strings, keep as-is
    except (ValueError, AttributeError):
        await message.reply(
            text="❌ Invalid value format for this setting! Please try again or /cancel",
            quote=True
        )
        return
    
    try:
        await options.update_settings(key=key, value=new_value)
        await message.reply(
            text=f"✅ Successfully updated:\n**{key}** = `{new_value}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", 
                 callback_data="option_back_")]
            ]),
            quote=True
        )
        del user_sessions[user_id]
    except InvalidValueError:
        await message.reply(
            text="❌ Invalid value for this setting! Please try again or /cancel",
            quote=True
        )

HelpCmd.set_help(
    command="option",
    description=option_config_cmd.__doc__,
    allow_global=False,
    allow_non_admin=False,
    alias=["settings"],
    )
