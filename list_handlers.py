# list_handlers.py (manter a versão anterior que te enviei)

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import db 

logger = logging.getLogger(__name__)

# --- Estados da Conversa para Listas ---
SELECTING_LIST_NAME = 1
VIEWING_LIST_COMMAND_START = 2
SELECTING_LIST_TO_ADD_ITEM = 3
GETTING_ITEM_TEXT = 4
SELECTING_LIST_TO_TOGGLE = 5
GETTING_ITEM_ID_TO_TOGGLE = 6
SELECTING_LIST_TO_REMOVE = 7
GETTING_ITEM_ID_TO_REMOVE = 8
CONFIRM_DELETE_LIST = 9

# --- Funções Auxiliares ---

async def _send_list_selection_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    """Envia um teclado inline com as listas do usuário para seleção."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id) 

    if not lists:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Você ainda não tem nenhuma lista. Crie uma com /novalista!")
        else:
            await update.message.reply_text("Você ainda não tem nenhuma lista. Crie uma com /novalista!")
        return ConversationHandler.END

    keyboard = []
    for list_id, list_name in lists:
        keyboard.append([InlineKeyboardButton(list_name, callback_data=f"select_list_id:{list_id}")])

    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

# --- Handlers de Início de Conversa ---

async def new_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para criar uma nova lista."""
    logger.info(f"Comando /novalista recebido de {update.effective_user.id}.")
    await update.message.reply_text("Qual o nome da nova lista que você quer criar?")
    return SELECTING_LIST_NAME

