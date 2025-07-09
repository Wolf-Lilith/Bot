import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import db

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
            await update.callback_query.edit_message_text("Você não tem nenhuma lista. Use /novalista para criar uma!")
        else:
            await update.message.reply_text("Você não tem nenhuma lista. Use /novalista para criar uma!")
        return # Encerrar a função se não houver listas

    keyboard = []
    for list_obj in lists:
        keyboard.append([InlineKeyboardButton(list_obj['name'], callback_data=f"select_list:{list_obj['id']}")])
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Verifica se a chamada veio de um callback ou de um comando
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=prompt_text,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text=prompt_text,
            reply_markup=reply_markup
        )


# --- Handlers para Criação de Listas ---
async def new_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para criar uma nova lista."""
    await update.message.reply_text("Qual nome você gostaria de dar para a nova lista? (Ex: 'Compras', 'Tarefas de Casa')")
    logger.info(f"Usuário {update.effective_user.id} iniciou a criação de nova lista.")
    return SELECTING_LIST_NAME

async def create_new_list_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da nova lista e a cria no DB."""
    list_name = update.message.text.strip()
    user_id = update.effective_user.id

    if not list_name:
        await update.message.reply_text("O nome da lista não pode ser vazio. Por favor, digite um nome válido ou /cancelar.")
        return SELECTING_LIST_NAME

    list_id = db.create_list(user_id, list_name)
    if list_id:
        await update.message.reply_text(f"✅ Lista '{list_name}' criada com sucesso! (ID: `{list_id}`)")
        logger.info(f"Lista '{list_name}' (ID: {list_id}) criada por {user_id}.")
    else:
        await update.message.reply_text(f"❌ Não foi possível criar a lista '{list_name}'. Talvez você já tenha uma lista com esse nome.")
        logger.warning(f"Falha ao criar lista '{list_name}' para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Handlers para Visualizar Listas ---
async def list_my_lists(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista todas as listas do usuário."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id)

    if lists:
        text = "*Suas Listas:*\n\n"
        for list_obj in lists:
            text += f"• `{list_obj['id']}`: {list_obj['name']}\n"
        await update.message.reply_text(text, parse_mode='MarkdownV2')
        logger.info(f"Usuário {user_id} listou suas listas.")
    else:
        await update.message.reply_text("Você não tem nenhuma lista. Use /novalista para criar uma!")

async def view_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de visualização de uma lista, pedindo ao usuário para selecionar."""
    await _send_list_selection_keyboard(update, context, "Selecione a lista que deseja visualizar:")
    logger.info(f"Usuário {update.effective_user.id} iniciou a visualização de lista.")
    return VIEWING_LIST_COMMAND_START

async def view_specific_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Visualiza os itens de uma lista selecionada."""
    query = update.callback_query
    await query.answer()

    user_id = query.effective_user.id
    list_id = int(query.data.split(":")[1])
    
    list_name = db.get_list_name(list_id, user_id)
    if not list_name:
        await query.edit_message_text("❌ Lista não encontrada ou não pertence a você.")
        context.user_data.clear()
        return ConversationHandler.END

    items = db.get_list_items(list_id)

    text = f"📋 *Lista '{list_name}' (ID: `{list_id}`):*\n\n"
    if items:
        for item in items:
            status = "✅" if item['completed'] else "⏳"
            text += f"{status} `{item['id']}`: {item['text']}\n"
    else:
        text += "Nenhum item nesta lista. Use /additem para adicionar um!"
    
    await query.edit_message_text(text, parse_mode='MarkdownV2')
    logger.info(f"Usuário {user_id} visualizou itens da lista ID {list_id}.")

    context.user_data.clear() # Encerra o diálogo após mostrar a lista
    return ConversationHandler.END

# --- Handlers para Adicionar Itens à Lista ---
async def add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de adicionar um item, pedindo ao usuário para selecionar a lista."""
    await _send_list_selection_keyboard(update, context, "Selecione a lista à qual deseja adicionar um item:")
    logger.info(f"Usuário {update.effective_user.id} iniciou adição de item.")
    return SELECTING_LIST_TO_ADD_ITEM

async def add_item_to_selected_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a lista selecionada e pede o texto do item."""
    query = update.callback_query
    await query.answer()
    
    list_id = int(query.data.split(":")[1])
    user_id = query.effective_user.id

    list_name = db.get_list_name(list_id, user_id)
    if not list_name:
        await query.edit_message_text("❌ Lista não encontrada ou não pertence a você.")
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data['selected_list_id'] = list_id
    context.user_data['selected_list_name'] = list_name # Armazena o nome também para confirmação
    await query.edit_message_text(f"Certo! Você selecionou a lista '{list_name}'.\n\nQual item você quer adicionar a ela?")
    logger.info(f"Usuário {user_id} selecionou lista ID {list_id} para adicionar item.")
    return GETTING_ITEM_TEXT

async def get_item_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o texto do item e adiciona à lista."""
    item_text = update.message.text.strip()
    user_id = update.effective_user.id
    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name')

    if not item_text:
        await update.message.reply_text("O item não pode ser vazio. Por favor, digite o item ou /cancelar.")
        return GETTING_ITEM_TEXT
    
    if not list_id or not list_name:
        logger.error(f"Erro: list_id ou list_name não encontrados para user {user_id} no estado GETTING_ITEM_TEXT.")
        await update.message.reply_text("Ocorreu um erro. Por favor, tente novamente com /additem.")
        context.user_data.clear()
        return ConversationHandler.END

    item_id = db.add_list_item(list_id, item_text)
    if item_id:
        await update.message.reply_text(f"✅ Item '{item_text}' (ID: `{item_id}`) adicionado à lista '{list_name}' com sucesso!")
        logger.info(f"Item '{item_text}' (ID: {item_id}) adicionado à lista ID {list_id} por {user_id}.")
    else:
        await update.message.reply_text(f"❌ Não foi possível adicionar o item à lista '{list_name}'.")
        logger.warning(f"Falha ao adicionar item '{item_text}' à lista ID {list_id} por {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Handlers para Marcar/Desmarcar Itens ---
async def toggle_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de marcar/desmarcar item, pedindo ao usuário para selecionar a lista."""
    await _send_list_selection_keyboard(update, context, "Selecione a lista onde está o item que deseja marcar/desmarcar:")
    logger.info(f"Usuário {update.effective_user.id} iniciou marcação/desmarcação de item.")
    return SELECTING_LIST_TO_TOGGLE

async def get_item_id_to_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a lista selecionada e mostra os itens para o usuário marcar/desmarcar."""
    query = update.callback_query
    await query.answer()

    list_id = int(query.data.split(":")[1])
    user_id = query.effective_user.id

    list_name = db.get_list_name(list_id, user_id)
    if not list_name:
        await query.edit_message_text("❌ Lista não encontrada ou não pertence a você.")
        context.user_data.clear()
        return ConversationHandler.END
    
    context.user_data['list_id_for_toggle'] = list_id # Armazena o ID da lista
    
    items = db.get_list_items(list_id)
    if not items:
        await query.edit_message_text(f"A lista '{list_name}' não tem itens para marcar/desmarcar.")
        context.user_data.clear()
        return ConversationHandler.END

    text = f"📋 *Lista '{list_name}' (ID: `{list_id}`):*\n\n"
    keyboard = []
    for item in items:
        status = "✅" if item['completed'] else "⏳"
        text += f"{status} `{item['id']}`: {item['text']}\n"
        keyboard.append([InlineKeyboardButton(f"{status} ID {item['id']}: {item['text']}", callback_data=f"toggle_item:{item['id']}")])
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    logger.info(f"Usuário {user_id} visualizou itens para marcar/desmarcar na lista ID {list_id}.")
    return GETTING_ITEM_ID_TO_TOGGLE

async def toggle_item_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Marca/desmarca o status de um item da lista."""
    query = update.callback_query
    await query.answer()

    item_id = int(query.data.split(":")[1])
    list_id = context.user_data.get('list_id_for_toggle')
    user_id = query.effective_user.id

    if not list_id:
        logger.error(f"Erro: list_id não encontrada para user {user_id} no estado toggle_item_status.")
        await query.edit_message_text("Ocorreu um erro. Por favor, tente novamente com /marcaritem.")
        context.user_data.clear()
        return ConversationHandler.END

    if db.toggle_list_item_status(item_id, list_id):
        # Atualizar a mensagem para refletir o novo estado
        list_name = db.get_list_name(list_id, user_id)
        items = db.get_list_items(list_id)
        
        updated_text = f"📋 *Lista '{list_name}' (ID: `{list_id}`):*\n\n"
        for item in items:
            status = "✅" if item['completed'] else "⏳"
            updated_text += f"{status} `{item['id']}`: {item['text']}\n"
        
        await query.edit_message_text(updated_text, parse_mode='MarkdownV2')
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ Status do item `{item_id}` atualizado!")
        logger.info(f"Status do item ID {item_id} da lista ID {list_id} alternado por {user_id}.")
    else:
        await query.edit_message_text(f"❌ Não foi possível atualizar o status do item `{item_id}`.")
        logger.warning(f"Falha ao alternar status do item ID {item_id} da lista ID {list_id} por {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END


# --- Handlers para Remover Itens ---
async def remove_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de remover item, pedindo ao usuário para selecionar a lista."""
    await _send_list_selection_keyboard(update, context, "Selecione a lista de onde deseja remover um item:")
    logger.info(f"Usuário {update.effective_user.id} iniciou remoção de item.")
    return SELECTING_LIST_TO_REMOVE

async def get_item_id_to_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a lista selecionada e mostra os itens para o usuário remover."""
    query = update.callback_query
    await query.answer()

    list_id = int(query.data.split(":")[1])
    user_id = query.effective_user.id

    list_name = db.get_list_name(list_id, user_id)
    if not list_name:
        await query.edit_message_text("❌ Lista não encontrada ou não pertence a você.")
        context.user_data.clear()
        return ConversationHandler.END
    
    context.user_data['list_id_for_remove'] = list_id # Armazena o ID da lista
    
    items = db.get_list_items(list_id)
    if not items:
        await query.edit_message_text(f"A lista '{list_name}' não tem itens para remover.")
        context.user_data.clear()
        return ConversationHandler.END

    text = f"📋 *Lista '{list_name}' (ID: `{list_id}`):*\n\n"
    keyboard = []
    for item in items:
        status = "✅" if item['completed'] else "⏳"
        text += f"{status} `{item['id']}`: {item['text']}\n"
        keyboard.append([InlineKeyboardButton(f"Remover ID {item['id']}: {item['text']}", callback_data=f"remove_item:{item['id']}")])
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    logger.info(f"Usuário {user_id} visualizou itens para remover na lista ID {list_id}.")
    return GETTING_ITEM_ID_TO_REMOVE

async def remove_item_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove um item da lista."""
    query = update.callback_query
    await query.answer()

    item_id = int(query.data.split(":")[1])
    list_id = context.user_data.get('list_id_for_remove')
    user_id = query.effective_user.id

    if not list_id:
        logger.error(f"Erro: list_id não encontrada para user {user_id} no estado remove_item_from_list.")
        await query.edit_message_text("Ocorreu um erro. Por favor, tente novamente com /removeritem.")
        context.user_data.clear()
        return ConversationHandler.END

    if db.remove_list_item(item_id, list_id):
        # Atualizar a mensagem para refletir o novo estado (itens restantes)
        list_name = db.get_list_name(list_id, user_id)
        items = db.get_list_items(list_id)
        
        updated_text = f"✅ Item `{item_id}` removido da lista '{list_name}'.\n\n"
        updated_text += f"📋 *Lista '{list_name}' (ID: `{list_id}`):*\n\n"
        if items:
            for item in items:
                status = "✅" if item['completed'] else "⏳"
                updated_text += f"{status} `{item['id']}`: {item['text']}\n"
        else:
            updated_text += "A lista está vazia."

        await query.edit_message_text(updated_text, parse_mode='MarkdownV2')
        logger.info(f"Item ID {item_id} removido da lista ID {list_id} por {user_id}.")
    else:
        await query.edit_message_text(f"❌ Não foi possível remover o item `{item_id}`. Verifique se ele existe e pertence à lista.")
        logger.warning(f"Falha ao remover item ID {item_id} da lista ID {list_id} por {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Handlers para Apagar Listas Completas ---
async def delete_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de apagar uma lista inteira, pedindo confirmação."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id)

    if not lists:
        await update.message.reply_text("Você não tem nenhuma lista para apagar.")
        return ConversationHandler.END

    text = "⚠️ *ATENÇÃO:* Apagar uma lista removerá *todos* os seus itens.\n\n"
    text += "Selecione a lista que deseja apagar:\n\n"
    keyboard = []
    for list_obj in lists:
        text += f"• `{list_obj['id']}`: {list_obj['name']}\n"
        # O callback_data inclui o ID e o nome (encodado para evitar problemas com espaços)
        keyboard.append([InlineKeyboardButton(f"Apagar '{list_obj['name']}' (ID: {list_obj['id']})", callback_data=f"confirm_delete_list:{list_obj['id']}:{list_obj['name']}")])
    
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    logger.info(f"Usuário {user_id} iniciou o processo de apagar lista.")
    return CONFIRM_DELETE_LIST

async def confirm_delete_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga a lista selecionada."""
    query = update.callback_query
    await query.answer()

    user_id = query.effective_user.id

    if query.data.startswith("confirm_delete_list:"):
        parts = query.data.split(":")
        if len(parts) >= 3: # Deve ter pelo menos 'confirm_delete_list', ID e Nome (pode ter mais ':' no nome)
            list_id = int(parts[1])
            list_name = ":".join(parts[2:]) # Junta o resto para formar o nome original
        else:
            logger.warning(f"Dados de callback inválidos para confirmação de deleção: {query.data}.")
            context.user_data.clear()
            return ConversationHandler.END

        if db.delete_list(list_id, user_id):
            await query.edit_message_text(f"🗑️ Lista '{list_name}' (ID: `{list_id}`) e todos os seus itens apagados com sucesso!", parse_mode='MarkdownV2')
            logger.info(f"Lista ID {list_id} '{list_name}' deletada por {user_id}.")
        else:
            await query.edit_message_text(f"❌ Não foi possível apagar a lista '{list_name}'. Verifique se ela pertence a você.")
            logger.warning(f"Falha ao deletar lista ID {list_id} '{list_name}' por {user_id}.")
    elif query.data == "cancel_list_action":
        await query.edit_message_text("Operação de apagar lista cancelada.")
    else:
        await query.edit_message_text("Ação desconhecida para apagar lista.")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_list_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo de lista em andamento."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Operação de lista cancelada.")
    elif update.message:
        await update.message.reply_text("Operação de lista cancelada.")
    
    context.user_data.clear() # Limpa os dados do usuário
    return ConversationHandler.END