from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
import logging
import db
import re

# Use um logger específico para o módulo handlers para melhor rastreamento
logger = logging.getLogger(__name__)

# Estados para ConversationHandler (Frases Personalizadas)
GETTING_TRIGGER_PHRASE = 0
GETTING_RESPONSE_PHRASE = 1
GETTING_PHRASE_ID_TO_DELETE = 2

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Olá, {user.mention_html()}! Sou a Lilith, sua assistente pessoal.\\n"
        "Use /ajuda para ver o que eu posso fazer!"
    )
    logger.info(f"Comando /start recebido de {user.id}.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await send_main_help_menu(update, context, update.message.message_id, update.message.chat_id)
    logger.info(f"Comando /ajuda recebido de {user_id}.")

async def send_main_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id=None, chat_id=None):
    """Função auxiliar para enviar/editar o menu de ajuda principal."""
    keyboard = [
        [InlineKeyboardButton("Frases Personalizadas", callback_data="help_category:phrases")],
        [InlineKeyboardButton("Listas", callback_data="help_category:lists")],
        [InlineKeyboardButton("Lembretes", callback_data="help_category:reminders")],
        [InlineKeyboardButton("Contas Financeiras", callback_data="help_category:accounts")], # Adicionado para o menu de ajuda
        [InlineKeyboardButton("Comandos Gerais", callback_data="help_category:general")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    help_text = escape_markdown(
        "Selecione uma categoria para ver os comandos disponíveis:", version=2
    )

    if message_id and chat_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=help_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Menu de ajuda principal enviado.")


async def handle_help_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lida com a seleção de categoria no menu de ajuda."""
    query = update.callback_query
    await query.answer()
    category = query.data.split(':')[1]
    user_id = query.from_user.id

    commands = db.get_all_commands()
    category_commands = []
    category_title = ""

    if category == "phrases":
        category_title = "📚 Frases Personalizadas"
        category_commands = [cmd for cmd, func_name, desc in commands if "phrase" in func_name or "frase" in func_name.lower()]
    elif category == "lists":
        category_title = "📝 Listas"
        category_commands = [cmd for cmd, func_name, desc in commands if "list" in func_name or "lista" in func_name.lower()]
    elif category == "reminders":
        category_title = "⏰ Lembretes"
        category_commands = [cmd for cmd, func_name, desc in commands if "reminder" in func_name or "lembrete" in func_name.lower()]
    elif category == "accounts": # Nova categoria
        category_title = "💰 Contas Financeiras"
        category_commands = [cmd for cmd, func_name, desc in commands if "account" in func_name or "contas" in func_name.lower() or "income" in func_name.lower()]
    elif category == "general":
        category_title = "✨ Comandos Gerais"
        # Filtra comandos gerais (start, ajuda, cancelar e outros que não se encaixam nas categorias acima)
        specific_commands_functions = [
            "start_command", "help_command", "send_main_help_menu", "add_phrase_start", "view_my_phrases",
            "delete_phrase_start", "new_list_start", "list_my_lists", "add_item_start", "toggle_item_start",
            "remove_item_start", "delete_list_start", "add_reminder_start", "view_reminders",
            "delete_reminder_start", "accounts_menu_start", "add_account_start", "add_income_start",
            "delete_account_start", "delete_income_start", "mark_account_paid_start"
        ]
        category_commands = [cmd for cmd, func_name, desc in commands if func_name.split('.')[-1] not in specific_commands_functions]
        # Adiciona /start, /ajuda e /cancelar explicitamente se não estiverem já
        if ("start", "handlers.start_command", "Inicia o bot e te cumprimenta.") not in commands:
            category_commands.append(("start", "handlers.start_command", "Inicia o bot e te cumprimenta."))
        if ("ajuda", "handlers.help_command", "Mostra o menu de ajuda interativo.") not in commands:
            category_commands.append(("ajuda", "handlers.help_command", "Mostra o menu de ajuda interativo."))
        if ("cancelar", "handlers.cancel_dialog", "Cancela a operação atual.") not in commands: # Supondo que você queira adicionar um db.insert para cancelar
             category_commands.append(("cancelar", "handlers.cancel_dialog", "Cancela a operação atual."))
        
        # Remove duplicatas e garante a ordem
        unique_commands = []
        seen_commands = set()
        for cmd_tuple in category_commands:
            if cmd_tuple[0] not in seen_commands:
                unique_commands.append(cmd_tuple)
                seen_commands.add(cmd_tuple[0])
        category_commands = sorted(unique_commands, key=lambda x: x[0]) # Ordena alfabeticamente

    if not category_commands:
        response_text = f"Nenhum comando encontrado para a categoria '{category_title}'. 😕"
    else:
        response_text = f"**{escape_markdown(category_title, version=2)}**\\n\\n"
        for cmd, func_name, desc in commands:
            if cmd in [c[0] for c in category_commands] and desc: # Apenas comandos que pertencem a esta categoria e que tem descrição
                 response_text += f"*{escape_markdown('/' + cmd, version=2)}*: {escape_markdown(desc, version=2)}\\n"

    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="help_category:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=response_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logger.info(f"Menu de ajuda da categoria '{category}' exibido para {user_id}.")


# --- Funções de Handler para Frases Personalizadas ---

async def add_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar uma nova frase."""
    await update.message.reply_text("Certo! Qual frase você quer que eu detecte? (Ex: 'bom dia')")
    logger.info(f"Diálogo 'addfrase' iniciado por {update.effective_user.id}.")
    return GETTING_TRIGGER_PHRASE

async def get_trigger_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de gatilho e pede a frase de resposta."""
    context.user_data['trigger_phrase'] = update.message.text
    await update.message.reply_text(f"Ok! Quando alguém disser '{update.message.text}', o que você quer que eu responda?")
    logger.info(f"Frase de gatilho '{update.message.text}' recebida de {update.effective_user.id}.")
    return GETTING_RESPONSE_PHRASE

async def get_response_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de resposta e salva no banco de dados."""
    user_id = update.effective_user.id
    trigger_phrase = context.user_data['trigger_phrase']
    response_phrase = update.message.text

    if db.insert_personal_phrase(user_id, trigger_phrase, response_phrase):
        await update.message.reply_text(f"✨ Entendido! Frase '{trigger_phrase}' com resposta '{response_phrase}' adicionada!")
        logger.info(f"Frase personalizada adicionada por {user_id}: '{trigger_phrase}' -> '{response_phrase}'.")
    else:
        await update.message.reply_text(f"❌ Ops! Não consegui adicionar a frase. Talvez você já tenha essa frase de gatilho registrada?")
        logger.warning(f"Falha ao adicionar frase personalizada por {user_id}. Gatilho: '{trigger_phrase}'.")

    context.user_data.clear()
    return ConversationHandler.END

async def view_my_phrases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe as frases personalizadas do usuário."""
    user_id = update.effective_user.id
    phrases = db.get_personal_phrases(user_id)

    if not phrases:
        await update.message.reply_text("Você ainda não tem nenhuma frase personalizada. Use /addfrase para adicionar uma!")
        logger.info(f"Nenhuma frase personalizada para {user_id}.")
        return

    message_text = "Suas frases personalizadas:\\n\\n"
    for phrase in phrases:
        message_text += f"**ID:** `{phrase['id']}`\\n" \
                        f"**Gatilho:** {escape_markdown(phrase['trigger_phrase'], version=2)}\\n" \
                        f"**Resposta:** {escape_markdown(phrase['response_phrase'], version=2)}\\n\\n"
    
    message_text += "Use /apagarfrase <ID> para remover uma."

    await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Frases personalizadas exibidas para {user_id}.")

async def delete_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar uma frase personalizada."""
    args = context.args
    if not args:
        await update.message.reply_text("Qual o ID da frase que você quer apagar? (Use /minhasfrases para ver os IDs)")
        return GETTING_PHRASE_ID_TO_DELETE
    
    try:
        phrase_id = int(args[0])
        user_id = update.effective_user.id
        
        if db.delete_personal_phrase(phrase_id, user_id):
            await update.message.reply_text(f"🗑️ Frase ID {phrase_id} apagada com sucesso!")
            logger.info(f"Frase ID {phrase_id} apagada por {user_id} via comando direto.")
        else:
            await update.message.reply_text(f"❌ Não foi possível apagar a frase ID {phrase_id}. Verifique se o ID está correto ou se a frase pertence a você.")
            logger.warning(f"Falha ao apagar frase ID {phrase_id} por {user_id} via comando direto.")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Por favor, digite um ID de frase válido (um número).")
        return GETTING_PHRASE_ID_TO_DELETE

async def confirm_delete_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga a frase personalizada com base no ID fornecido."""
    try:
        phrase_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Por favor, digite um ID de frase válido (um número).")
        return GETTING_PHRASE_ID_TO_DELETE

    user_id = update.effective_user.id
    if db.delete_personal_phrase(phrase_id, user_id):
        await update.message.reply_text(f"🗑️ Frase ID {phrase_id} apagada com sucesso!")
    else:
        await update.message.reply_text(f"❌ Não foi possível apagar a frase ID {phrase_id}. Verifique se o ID está correto.")
        logger.warning(f"Falha ao apagar frase ID {phrase_id} por {user_id}.")

    context.user_data.clear() # Limpa os dados do usuário para encerrar o diálogo
    return ConversationHandler.END


async def handle_personal_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lida com mensagens que podem ser frases personalizadas."""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    response_phrase = db.get_response_for_trigger(user_id, text)
    if response_phrase:
        await update.message.reply_text(escape_markdown(response_phrase, version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Frase personalizada acionada por {user_id}: '{text}' -> '{response_phrase}'.")
        return # Importante para não continuar processando com outros handlers

async def cancel_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo em andamento."""
    if update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.data == "help_category:main_menu":
            await send_main_help_menu(update, context, update.callback_query.message.message_id, update.callback_query.message.chat_id)
        else:
            await update.callback_query.edit_message_text(escape_markdown("Operação cancelada.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(escape_markdown("Operação cancelada. Estou à disposição para o que precisar!", version=2), parse_mode=ParseMode.MARKDOWN_V2)

    logger.info(f"Diálogo cancelado por {update.effective_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END