async def get_list_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da nova lista e a cria."""
    user_id = update.effective_user.id
    list_name = update.message.text.strip()
    logger.info(f"Usuário {user_id} informou o nome da lista: {list_name}")

    if not list_name:
        await update.message.reply_text("O nome da lista não pode ser vazio. Por favor, digite um nome válido.")
        return SELECTING_LIST_NAME

    if db.add_list(user_id, list_name): 
        await update.message.reply_text(f"Lista '{list_name}' criada com sucesso! 🎉")
    else:
        await update.message.reply_text(f"Já existe uma lista com o nome '{list_name}'. Por favor, escolha outro nome.")
    return ConversationHandler.END

async def list_my_lists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todas as listas do usuário."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id)

    if not lists:
        await update.message.reply_text("Você ainda não tem nenhuma lista. Crie uma com /novalista!")
        return

    message = "Suas listas:\n\n"
    for list_id, list_name in lists:
        message += f"• {list_name} (ID: {list_id})\n"
    await update.message.reply_text(message)

async def view_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para visualizar os itens de uma lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /verlista recebido de {user_id}.")
    await _send_list_selection_keyboard(update, context, "Qual lista você quer visualizar?")
    return VIEWING_LIST_COMMAND_START

async def get_list_to_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista para visualizar e mostra seus itens."""
    query = update.callback_query
    user_id = update.effective_user.id 
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith("select_list_id:"):
        list_id = int(callback_data.split(":")[1])
        
        list_info = db.get_list_by_id(list_id, user_id) 
        if not list_info:
            await query.edit_message_text("Lista não encontrada ou você não tem permissão para acessá-la. Por favor, tente novamente.")
            return ConversationHandler.END
        list_name = list_info[1] 

        items = db.get_list_items(list_id)
        message = f"Itens da lista '{list_name}':\n\n"
        if not items:
            message += "Esta lista está vazia. Adicione itens com /additem!"
        else:
            for item_id, item_text, completed in items:
                status_emoji = "✅" if completed else "⬜"
                message += f"{status_emoji} {item_text} (ID: {item_id})\n"
        
        keyboard = [[InlineKeyboardButton("Voltar às Listas", callback_data="view_lists_back")],
                    [InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=message, reply_markup=reply_markup)
        return VIEWING_LIST_COMMAND_START 
    elif callback_data == "view_lists_back":
        await _send_list_selection_keyboard(update, context, "Qual lista você quer visualizar?")
        return VIEWING_LIST_COMMAND_START
    elif callback_data == "cancel_list_action":
        await cancel_list_dialog(update, context)
        return ConversationHandler.END
    else:
        logger.warning(f"Callback de visualização de lista inválido ou não tratado: {callback_data}")
        await query.edit_message_text("Ocorreu um erro. Por favor, tente novamente.")
        return ConversationHandler.END


# --- Adicionar Item à Lista ---

async def add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar um item a uma lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /additem recebido de {user_id}.")
    context.user_data['current_list_flow_state'] = SELECTING_LIST_TO_ADD_ITEM 
    await _send_list_selection_keyboard(update, context, "Para qual lista você quer adicionar um item?")
    return SELECTING_LIST_TO_ADD_ITEM

async def get_item_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o texto do item e o adiciona à lista selecionada."""
    user_id = update.effective_user.id
    item_text = update.message.text.strip()
    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name')

    if not list_id or not list_name:
        await update.message.reply_text("Parece que a lista não foi selecionada corretamente. Por favor, tente novamente com /additem.")
        return ConversationHandler.END

    if not item_text:
        await update.message.reply_text("O item não pode ser vazio. Por favor, digite o texto do item.")
        return GETTING_ITEM_TEXT

    if db.add_list_item(list_id, item_text): 
        await update.message.reply_text(f"Item '{item_text}' adicionado à lista '{list_name}' com sucesso! ✅")
    else:
        await update.message.reply_text("Ocorreu um erro ao adicionar o item. Por favor, tente novamente.")
    
    # Limpa os dados da conversa
    if 'selected_list_id' in context.user_data:
        del context.user_data['selected_list_id']
    if 'selected_list_name' in context.user_data:
        del context.user_data['selected_list_name']
    if 'current_list_flow_state' in context.user_data: 
        del context.user_data['current_list_flow_state']

    return ConversationHandler.END


# --- Marcar/Desmarcar Item ---

async def toggle_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para marcar/desmarcar um item da lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /marcaritem recebido de {user_id}.")
    context.user_data['current_list_flow_state'] = SELECTING_LIST_TO_TOGGLE
    await _send_list_selection_keyboard(update, context, "De qual lista você quer marcar/desmarcar um item?")
    return SELECTING_LIST_TO_TOGGLE

async def get_item_id_to_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID do item e o marca/desmarca."""
    user_id = update.effective_user.id
    item_id_str = update.message.text.strip()
    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name')

    if not list_id or not list_name:
        await update.message.reply_text("Parece que a lista não foi selecionada corretamente. Por favor, tente novamente com /marcaritem.")
        return ConversationHandler.END

    try:
        item_id = int(item_id_str)
    except ValueError:
        await update.message.reply_text("Por favor, digite um ID de item válido (um número).")
        return GETTING_ITEM_ID_TO_TOGGLE

    item_info = db.get_list_item_by_id(item_id) 
    if not item_info or item_info[0] != list_id: 
        await update.message.reply_text("Item não encontrado nesta lista ou não pertence a ela. Por favor, verifique o ID e tente novamente.")
        return GETTING_ITEM_ID_TO_TOGGLE
    
    item_text = item_info[1]
    current_status = item_info[2]
    new_status = not current_status

    if db.toggle_list_item(item_id, list_id): 
        status_text = "marcado como completo ✅" if new_status else "desmarcado ⬜"
        await update.message.reply_text(f"Item '{item_text}' na lista '{list_name}' foi {status_text} com sucesso!")
    else:
        await update.message.reply_text("Ocorreu um erro ao atualizar o item. Por favor, tente novamente.")

    # Limpa os dados da conversa
    if 'selected_list_id' in context.user_data:
        del context.user_data['selected_list_id']
    if 'selected_list_name' in context.user_data:
        del context.user_data['selected_list_name']
    if 'current_list_flow_state' in context.user_data:
        del context.user_data['current_list_flow_state']

    return ConversationHandler.END


# --- Remover Item ---

async def remove_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para remover um item da lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /removeritem recebido de {user_id}.")
    context.user_data['current_list_flow_state'] = SELECTING_LIST_TO_REMOVE
    await _send_list_selection_keyboard(update, context, "De qual lista você quer remover um item?")
    return SELECTING_LIST_TO_REMOVE

async def get_item_id_to_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID do item e o remove."""
    user_id = update.effective_user.id
    item_id_str = update.message.text.strip()
    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name')

    if not list_id or not list_name:
        await update.message.reply_text("Parece que a lista não foi selecionada corretamente. Por favor, tente novamente com /removeritem.")
        return ConversationHandler.END

    try:
        item_id = int(item_id_str)
    except ValueError:
        await update.message.reply_text("Por favor, digite um ID de item válido (um número).")
        return GETTING_ITEM_ID_TO_REMOVE

    item_info = db.get_list_item_by_id(item_id) 
    if not item_info or item_info[0] != list_id:
        await update.message.reply_text("Item não encontrado nesta lista ou não pertence a ela. Por favor, verifique o ID e tente novamente.")
        return GETTING_ITEM_ID_TO_REMOVE

    if db.remove_list_item(item_id, list_id): 
        await update.message.reply_text(f"Item '{item_info[1]}' removido da lista '{list_name}' com sucesso! 🗑️")
    else:
        await update.message.reply_text("Ocorreu um erro ao remover o item. Por favor, tente novamente.")

    # Limpa os dados da conversa
    if 'selected_list_id' in context.user_data:
        del context.user_data['selected_list_id']
    if 'selected_list_name' in context.user_data:
        del context.user_data['selected_list_name']
    if 'current_list_flow_state' in context.user_data:
        del context.user_data['current_list_flow_state']

    return ConversationHandler.END


# --- Apagar Lista ---

async def delete_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar uma lista inteira."""
    user_id = update.effective_user.id
    logger.info(f"Comando /apagarlista recebido de {user_id}.")
    context.user_data['current_list_flow_state'] = CONFIRM_DELETE_LIST
    await _send_list_selection_keyboard(update, context, "Qual lista você quer apagar?")
    return CONFIRM_DELETE_LIST

# --- Handler de Callback Genérico para Ações de Lista ---

async def handle_list_item_action_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Lida com callbacks de seleção de lista e confirmação de exclusão para diferentes fluxos.
    Este handler é chamado quando um botão inline de seleção de lista é clicado.
    """
    query = update.callback_query
    user_id = update.effective_user.id 
    await query.answer()
    callback_data = query.data
    logger.info(f"Callback de ação de lista recebido de {user_id}: {callback_data}")

    if callback_data == "cancel_list_action":
        await cancel_list_dialog(update, context)
        return ConversationHandler.END
    
    if callback_data == "view_lists_back":
        current_flow_state = context.user_data.get('current_list_flow_state')
        if current_flow_state == SELECTING_LIST_TO_ADD_ITEM:
            await _send_list_selection_keyboard(update, context, "Para qual lista você quer adicionar um item?")
            return SELECTING_LIST_TO_ADD_ITEM
        elif current_flow_state == SELECTING_LIST_TO_TOGGLE:
            await _send_list_selection_keyboard(update, context, "De qual lista você quer marcar/desmarcar um item?")
            return SELECTING_LIST_TO_TOGGLE
        elif current_flow_state == SELECTING_LIST_TO_REMOVE:
            await _send_list_selection_keyboard(update, context, "De qual lista você quer remover um item?")
            return SELECTING_LIST_TO_REMOVE
        elif current_flow_state == CONFIRM_DELETE_LIST:
            await _send_list_selection_keyboard(update, context, "Qual lista você quer apagar?")
            return CONFIRM_DELETE_LIST
        else:
            await query.edit_message_text("Voltando ao menu principal de listas.")
            return ConversationHandler.END

    if callback_data.startswith("select_list_id:"):
        list_id = int(callback_data.split(":")[1])
        
        list_info = db.get_list_by_id(list_id, user_id)
        if not list_info:
            await query.edit_message_text("Lista não encontrada ou você não tem permissão para acessá-la. Por favor, tente novamente.")
            return ConversationHandler.END
        list_name = list_info[1] 

        context.user_data['selected_list_id'] = list_id
        context.user_data['selected_list_name'] = list_name

        current_flow_state = context.user_data.get('current_list_flow_state')
        
        if current_flow_state == SELECTING_LIST_TO_ADD_ITEM:
            await query.edit_message_text(f"Ok! Agora, qual item você quer adicionar à lista '{list_name}'?")
            return GETTING_ITEM_TEXT
        
        elif current_flow_state == SELECTING_LIST_TO_TOGGLE:
            # Lista os itens da lista para que o usuário possa ver os IDs
            items = db.get_list_items(list_id)
            message = f"Itens da lista '{list_name}':\n\n"
            if not items:
                message += "Esta lista está vazia. Não há itens para marcar/desmarcar."
                await query.edit_message_text(message)
                return ConversationHandler.END
            else:
                for item_id, item_text, completed in items:
                    status_emoji = "✅" if completed else "⬜"
                    message += f"{status_emoji} {item_text} (ID: {item_id})\n"
                message += "\nQual o ID do item que você quer marcar/desmarcar?"
                await query.edit_message_text(message)
            return GETTING_ITEM_ID_TO_TOGGLE
        
        elif current_flow_state == SELECTING_LIST_TO_REMOVE:
            # Lista os itens da lista para que o usuário possa ver os IDs
            items = db.get_list_items(list_id)
            message = f"Itens da lista '{list_name}':\n\n"
            if not items:
                message += "Esta lista está vazia. Não há itens para remover."
                await query.edit_message_text(message)
                return ConversationHandler.END
            else:
                for item_id, item_text, completed in items:
                    status_emoji = "✅" if completed else "⬜"
                    message += f"{status_emoji} {item_text} (ID: {item_id})\n"
                message += "\nQual o ID do item que você quer remover?"
                await query.edit_message_text(message)
            return GETTING_ITEM_ID_TO_REMOVE
        
        elif current_flow_state == CONFIRM_DELETE_LIST:
            keyboard = [[InlineKeyboardButton("Sim, Apagar!", callback_data=f"confirm_delete_list_action:{list_id}")],
                        [InlineKeyboardButton("Não, Cancelar", callback_data="cancel_list_action")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Tem certeza que deseja apagar a lista '{list_name}' e todos os seus itens? Esta ação é irreversível.",
                reply_markup=reply_markup
            )
            return CONFIRM_DELETE_LIST 
        
        else:
            logger.warning(f"Callback de seleção de lista inválido ou não tratado no estado {current_flow_state}: {callback_data}")
            await query.edit_message_text("Ocorreu um erro inesperado. Por favor, tente novamente.")
            return ConversationHandler.END

    if callback_data.startswith("confirm_delete_list_action:"):
        list_id = int(callback_data.split(":")[1])
        
        list_info = db.get_list_by_id(list_id, user_id)
        if not list_info:
            await query.edit_message_text("Lista não encontrada para exclusão ou você não tem permissão para acessá-la. Por favor, tente novamente.")
            return ConversationHandler.END
        list_name = list_info[1]

        if db.delete_list(list_id, user_id): 
            await query.edit_message_text(f"Lista '{list_name}' e todos os seus itens foram apagados com sucesso! 🗑️")
        else:
            await query.edit_message_text("Ocorreu um erro ao apagar a lista. Por favor, tente novamente.")
        
        if 'selected_list_id' in context.user_data:
            del context.user_data['selected_list_id']
        if 'selected_list_name' in context.user_data:
            del context.user_data['selected_list_name']
        if 'current_list_flow_state' in context.user_data:
            del context.user_data['current_list_flow_state']

        return ConversationHandler.END
    
    logger.warning(f"Callback de ação de lista inválido ou não tratado: {callback_data}")
    await query.edit_message_text("Ocorreu um erro. Por favor, tente novamente.")
    return ConversationHandler.END

# --- Funções de Cancelamento ---

async def cancel_list_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo de lista em andamento."""
    user_id = update.effective_user.id
    logger.info(f"Diálogo de lista cancelado por {user_id}.")
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Operação de lista cancelada. ✅")
    else:
        await update.message.reply_text("Operação de lista cancelada. ✅")

    if 'selected_list_id' in context.user_data:
        del context.user_data['selected_list_id']
    if 'selected_list_name' in context.user_data:
        del context.user_data['selected_list_name']
    if 'current_list_flow_state' in context.user_data:
        del context.user_data['current_list_flow_state']

    return ConversationHandler.END