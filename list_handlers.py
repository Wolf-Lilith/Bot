# list_handlers.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Importado para ParseMode.MARKDOWN_V2
from telegram.helpers import escape_markdown # Importado para escapar texto Markdown

import db

# Usar o logger configurado em main.py
logger = logging.getLogger(__name__)

# Estados para ConversationHandler (valores altos para evitar conflitos)
SELECTING_LIST_NAME = 200
VIEWING_LIST_COMMAND_START = 201 # Para /verlista
SELECTING_LIST_TO_ADD_ITEM = 202 # Para /additem
GETTING_ITEM_TEXT = 203
SELECTING_LIST_TO_TOGGLE = 204 # Para /marcaritem
GETTING_ITEM_ID_TO_TOGGLE = 205
SELECTING_LIST_TO_REMOVE = 206 # Para /removeritem
GETTING_ITEM_ID_TO_REMOVE = 207
CONFIRM_DELETE_LIST = 208 # Para /apagarlista


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

    keyboard = []
    for list_id, list_name in lists:
        # Usar escape_markdown no list_name para evitar problemas se contiver caracteres especiais
        escaped_list_name = escape_markdown(list_name, version=2)
        # O callback_data deve ser simples, o parsing do ID será feito depois
        keyboard.append([InlineKeyboardButton(f"{escaped_list_name} (ID: {list_id})", callback_data=f"select_list_id:{list_id}")])
    
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            escape_markdown(prompt_text, version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            escape_markdown(prompt_text, version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )

# --- Criar Nova Lista ---

async def new_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para criar uma nova lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /novalista recebido de {user_id}.")
    await update.message.reply_text(escape_markdown("Qual o nome da nova lista (ex: Compras, Tarefas)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return SELECTING_LIST_NAME

async def get_list_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da nova lista e a salva."""
    user_id = update.effective_user.id
    list_name = update.message.text.strip()
    if not list_name:
        await update.message.reply_text(escape_markdown("O nome da lista não pode ser vazio. Tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return SELECTING_LIST_NAME

    if db.add_list(user_id, list_name):
        await update.message.reply_text(escape_markdown(f"🎉 Lista '{list_name}' criada com sucesso!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lista '{list_name}' criada por {user_id}.")
    else:
        await update.message.reply_text(escape_markdown(f"❌ Ops! Já existe uma lista com o nome '{list_name}'. Tente outro nome ou use /listas para ver as suas.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Falha ao criar lista '{list_name}' para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Ver Minhas Listas ---

async def list_my_lists(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vê todas as listas do usuário."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id)
    if lists:
        message_text = "📚 Suas listas:\n\n"
        for list_id, list_name in lists:
            message_text += f"**ID: {list_id}** - {escape_markdown(list_name, version=2)}\n"
        await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Listas exibidas para {user_id}.")
    else:
        await update.message.reply_text(escape_markdown("Você ainda não criou nenhuma lista. Use /novalista para começar!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Nenhuma lista encontrada para {user_id}.")

# --- Ver Itens de uma Lista ---

async def view_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para ver os itens de uma lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /verlista recebido de {user_id}.")
    await _send_list_selection_keyboard(update, context, "De qual lista você quer ver os itens?")
    return VIEWING_LIST_COMMAND_START

async def get_list_to_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a lista a ser visualizada (por ID de callback) e mostra seus itens."""
    query = update.callback_query
    await query.answer()
    list_id = int(query.data.split(':')[1]) # select_list_id:123 -> 123

    list_info = db.get_list_by_id(list_id, query.from_user.id)
    if not list_info:
        await query.edit_message_text(escape_markdown("Lista não encontrada ou não pertence a você.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    list_name = list_info[1]
    items = db.get_list_items(list_id)

    message_text = f"📝 Itens da lista '{escape_markdown(list_name, version=2)}':\n\n"
    if items:
        for item_id, item_text, is_completed in items:
            status = "✅" if is_completed else "❌"
            message_text += f"{status} **ID: {item_id}** - {escape_markdown(item_text, version=2)}\n"
    else:
        message_text += "A lista está vazia. Adicione itens com /additem!"
    
    keyboard = [[InlineKeyboardButton("↩️ Voltar às Listas", callback_data="view_lists_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Itens da lista '{list_name}' (ID: {list_id}) exibidos para {query.from_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END # Encerra a conversa após exibir os itens

# --- Adicionar Item à Lista ---

async def add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar um item a uma lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /additem recebido de {user_id}.")
    await _send_list_selection_keyboard(update, context, "Para qual lista você quer adicionar um item?")
    return SELECTING_LIST_TO_ADD_ITEM

async def handle_list_item_action_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com callbacks de seleção de lista para adicionar, marcar/desmarcar ou remover itens."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    # Callback para "voltar às listas" no menu de visualização
    if query.data == "view_lists_back":
        await list_my_lists(update, context) # Reutiliza a função de listar todas as listas
        return ConversationHandler.END # Volta para o estado inicial

    # Callback para cancelar
    if query.data == "cancel_list_action":
        return await cancel_list_dialog(update, context)

    # Lógica para selecionar a lista
    if query.data.startswith("select_list_id:"):
        list_id = int(query.data.split(':')[1])
        context.user_data['selected_list_id'] = list_id
        
        list_info = db.get_list_by_id(list_id, user_id)
        if not list_info:
            await query.edit_message_text(escape_markdown("Lista não encontrada ou não pertence a você.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            context.user_data.clear()
            return ConversationHandler.END
        
        list_name = list_info[1]
        current_state = context.user_data.get('current_list_flow_state') # Recupera o estado para onde ir depois da seleção

        if current_state == SELECTING_LIST_TO_ADD_ITEM:
            await query.edit_message_text(escape_markdown(f"Ok! Qual item você quer adicionar à lista '{escape_markdown(list_name, version=2)}'?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            return GETTING_ITEM_TEXT
        elif current_state == SELECTING_LIST_TO_TOGGLE:
            context.user_data['selected_list_name'] = list_name # Guarda o nome para exibição
            items = db.get_list_items(list_id)
            if not items:
                await query.edit_message_text(escape_markdown(f"A lista '{escape_markdown(list_name, version=2)}' está vazia. Não há itens para marcar/desmarcar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
                context.user_data.clear()
                return ConversationHandler.END
            
            message_text = f"Itens da lista '{escape_markdown(list_name, version=2)}':\n\n"
            for item_id, item_text, is_completed in items:
                status = "✅" if is_completed else "❌"
                message_text += f"{status} **ID: {item_id}** - {escape_markdown(item_text, version=2)}\n"
            message_text += "\nDigite o *ID* do item que deseja marcar/desmarcar."
            await query.edit_message_text(message_text, parse_mode=ParseMode.MARKDOWN_V2)
            return GETTING_ITEM_ID_TO_TOGGLE
        elif current_state == SELECTING_LIST_TO_REMOVE:
            context.user_data['selected_list_name'] = list_name # Guarda o nome para exibição
            items = db.get_list_items(list_id)
            if not items:
                await query.edit_message_text(escape_markdown(f"A lista '{escape_markdown(list_name, version=2)}' está vazia. Não há itens para remover.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
                context.user_data.clear()
                return ConversationHandler.END
            
            message_text = f"Itens da lista '{escape_markdown(list_name, version=2)}':\n\n"
            for item_id, item_text, is_completed in items:
                status = "✅" if is_completed else "❌"
                message_text += f"{status} **ID: {item_id}** - {escape_markdown(item_text, version=2)}\n"
            message_text += "\nDigite o *ID* do item que deseja remover."
            await query.edit_message_text(message_text, parse_mode=ParseMode.MARKDOWN_V2)
            return GETTING_ITEM_ID_TO_REMOVE
        elif current_state == CONFIRM_DELETE_LIST:
            # Isso é para quando o usuário seleciona a lista a ser apagada
            list_id_to_delete = list_id
            list_name_to_delete = list_name
            
            keyboard = [
                [InlineKeyboardButton("✅ Sim, Apagar Lista!", callback_data=f"confirm_delete_list_action:{list_id_to_delete}")],
                [InlineKeyboardButton("❌ Não, Cancelar", callback_data="cancel_list_action")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                escape_markdown(f"Tem certeza que deseja apagar a lista '{escape_markdown(list_name_to_delete, version=2)}' (ID: {list_id_to_delete}) e todos os seus itens? Esta ação é irreversível!", version=2),
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return CONFIRM_DELETE_LIST # Permanece no estado de confirmação
    
    # Lógica para confirmar a deleção final de uma lista
    if query.data.startswith("confirm_delete_list_action:"):
        list_id = int(query.data.split(':')[1])
        list_name = db.get_list_by_id(list_id, user_id)
        list_name_str = list_name[1] if list_name else "Desconhecida"

        if db.delete_list(list_id, user_id):
            await query.edit_message_text(escape_markdown(f"🗑️ Lista '{list_name_str}' (ID: `{list_id}`) e todos os seus itens apagados com sucesso!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Lista ID {list_id} '{list_name_str}' deletada por {user_id}.")
        else:
            await query.edit_message_text(escape_markdown(f"❌ Não foi possível apagar a lista '{list_name_str}'. Verifique se ela pertence a você.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.warning(f"Falha ao deletar lista ID {list_id} '{list_name_str}' por {user_id}.")
        
        context.user_data.clear()
        return ConversationHandler.END

    logger.warning(f"Callback de ação de lista inválido ou não tratado: {query.data}")
    await query.edit_message_text(escape_markdown("Ocorreu um erro ou a ação não é reconhecida. Por favor, tente novamente ou cancele.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END # Volta para o estado inicial em caso de erro

async def get_item_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o texto do item e o adiciona à lista."""
    user_id = update.effective_user.id
    item_text = update.message.text.strip()
    list_id = context.user_data.get('selected_list_id')

    if not item_text:
        await update.message.reply_text(escape_markdown("O item não pode ser vazio. Por favor, digite o item.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_ITEM_TEXT

    if list_id and db.add_list_item(list_id, item_text):
        list_info = db.get_list_by_id(list_id, user_id)
        list_name = list_info[1] if list_info else "lista desconhecida"
        await update.message.reply_text(
            escape_markdown(f"🎉 Item '{item_text}' adicionado à lista '{list_name}' com sucesso!", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Item '{item_text}' adicionado à lista {list_id} por {user_id}.")
    else:
        await update.message.reply_text(escape_markdown("❌ Ops! Não foi possível adicionar o item. A lista pode não existir.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Falha ao adicionar item '{item_text}' à lista {list_id} para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Marcar/Desmarcar Item ---

async def toggle_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para marcar/desmarcar um item da lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /marcaritem recebido de {user_id}.")
    context.user_data['current_list_flow_state'] = SELECTING_LIST_TO_TOGGLE # Para handle_list_item_action_callbacks
    await _send_list_selection_keyboard(update, context, "De qual lista você quer marcar/desmarcar um item?")
    return SELECTING_LIST_TO_TOGGLE

async def get_item_id_to_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID do item a ser marcado/desmarcado e o processa."""
    user_id = update.effective_user.id
    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name', "lista")
    
    try:
        item_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, insira um ID de item válido (um número).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_ITEM_ID_TO_TOGGLE

    if list_id and db.toggle_list_item(item_id, list_id):
        await update.message.reply_text(
            escape_markdown(f"✅ Item ID **{item_id}** da lista '{list_name}' marcado/desmarcado com sucesso!", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Item ID {item_id} da lista {list_id} alternado por {user_id}.")
    else:
        await update.message.reply_text(
            escape_markdown(f"❌ Não foi possível marcar/desmarcar o item ID **{item_id}** da lista '{list_name}'. Verifique se o ID está correto.", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Falha ao alternar item ID {item_id} da lista {list_id} para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Remover Item ---

async def remove_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para remover um item da lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /removeritem recebido de {user_id}.")
    context.user_data['current_list_flow_state'] = SELECTING_LIST_TO_REMOVE # Para handle_list_item_action_callbacks
    await _send_list_selection_keyboard(update, context, "De qual lista você quer remover um item?")
    return SELECTING_LIST_TO_REMOVE

async def get_item_id_to_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID do item a ser removido e o processa."""
    user_id = update.effective_user.id
    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name', "lista")

    try:
        item_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, insira um ID de item válido (um número).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_ITEM_ID_TO_REMOVE

    if list_id and db.remove_list_item(item_id, list_id):
        await update.message.reply_text(
            escape_markdown(f"🗑️ Item ID **{item_id}** removido da lista '{list_name}' com sucesso!", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Item ID {item_id} removido da lista {list_id} por {user_id}.")
    else:
        await update.message.reply_text(
            escape_markdown(f"❌ Não foi possível remover o item ID **{item_id}** da lista '{list_name}'. Verifique se o ID está correto.", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Falha ao remover item ID {item_id} da lista {list_id} para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Apagar Lista ---

async def delete_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar uma lista inteira."""
    user_id = update.effective_user.id
    logger.info(f"Comando /apagarlista recebido de {user_id}.")
    context.user_data['current_list_flow_state'] = CONFIRM_DELETE_LIST # Para handle_list_item_action_callbacks
    await _send_list_selection_keyboard(update, context, "Qual lista você quer apagar?")
    return CONFIRM_DELETE_LIST # Vai para o estado de confirmação (que é o mesmo handler)

# A função `handle_list_item_action_callbacks` agora também lida com a confirmação de deleção
# Ela é chamada novamente após a seleção da lista a ser apagada para pedir a confirmação.

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