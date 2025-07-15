import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import ContextTypes, ConversationHandler 
from telegram.constants import ParseMode 
import logging
import db
import re
import list_handlers 
import reminders_handlers 

# Usar o logger configurado em main.py
logger = logging.getLogger(__name__)

# --- Estados para ConversationHandler (certifique-se de que são únicos globalmente) ---
GETTING_TRIGGER_PHRASE = 0
GETTING_RESPONSE_PHRASE = 1
AWAIT_NEXT_PHRASE_ACTION = 3
AWAIT_NEXT_DELETE_ACTION = 4

# --- Handlers de Comandos e Funções Auxiliares ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia o bot e cumprimenta o usuário."""
    user = update.effective_user
    if update.effective_message:
        await update.effective_message.reply_html(
            f"Olá, {user.mention_html()}! Sou a Lilith, sua assistente pessoal.\n" # Alterado de <br> para \n
            "Use /ajuda para ver o que eu posso fazer!"
        )
    logger.info(f"Comando /start recebido de {user.id}.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o menu de ajuda principal."""
    user_id = update.effective_user.id
    await send_main_help_menu(update, context)
    logger.info(f"Comando /ajuda recebido de {user_id}.")

async def send_main_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Função auxiliar para enviar/editar o menu de ajuda principal."""
    keyboard = [
        [InlineKeyboardButton("Frases Personalizadas", callback_data="help_category:phrases")],
        [InlineKeyboardButton("Listas", callback_data="help_category:lists")],
        [InlineKeyboardButton("Lembretes", callback_data="help_category:reminders")],
        [InlineKeyboardButton("Comandos Gerais", callback_data="help_category:general")],
        [InlineKeyboardButton("💰 Contas Financeiras", callback_data="accounts_action:open_menu")], 
        [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    help_message_text = "Selecione uma categoria de ajuda para ver os comandos:"

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            await query.edit_message_text(
                text=help_message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML 
            )
        except Exception as e: 
            logger.warning(f"Erro ao editar mensagem (send_main_help_menu): {e}. Tentando enviar nova mensagem.")
            await query.message.reply_text(
                text=help_message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML 
            )
        logger.info(f"Menu de ajuda editado/enviado via callback para {query.from_user.id}.")
    elif update.message:
        await update.message.reply_text(
            text=help_message_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML 
        )
        logger.info(f"Menu de ajuda enviado via comando para {update.effective_user.id}.")
    else:
        logger.warning("send_main_help_menu foi chamado sem update.message ou update.callback_query.")

async def send_help_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o menu de ajuda para categorias específicas."""
    query = update.callback_query
    await query.answer()
    category = query.data.split(':')[1]

    category_message = ""
    category_keyboard = []

    if category == "phrases":
        category_message = (
            "⚙️ <b>Frases Personalizadas:</b>\n" # Alterado de <br> para \n
            "Eu responderei automaticamente quando vir a sua frase de gatilho!\n\n" # Alterado de <br> para \n
            "Selecione uma ação:"
        )
        category_keyboard = [
            [InlineKeyboardButton("➕ Adicionar Frase", callback_data="command:/addfrase")],
            [InlineKeyboardButton("📚 Minhas Frases", callback_data="command:/minhasfrases")],
            [InlineKeyboardButton("🗑️ Apagar Frase", callback_data="command:/apagarfrase")],
        ]
    elif category == "lists":
        await list_handlers.list_my_lists_menu(update, context)
        logger.info(f"Menu de ajuda da categoria 'lists' direcionado para list_handlers.list_my_lists_menu para {query.from_user.id}.")
        return
    elif category == "reminders":
        await reminders_menu(update, context) 
        logger.info(f"Menu de ajuda da categoria 'reminders' direcionado para reminders_menu para {query.from_user.id}.")
        return
    elif category == "general":
        category_message = (
            "✨ <b>Comandos Gerais:</b>\n" # Alterado de <br> para \n
            "Estou sempre aprendendo e disponível para te ajudar! Selecione uma ação:"
        )
        category_keyboard = [
            [InlineKeyboardButton("👋 Iniciar Conversa", callback_data="show_command:/start")],
            [InlineKeyboardButton("❓ Menu de Ajuda", callback_data="show_command:/ajuda")],
            [InlineKeyboardButton("❌ Cancelar Operação", callback_data="cancel_dialog_action")],
        ]
    elif category == "accounts":
        category_message = (
            "💰 <b>Contas Financeiras:</b>\n" # Alterado de <br> para \n
            "Mantenha suas finanças organizadas! Selecione uma ação:"
        )
        category_keyboard = [
            [InlineKeyboardButton("Abrir Menu de Contas", callback_data="accounts_action:open_menu")], 
        ]
        logger.info(f"Menu de ajuda da categoria 'accounts' exibido para {query.from_user.id}.") 
    elif category == "main_menu":
        await send_main_help_menu(update, context)
        return

    if category != "main_menu":
        category_keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="help_category:main_menu")])
    reply_markup = InlineKeyboardMarkup(category_keyboard)

    try:
        await query.edit_message_text(
            text=category_message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML 
        )
    except Exception as e:
        logger.warning(f"Erro ao editar mensagem para categoria '{category}': {e}. Tentando enviar nova mensagem.")
        await query.message.reply_text(
            text=category_message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML 
        )

    logger.info(f"Menu de ajuda da categoria '{category}' enviado para {query.from_user.id}.")

