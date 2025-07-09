import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import db
from telegram.constants import ParseMode # Importado para ParseMode
from telegram.helpers import escape_markdown # Importado para escape_markdown


# Habilitar logging para este módulo
logger = logging.getLogger(__name__)

# Estados para ConversationHandler
SELECTING_LIST_NAME = 10
VIEWING_LIST_COMMAND_START = 11 # Para /verlista
SELECTING_LIST_TO_ADD_ITEM = 12 # Para /additem
GETTING_ITEM_TEXT = 13
SELECTING_LIST_TO_TOGGLE = 14 # Para /marcaritem
GETTING_ITEM_ID_TO_TOGGLE = 15
SELECTING_LIST_TO_REMOVE = 16 # Para /removeritem
GETTING_ITEM_ID_TO_REMOVE = 17
CONFIRM_DELETE_LIST = 18 # Para /apagarlista

# --- Funções Auxiliares ---
async def _send_list_selection_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_text: str) -> None:
    """Envia um teclado inline para seleção de lista."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id)

    if not lists:
        # Decide if we are in a callback query or message for proper response
        if update.callback_query:
            await update.callback_query.answer() # Acknowledge the callback
            await update.callback_query.edit_message_text(escape_markdown("Você não tem nenhuma lista. Use /novalista para criar uma!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text(escape_markdown("Você não tem nenhuma lista. Use /novalista para criar uma!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return

    keyboard = [[InlineKeyboardButton(lst['name'], callback_data=f"select_list:{lst['id']}")] for lst in lists]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Verifica se a chamada veio de um callback ou de um comando
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(escape_markdown(prompt_text, version=2), reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(escape_markdown(prompt_text, version=2), reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)


async def _send_list_items_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, list_id: int, list_name: str, action_prefix: str) -> None:
    """Envia um teclado inline com os itens de uma lista para uma ação específica."""
    user_id = update.effective_user.id
    items = db.get_list_items(list_id)

    if not items:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"A lista '{list_name}' está vazia.")
        return ConversationHandler.END

    keyboard = []
    message_text = f"Itens da lista '{escape_markdown(list_name, version=2)}':\\n\\n"
    for item in items:
        status_emoji = "✅" if item['is_completed'] else "❌"
        message_text += f"`{item['id']}` {status_emoji} {escape_markdown(item['text'], version=2)}\\n"
        keyboard.append([InlineKeyboardButton(f"{status_emoji} {item['text']}", callback_data=f"{action_prefix}:{item['id']}")])

    keyboard.append([InlineKeyboardButton("⬅️ Voltar para Listas", callback_data="view_lists_back")]) # Botão de voltar

    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )

# --- Handlers de Comando ---

async def new_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para criar uma nova lista."""
    await update.message.reply_text("Certo! Qual será o nome da sua nova lista? (Ex: 'Compras', 'Tarefas')")
    logger.info(f"Diálogo 'novalista' iniciado por {update.effective_user.id}.")
    return SELECTING_LIST_NAME

async def get_new_list_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da nova lista e tenta criá-la."""
    user_id = update.effective_user.id
    list_name = update.message.text.strip()

    if db.create_new_list(user_id, list_name):
        await update.message.reply_text(f"🎉 Lista '{list_name}' criada com sucesso! Use /additem para adicionar itens.")
        logger.info(f"Lista '{list_name}' criada por {user_id}.")
    else:
        await update.message.reply_text(f"❌ Não foi possível criar a lista '{list_name}'. Talvez você já tenha uma lista com esse nome?")
        logger.warning(f"Falha ao criar lista '{list_name}' por {user_id}.")

    return ConversationHandler.END

async def list_my_lists(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra todas as listas do usuário."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id)

    if not lists:
        await update.message.reply_text(escape_markdown("Você não tem nenhuma lista. Use /novalista para criar uma!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Nenhuma lista para {user_id}.")
        return

    message_text = "Suas listas:\\n\\n"
    keyboard = []
    for lst in lists:
        message_text += f"**ID:** `{lst['id']}` - {escape_markdown(lst['name'], version=2)}\\n"
        keyboard.append([InlineKeyboardButton(lst['name'], callback_data=f"view_list:{lst['id']}")])
    
    message_text += "\\nSelecione uma lista para ver os detalhes ou use /novalista para criar uma nova."

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Listas exibidas para {user_id}.")


async def view_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de visualização de uma lista específica."""
    await _send_list_selection_keyboard(update, context, "Selecione a lista que deseja ver:")
    return VIEWING_LIST_COMMAND_START

async def display_specific_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe os itens de uma lista selecionada."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(':')
    if len(data) == 2 and data[0] == "view_list":
        list_id = int(data[1])
        user_id = update.effective_user.id
        
        list_data = db.get_list_by_id(list_id, user_id)
        if not list_data:
            await query.edit_message_text("❌ Lista não encontrada ou não pertence a você.")
            logger.warning(f"Tentativa de ver lista {list_id} por {user_id} falhou: não encontrada/não pertence.")
            return ConversationHandler.END

        items = db.get_list_items(list_id)
        message_text = f"Items na lista '{escape_markdown(list_data['name'], version=2)}' (ID: `{list_id}`):\\n\\n"
        if not items:
            message_text += "Ainda não há itens nesta lista. Use /additem para adicionar um!"
        else:
            for item in items:
                status_emoji = "✅" if item['is_completed'] else "❌"
                message_text += f"`{item['id']}` {status_emoji} {escape_markdown(item['item_text'], version=2)}\\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Voltar para Listas", callback_data="view_lists_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lista ID {list_id} '{list_data['name']}' exibida para {user_id}.")
        return VIEWING_LIST_COMMAND_START # Permanece neste estado para permitir voltar ou outras ações
    else:
        logger.warning(f"Callback query inválida para display_specific_list: {query.data}")
        await query.edit_message_text(escape_markdown("Ocorreu um erro ao processar sua seleção. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END


# --- Add Item Handlers ---
async def add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar um item a uma lista."""
    await _send_list_selection_keyboard(update, context, "Para qual lista você quer adicionar um item?")
    return SELECTING_LIST_TO_ADD_ITEM

async def select_list_to_add_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista e pede o item."""
    query = update.callback_query
    await query.answer()
    
    list_id = int(query.data.split(':')[1])
    context.user_data['current_list_id'] = list_id
    
    list_name = db.get_list_by_id(list_id, update.effective_user.id)['name']
    await query.edit_message_text(f"Ok! O que você quer adicionar à lista '{list_name}'?")
    logger.info(f"Lista {list_id} selecionada para adicionar item por {update.effective_user.id}.")
    return GETTING_ITEM_TEXT

async def get_item_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o texto do item e o adiciona à lista."""
    user_id = update.effective_user.id
    list_id = context.user_data.get('current_list_id')
    item_text = update.message.text.strip()

    if not list_id:
        await update.message.reply_text("Ocorreu um erro. Por favor, comece de novo usando /additem.")
        logger.error(f"Erro: list_id não encontrado para {user_id} em get_item_text.")
        context.user_data.clear()
        return ConversationHandler.END

    if db.add_list_item(list_id, item_text):
        list_name = db.get_list_by_id(list_id, user_id)['name']
        await update.message.reply_text(f"Adicionado: '{item_text}' à lista '{list_name}'! ✅")
        logger.info(f"Item '{item_text}' adicionado à lista {list_id} por {user_id}.")
    else:
        await update.message.reply_text(f"❌ Não foi possível adicionar o item '{item_text}'.")
        logger.warning(f"Falha ao adicionar item '{item_text}' à lista {list_id} por {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END


# --- Toggle Item Handlers ---
async def toggle_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para marcar/desmarcar um item."""
    await _send_list_selection_keyboard(update, context, "De qual lista você quer marcar/desmarcar um item?")
    return SELECTING_LIST_TO_TOGGLE

async def select_list_to_toggle_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista e exibe os itens para alternar."""
    query = update.callback_query
    await query.answer()
    
    list_id = int(query.data.split(':')[1])
    context.user_data['current_list_id'] = list_id
    
    list_name = db.get_list_by_id(list_id, update.effective_user.id)['name']
    await _send_list_items_keyboard(update, context, list_id, list_name, "toggle_item")
    logger.info(f"Lista {list_id} selecionada para alternar item por {update.effective_user.id}.")
    return GETTING_ITEM_ID_TO_TOGGLE

async def get_item_id_to_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID do item e alterna seu status."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    if len(data) == 2 and data[0] == "toggle_item":
        item_id = int(data[1])
        user_id = update.effective_user.id
        list_id = context.user_data.get('current_list_id')

        if not list_id:
            await query.edit_message_text(escape_markdown("Ocorreu um erro. Por favor, comece de novo usando /marcaritem.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.error(f"Erro: list_id não encontrado para {user_id} em get_item_id_to_toggle.")
            context.user_data.clear()
            return ConversationHandler.END

        item = db.get_list_item_by_id(item_id, list_id)
        if not item:
            await query.edit_message_text(escape_markdown(f"❌ Item ID `{item_id}` não encontrado nesta lista.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            return SELECTING_LIST_TO_TOGGLE # Volta para o estado de seleção de lista se o item não for encontrado

        new_status = not item['is_completed']
        if db.toggle_list_item_status(item_id, new_status, list_id):
            status_text = "marcado" if new_status else "desmarcado"
            await query.edit_message_text(f"Item '{escape_markdown(item['item_text'], version=2)}' foi {status_text}! 👍", parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Item {item_id} alternado para {status_text} por {user_id} na lista {list_id}.")
        else:
            await query.edit_message_text(escape_markdown(f"❌ Não foi possível alterar o status do item ID `{item_id}`.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.warning(f"Falha ao alternar status do item {item_id} por {user_id} na lista {list_id}.")
    else:
        logger.warning(f"Dados de callback inválidos para toggle_item: {query.data}")
        await query.edit_message_text(escape_markdown("Ocorreu um erro. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)

    context.user_data.clear()
    return ConversationHandler.END


# --- Remove Item Handlers ---
async def remove_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para remover um item."""
    await _send_list_selection_keyboard(update, context, "De qual lista você quer remover um item?")
    return SELECTING_LIST_TO_REMOVE

async def select_list_to_remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista e exibe os itens para remover."""
    query = update.callback_query
    await query.answer()
    
    list_id = int(query.data.split(':')[1])
    context.user_data['current_list_id'] = list_id
    
    list_name = db.get_list_by_id(list_id, update.effective_user.id)['name']
    await _send_list_items_keyboard(update, context, list_id, list_name, "remove_item")
    logger.info(f"Lista {list_id} selecionada para remover item por {update.effective_user.id}.")
    return GETTING_ITEM_ID_TO_REMOVE

async def get_item_id_to_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID do item e o remove."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    if len(data) == 2 and data[0] == "remove_item":
        item_id = int(data[1])
        user_id = update.effective_user.id
        list_id = context.user_data.get('current_list_id')

        if not list_id:
            await query.edit_message_text(escape_markdown("Ocorreu um erro. Por favor, comece de novo usando /removeritem.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.error(f"Erro: list_id não encontrado para {user_id} em get_item_id_to_remove.")
            context.user_data.clear()
            return ConversationHandler.END

        item = db.get_list_item_by_id(item_id, list_id)
        if not item:
            await query.edit_message_text(escape_markdown(f"❌ Item ID `{item_id}` não encontrado nesta lista.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            return GETTING_ITEM_ID_TO_REMOVE # Permanece no estado para tentar outro ID

        if db.delete_list_item(item_id, list_id):
            await query.edit_message_text(f"🗑️ Item '{escape_markdown(item['item_text'], version=2)}' removido com sucesso!", parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Item {item_id} removido por {user_id} da lista {list_id}.")
        else:
            await query.edit_message_text(escape_markdown(f"❌ Não foi possível remover o item ID `{item_id}`.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.warning(f"Falha ao remover item {item_id} por {user_id} da lista {list_id}.")
    else:
        logger.warning(f"Dados de callback inválidos para remove_item: {query.data}")
        await query.edit_message_text(escape_markdown("Ocorreu um erro. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
    context.user_data.clear()
    return ConversationHandler.END


# --- Delete List Handlers ---
async def delete_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar uma lista."""
    await _send_list_selection_keyboard(update, context, "Qual lista você quer apagar permanentemente? (Isso apagará todos os itens também!)")
    return CONFIRM_DELETE_LIST

async def confirm_delete_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga a lista selecionada."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    if len(data) == 2 and data[0] == "select_list":
        list_id = int(data[1])
        user_id = update.effective_user.id
        list_name_obj = db.get_list_by_id(list_id, user_id)
        if not list_name_obj:
            await query.edit_message_text(escape_markdown("❌ Lista não encontrada ou não pertence a você.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            context.user_data.clear()
            return ConversationHandler.END
        
        list_name = list_name_obj['name'] # Obtém o nome da lista
        
        keyboard = [
            [InlineKeyboardButton("✅ Sim, Apagar Tudo", callback_data=f"confirm_delete_list:{list_id}")],
            [InlineKeyboardButton("❌ Não, Cancelar", callback_data="cancel_list_action")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            escape_markdown(f"Tem certeza que deseja apagar a lista '{list_name}' (ID: `{list_id}`)? Todos os itens nela serão perdidos. Esta ação é irreversível.", version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    elif len(data) == 2 and data[0] == "confirm_delete_list":
        list_id = int(data[1])
        user_id = update.effective_user.id
        list_name_obj = db.get_list_by_id(list_id, user_id)
        list_name = list_name_obj['name'] if list_name_obj else f"ID {list_id}" # Nome para log

        if db.delete_list(list_id, user_id):
            await query.edit_message_text(escape_markdown(f"🗑️ Lista '{list_name}' (ID: `{list_id}`) e todos os seus itens apagados com sucesso!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Lista ID {list_id} '{list_name}' deletada por {user_id}.")
        else:
            await query.edit_message_text(escape_markdown(f"❌ Não foi possível apagar a lista '{list_name}'. Verifique se ela pertence a você.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.warning(f"Falha ao deletar lista ID {list_id} '{list_name}' por {user_id}.")
    elif query.data == "cancel_list_action":
        await query.edit_message_text(escape_markdown("Operação de apagar lista cancelada.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text(escape_markdown("Ação desconhecida para apagar lista.", version=2), parse_mode=ParseMode.MARKDOWN_V2)

    context.user_data.clear()
    return ConversationHandler.END


async def handle_list_item_action_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Lida com callbacks de ações de itens de lista (como adicionar, marcar/desmarcar, remover).
    Este handler é geral e pode ser usado para retornar ao menu de listas.
    """
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "view_lists_back":
        # Chama a função para listar as listas novamente
        await list_my_lists(update, context) # Reutiliza a função existente
        return ConversationHandler.END # Encerra qualquer conversa ativa que tenha levado a este callback
    
    # Se não for "voltar", deixe que os ConversationHandlers específicos lidem com suas callbacks de item
    # Apenas loga para depuração se não for um callback de retorno
    logger.debug(f"Callback de ação de item de lista recebido: {data}")

async def cancel_list_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo de lista em andamento."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(escape_markdown("Operação de lista cancelada.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(escape_markdown("Operação de lista cancelada. Estou à disposição para o que precisar!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Diálogo de lista cancelado por {update.effective_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END