async def reminders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe o menu principal de lembretes."""
    keyboard = [
        [InlineKeyboardButton("➕ Adicionar Lembrete", callback_data="command:/add_lembrete")],
        [InlineKeyboardButton("📚 Ver Meus Lembretes", callback_data="command:/ver_lembretes")],
        [InlineKeyboardButton("🗑️ Apagar Lembrete", callback_data="command:/apagar_lembrete")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="help_category:main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = "⏰ <b>Lembretes:</b>\nNunca mais esqueça de nada importante! Selecione uma ação:" # Alterado de <br> para \n
    
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML 
            )
        except Exception as e:
            logger.warning(f"Erro ao editar mensagem (reminders_menu callback): {e}. Tentando enviar nova mensagem.")
            await update.callback_query.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML 
            )
    elif update.message:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML 
        )
    logger.info(f"Menu de lembretes exibido para {update.effective_user.id}.")


async def show_command_and_return_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mostra o comando associado ao botão e volta ao menu principal."""
    query = update.callback_query
    await query.answer()

    command_to_show = query.data.split(':')[1]

    await query.edit_message_text(
        f"O Comando para essa ação é <code>{html.escape(command_to_show)}</code>. Obrigado por perguntar!",
        parse_mode=ParseMode.HTML 
    )

    keyboard = [
        [InlineKeyboardButton("Frases Personalizadas", callback_data="help_category:phrases")],
        [InlineKeyboardButton("Listas", callback_data="help_category:lists")],
        [InlineKeyboardButton("Lembretes", callback_data="help_category:reminders")],
        [InlineKeyboardButton("Comandos Gerais", callback_data="help_category:general")],
        [InlineKeyboardButton("💰 Contas Financeiras", callback_data="accounts_action:open_menu")], 
        [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        "Selecione uma categoria de ajuda para ver os comandos:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML 
    )

    logger.info(f"Usuário {query.from_user.id} solicitou e visualizou o comando '{command_to_show}' e retornou ao menu principal.")
    return ConversationHandler.END

async def new_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar uma nova frase."""
    user_id = update.effective_user.id
    logger.info(f"Comando /addfrase recebido de {user_id}.")

    if update.effective_message:
        await update.effective_message.reply_html("Qual frase ou palavra deve <b>ativar</b> a minha resposta?", parse_mode=ParseMode.HTML) 

    return GETTING_TRIGGER_PHRASE

async def get_trigger_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de gatilho e pede a frase de resposta."""
    user_id = update.effective_user.id
    trigger_phrase = update.message.text.strip()
    if not trigger_phrase:
        await update.message.reply_text("A frase de gatilho não pode ser vazia. Tente novamente.", parse_mode=ParseMode.HTML) 
        return GETTING_TRIGGER_PHRASE

    context.user_data['trigger_phrase'] = trigger_phrase
    logger.info(f"Gatilho '{trigger_phrase}' recebido de {user_id}.")
    await update.message.reply_text(f"Entendi! E qual deve ser a minha <b>resposta</b> para '<code>{html.escape(trigger_phrase)}</code>'?", parse_mode=ParseMode.HTML) 
    return GETTING_RESPONSE_PHRASE

async def get_response_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de resposta e salva a frase personalizada."""
    user_id = update.effective_user.id
    response_phrase = update.message.text.strip()
    trigger_phrase = context.user_data.get('trigger_phrase')

    if not response_phrase:
        await update.message.reply_text("A frase de resposta não pode ser vazia. Tente novamente.", parse_mode=ParseMode.HTML) 
        return GETTING_RESPONSE_PHRASE

    if db.add_personal_phrase(user_id, trigger_phrase, response_phrase):
        confirmation_message = (
            f"🎉 Frase personalizada adicionada!\n" # Alterado de <br> para \n
            f"Quando você disser: '<code>{html.escape(trigger_phrase)}</code>'\n" # Alterado de <br> para \n
            f"Eu responderei: '<code>{html.escape(response_phrase)}</code>'"
        )
        await update.message.reply_text(confirmation_message, parse_mode=ParseMode.HTML) 
        logger.info(f"Frase personalizada adicionada por {user_id}: '{trigger_phrase}' -> '{response_phrase}'.")

        keyboard = [
            [InlineKeyboardButton("➕ Adicionar Outra Frase", callback_data="add_another_phrase")],
            [InlineKeyboardButton("🏠 Voltar ao Menu Principal", callback_data="help_category:main_menu")],
            [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML) 

        context.user_data.clear()
        return AWAIT_NEXT_PHRASE_ACTION

    else:
        await update.message.reply_text(
            "❌ Ops! Já existe uma frase com esse gatilho. Use /minhasfrases para ver suas frases.",
            parse_mode=ParseMode.HTML 
        )
        context.user_data.clear()
        return ConversationHandler.END

async def handle_next_phrase_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "add_another_phrase":
        await query.edit_message_text("Ótimo! Qual a próxima frase ou palavra que deve <b>ativar</b> a minha resposta?", parse_mode=ParseMode.HTML) 
        return GETTING_TRIGGER_PHRASE
    elif action == "help_category:main_menu":
        await send_main_help_menu(update, context)
        return ConversationHandler.END
    elif action == "cancel_dialog_action":
        await cancel_dialog(update, context)
        return ConversationHandler.END

    return ConversationHandler.END

async def view_my_phrases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vê as frases personalizadas do usuário."""
    user_id = update.effective_user.id
    phrases = db.get_user_personal_phrases(user_id)
    message_text = ""
    if phrases:
        message_text = "📚 Suas frases personalizadas:\n\n" # Alterado de <br> para \n
        for phrase_id, trigger, response in phrases:
            escaped_trigger = html.escape(trigger)
            escaped_response = html.escape(response)
            message_text += f"<b>ID: {phrase_id}</b>\n<code>Gatilho</code>: {escaped_trigger}\n<code>Resposta</code>: {escaped_response}\n\n" # Alterado de <br> para \n

        if update.effective_message:
            try:
                await update.effective_message.reply_text(message_text, parse_mode=ParseMode.HTML) 
            except Exception as e:
                logger.warning(f"Erro ao enviar/editar mensagem de frases (view_my_phrases): {e}. Tentando enviar nova mensagem.")
                await update.effective_message.reply_text(message_text, parse_mode=ParseMode.HTML) 
        logger.info(f"Frases personalizadas exibidas para {user_id}.")
    else:
        no_phrases_text = "Você ainda não adicionou nenhuma frase personalizada. Use /addfrase para adicionar uma!"
        if update.effective_message:
            try:
                await update.effective_message.reply_text(no_phrases_text, parse_mode=ParseMode.HTML) 
            except Exception as e:
                logger.warning(f"Erro ao enviar/editar mensagem de frases vazias (view_my_phrases): {e}. Tentando enviar nova mensagem.")
                await update.effective_message.reply_text(no_phrases_text, parse_mode=ParseMode.HTML) 
        logger.info(f"Nenhuma frase personalizada encontrada para {user_id}.")

    keyboard = [
        [InlineKeyboardButton("🏠 Voltar ao Menu Principal", callback_data="help_category:main_menu")],
        [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        try:
            await update.callback_query.message.edit_reply_markup(reply_markup)
        except Exception as e:
            logger.warning(f"Não foi possível editar o teclado da mensagem de callback para {update.callback_query.from_user.id}: {e}. Enviando nova mensagem de opções.")
            await update.callback_query.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML) 
    elif update.message:
        await update.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML) 
    logger.info(f"Menu de opções após listar frases enviado para {user_id}.")

async def delete_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar uma frase, exibindo-as como botões."""
    user_id = update.effective_user.id
    logger.info(f"Comando /apagarfrase recebido de {user_id}.")
    phrases = db.get_user_personal_phrases(user_id)
    if not phrases:
        no_phrases_text = "Você não tem nenhuma frase personalizada para apagar."
        if update.effective_message:
            await update.effective_message.reply_text(no_phrases_text, parse_mode=ParseMode.HTML) 
        return ConversationHandler.END

    message_text = "📚 Suas frases personalizadas:\n\n" \
                   "Selecione a frase que você deseja apagar:"

    keyboard = []
    for phrase_id, trigger, response in phrases:
        button_text = f"ID {phrase_id}: \"{trigger}\" -> \"{response}\""
        if len(button_text) > 64:
            button_text = button_text[:61] + "..."
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_phrase_id:{phrase_id}")])

    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_dialog_action")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML 
            )
        except Exception as e:
            logger.warning(f"Erro ao editar mensagem (delete_phrase_start callback): {e}. Tentando enviar nova mensagem.")
            await update.callback_query.message.reply_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML 
            )
    elif update.message:
        await update.message.reply_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML 
        )

    return AWAIT_NEXT_DELETE_ACTION

async def delete_phrase_select_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    phrase_id_str = query.data.split(':')[1]
    try:
        phrase_id = int(phrase_id_str)
    except ValueError:
        await query.edit_message_text("ID de frase inválido. Por favor, tente novamente.", parse_mode=ParseMode.HTML) 
        return ConversationHandler.END

    user_id = query.from_user.id

    if db.delete_personal_phrase(phrase_id, user_id):
        confirmation_message = f"🗑️ Frase ID <b>{phrase_id}</b> apagada com sucesso!"
        logger.info(f"Frase ID {phrase_id} apagada por {user_id}.")
    else:
        confirmation_message = f"❌ Não foi possível apagar a frase ID <b>{phrase_id}</b>. Verifique se o ID está correto ou se você tem permissão."
        logger.warning(f"Falha ao apagar frase ID {phrase_id} por {user_id}.")

    await query.edit_message_text(confirmation_message, parse_mode=ParseMode.HTML) 

    keyboard = [
        [InlineKeyboardButton("🗑️ Apagar Outra Frase", callback_data="delete_another_phrase")],
        [InlineKeyboardButton("🏠 Voltar ao Menu Principal", callback_data="help_category:main_menu")],
        [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML) 

    context.user_data.clear()
    return AWAIT_NEXT_DELETE_ACTION

async def handle_next_delete_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "delete_another_phrase":
        return await delete_phrase_start(update, context)
    elif action == "help_category:main_menu":
        await send_main_help_menu(update, context)
        return ConversationHandler.END
    elif action == "cancel_dialog_action":
        await cancel_dialog(update, context)
        return ConversationHandler.END

    return ConversationHandler.END

async def handle_personal_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lida com mensagens que podem ser frases personalizadas."""
    if update.message and update.message.text:
        text = update.message.text.strip()
        user_id = update.effective_user.id

        response_phrase = db.get_response_for_trigger(user_id, text)
        if response_phrase:
            await update.message.reply_text(html.escape(response_phrase), parse_mode=ParseMode.HTML) 
            logger.info(f"Frase personalizada acionada por {user_id}: '{text}' -> '{response_phrase}'.")
            return

async def cancel_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo em andamento ou encerra uma operação."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Operação cancelada.", parse_mode=ParseMode.HTML) 
    elif update.message:
        await update.message.reply_text("Operação cancelada. Estou à disposição para o que precisar!", parse_mode=ParseMode.HTML) 

    logger.info(f"Diálogo/Operação cancelada por {update.effective_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END