import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Importar ParseMode para uso explícito
import db 
import handlers # Manter aqui, pois list_handlers precisa chamar handlers.send_main_help_menu

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
SELECTING_LIST_TO_DELETE = 9 
CONFIRM_DELETE_LIST = 10 
LIST_MENU = 11 

# --- Funções Auxiliares ---

async def _send_list_selection_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    """Envia um teclado inline com as listas do usuário para seleção."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id) 

    if not lists:
        keyboard = [[InlineKeyboardButton("Criar Nova Lista", callback_data="list_action:new_list")],
                    [InlineKeyboardButton("Voltar ao Menu Principal", callback_data="help_category:main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.answer()
            try:
                await update.callback_query.edit_message_text(
                    "Você ainda não tem nenhuma lista. Crie uma com o botão abaixo!", 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            except telegram.error.BadRequest as e:
                if "Message is not modified" in str(e):
                    logger.info("Tentativa de editar mensagem com conteúdo idêntico em _send_list_selection_keyboard (sem listas). Enviando nova mensagem).")
                    await update.effective_message.reply_text(
                        "Você ainda não tem nenhuma lista. Crie uma com o botão abaixo!", 
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML # Garantir parse_mode
                    )
                else:
                    raise e
        else:
            await update.message.reply_text(
                "Você ainda não tem nenhuma lista. Crie uma com o botão abaixo!", 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        return ConversationHandler.END 
    
    keyboard = []
    for list_id, list_name in lists:
        keyboard.append([InlineKeyboardButton(list_name, callback_data=f"select_list_id_for_action:{list_id}")])

    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                text=message_text, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico em _send_list_selection_keyboard. Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    message_text, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e 
    else:
        await update.message.reply_text(
            message_text, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )

async def _send_list_action_menu(update: Update, list_id: int, list_name: str):
    """Envia o menu de ações para uma lista específica."""
    keyboard = [
        [InlineKeyboardButton("Ver Itens", callback_data=f"list_action:view_items:{list_id}")],
        [InlineKeyboardButton("Adicionar Item", callback_data=f"list_action:add_item_to_list:{list_id}")],
        [InlineKeyboardButton("Marcar/Desmarcar Item", callback_data=f"list_action:toggle_item_in_list:{list_id}")], 
        [InlineKeyboardButton("Remover Item", callback_data=f"list_action:remove_item_from_list:{list_id}")],
        [InlineKeyboardButton("Apagar Lista", callback_data=f"list_action:delete_specific_list:{list_id}")],
        [InlineKeyboardButton("Voltar ao Menu de Listas", callback_data="list_action:main_menu")], 
        [InlineKeyboardButton("Voltar ao Menu Principal", callback_data="help_category:main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"O que você gostaria de fazer com a lista '{list_name}'?"

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                message_text, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico em _send_list_action_menu. Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    message_text, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
    else: 
        await update.effective_message.reply_text(
            message_text, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )


# --- Handlers de Início de Conversa ---

async def list_my_lists_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe o menu principal de gerenciamento de listas (unificado com todas as opções)."""
    user_id = update.effective_user.id
    lists = db.get_user_lists(user_id)

    keyboard = []
    
    keyboard.append([InlineKeyboardButton("Criar Nova Lista", callback_data="list_action:new_list")])
    if lists:
        keyboard.append([InlineKeyboardButton("Ver/Gerenciar Listas Existentes", callback_data="list_action:select_existing_list")])
        keyboard.append([InlineKeyboardButton("Adicionar Item", callback_data="list_action:add_item")])
        keyboard.append([InlineKeyboardButton("Marcar/Desmarcar Item", callback_data="list_action:toggle_item")])
        keyboard.append([InlineKeyboardButton("Remover Item", callback_data="list_action:remove_item")])
        keyboard.append([InlineKeyboardButton("Apagar Lista Completa", callback_data="list_action:delete_list")])
    
    keyboard.append([InlineKeyboardButton("Voltar ao Menu Principal", callback_data="help_category:main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = "Gerencie suas Listas:\nOrganize suas tarefas e compras facilmente! Selecione uma ação:" # Alterado de <br> para \n
    
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                message_text, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico em list_my_lists_menu. Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    message_text, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e 
    else:
        await update.message.reply_text(
            message_text, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    return LIST_MENU

async def new_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para criar uma nova lista."""
    logger.info(f"Comando /novalista recebido de {update.effective_user.id}.")
    
    message_text = "Qual o nome da nova lista que você quer criar?"
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                message_text,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico em new_list_start. Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    message_text,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
    else:
        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    return SELECTING_LIST_NAME

async def get_list_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da nova lista e a cria."""
    user_id = update.effective_user.id
    list_name = update.message.text.strip()
    logger.info(f"Usuário {user_id} informou o nome da lista: {list_name}")

    if not list_name:
        await update.message.reply_text(
            "O nome da lista não pode ser vazio. Por favor, digite um nome válido.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return SELECTING_LIST_NAME

    if db.add_list(user_id, list_name): 
        await update.message.reply_text(
            f"Lista '{list_name}' criada com sucesso! 🎉",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    else:
        await update.message.reply_text(
            f"Já existe uma lista com o nome '{list_name}'. Por favor, escolha outro nome.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    
    await list_my_lists_menu(update, context) 
    return ConversationHandler.END


async def view_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE, pre_selected_list_id: int = None) -> int:
    """Inicia o diálogo para visualizar os itens de uma lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /verlista recebido de {user_id}.")
    
    if pre_selected_list_id:
        return await _display_list_items(update, context, pre_selected_list_id)
    else:
        await _send_list_selection_keyboard(update, context, "Qual lista você quer visualizar?")
        return VIEWING_LIST_COMMAND_START

async def get_list_to_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista para visualizar e mostra seus itens."""
    query = update.callback_query
    user_id = query.from_user.id 
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith("select_list_id_for_action:"):
        list_id = int(callback_data.split(":")[1])
        
        list_info = db.get_list_by_id(list_id, user_id) 
        if not list_info:
            await query.edit_message_text(
                "Lista não encontrada ou você não tem permissão para acessá-la. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
            return ConversationHandler.END
        
        return await _display_list_items(update, context, list_id)
    elif callback_data == "cancel_list_action":
        await cancel_list_dialog(update, context)
        return ConversationHandler.END
    else:
        logger.warning(f"Callback de visualização de lista inválido ou não tratado: {callback_data}.")
        try:
            await query.edit_message_text(
                "Ocorreu um erro. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (erro get_list_to_view). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    "Ocorreu um erro. Por favor, tente novamente.",
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
        return ConversationHandler.END

async def _display_list_items(update: Update, context: ContextTypes.DEFAULT_TYPE, list_id: int) -> int:
    """Função auxiliar para exibir os itens de uma lista e o menu de ações."""
    user_id = update.effective_user.id
    list_info = db.get_list_by_id(list_id, user_id)
    list_name = list_info[1]
    items = db.get_list_items(list_id)
    message = f"Itens da lista '{list_name}':\n\n"
    if not items:
        message += "Esta lista está vazia. Adicione itens com o botão 'Adicionar Item'!"
    else:
        for item_id, item_text, completed in items:
            status_emoji = "✅" if completed else "⬜"
            message += f"{status_emoji} {item_text} (ID: {item_id})\n"
    
    keyboard = [
        [InlineKeyboardButton("Adicionar Item", callback_data=f"list_action:add_item_to_list:{list_id}")],
        [InlineKeyboardButton("Marcar/Desmarcar Item", callback_data=f"list_action:toggle_item_in_list:{list_id}")],
        [InlineKeyboardButton("Remover Item", callback_data=f"list_action:remove_item_from_list:{list_id}")],
        [InlineKeyboardButton("Apagar Lista", callback_data=f"list_action:delete_specific_list:{list_id}")],
        [InlineKeyboardButton("Voltar ao Menu de Listas", callback_data="list_action:main_menu")],
        [InlineKeyboardButton("Voltar ao Menu Principal", callback_data="help_category:main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                text=message, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico em _display_list_items. Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    text=message, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
    else:
        await update.message.reply_text(
            text=message, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    return ConversationHandler.END 


# --- Adicionar Item à Lista ---

async def add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE, pre_selected_list_id: int = None) -> int:
    """Inicia o diálogo para adicionar um item a uma lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /additem recebido de {user_id}.")

    if pre_selected_list_id:
        list_info = db.get_list_by_id(pre_selected_list_id, user_id)
        if not list_info:
            await update.effective_message.reply_text(
                "Lista não encontrada ou você não tem permissão para acessá-la. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
            return ConversationHandler.END
        list_name = list_info[1]
        context.user_data['selected_list_id'] = pre_selected_list_id
        context.user_data['selected_list_name'] = list_name
        message_text = f"Ok! Agora, qual item você quer adicionar à lista '{list_name}'?"
        if update.callback_query:
            await update.callback_query.answer()
            try:
                await update.callback_query.edit_message_text(
                    message_text,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            except telegram.error.BadRequest as e:
                if "Message is not modified" in str(e):
                    logger.info("Tentativa de editar mensagem com conteúdo idêntico (add_item_start com pre_selected). Enviando nova mensagem).")
                    await update.effective_message.reply_text(
                        message_text,
                        parse_mode=ParseMode.HTML # Garantir parse_mode
                    )
                else:
                    raise e
        else:
            await update.effective_message.reply_text(
                message_text,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        return GETTING_ITEM_TEXT
    else:
        await _send_list_selection_keyboard(update, context, "Para qual lista você quer adicionar um item?")
        return SELECTING_LIST_TO_ADD_ITEM

async def get_list_to_add_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista para adicionar um item e pede o texto do item."""
    query = update.callback_query
    user_id = query.from_user.id 
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith("select_list_id_for_action:"):
        list_id = int(callback_data.split(":")[1])
        
        list_info = db.get_list_by_id(list_id, user_id) 
        if not list_info:
            await query.edit_message_text(
                "Lista não encontrada ou você não tem permissão para acessá-la. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
            return ConversationHandler.END
        list_name = list_info[1] 

        context.user_data['selected_list_id'] = list_id
        context.user_data['selected_list_name'] = list_name
        
        message_text = f"Ok! Agora, qual item você quer adicionar à lista '{list_name}'?"
        try:
            await query.edit_message_text(
                message_text,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (get_list_to_add_item). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    message_text,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
        return GETTING_ITEM_TEXT
    elif callback_data == "cancel_list_action":
        await cancel_list_dialog(update, context)
        return ConversationHandler.END
    else:
        logger.warning(f"Callback de seleção de lista inválido para adicionar item: {callback_data}.")
        try:
            await query.edit_message_text(
                "Ocorreu um erro. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (erro get_list_to_add_item). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    "Ocorreu um erro. Por favor, tente novamente.",
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
        return ConversationHandler.END

async def get_item_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o texto do item e o adiciona à lista selecionada."""
    user_id = update.effective_user.id
    item_text = update.message.text.strip()
    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name')

    if not list_id or not list_name:
        await update.message.reply_text(
            "Parece que a lista não foi selecionada corretamente. Por favor, tente novamente com /additem.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return ConversationHandler.END

    if not item_text:
        await update.message.reply_text(
            "O item não pode ser vazio. Por favor, digite o texto do item.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return GETTING_ITEM_TEXT

    if db.add_list_item(list_id, item_text): 
        await update.message.reply_text(
            f"Item '{item_text}' adicionado à lista '{list_name}' com sucesso! ✅",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    else:
        await update.message.reply_text(
            "Ocorreu um erro ao adicionar o item. Por favor, tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    
    context.user_data.pop('selected_list_id', None)
    context.user_data.pop('selected_list_name', None)

    await list_my_lists_menu(update, context) 
    return ConversationHandler.END


# --- Marcar/Desmarcar Item ---

async def toggle_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE, pre_selected_list_id: int = None) -> int:
    """Inicia o diálogo para marcar/desmarcar um item da lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /marcaritem recebido de {user_id}.")

    if pre_selected_list_id:
        return await _display_items_for_toggle(update, context, pre_selected_list_id)
    else:
        await _send_list_selection_keyboard(update, context, "De qual lista você quer marcar/desmarcar um item?")
        return SELECTING_LIST_TO_TOGGLE

async def get_list_to_toggle_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista para marcar/desmarcar item e mostra seus itens como botões."""
    query = update.callback_query
    user_id = query.from_user.id 
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith("select_list_id_for_action:"):
        list_id = int(callback_data.split(":")[1])
        
        list_info = db.get_list_by_id(list_id, user_id) 
        if not list_info:
            await query.edit_message_text(
                "Lista não encontrada ou você não tem permissão para acessá-la. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
            return ConversationHandler.END
        
        return await _display_items_for_toggle(update, context, list_id)
    elif callback_data == "cancel_list_action":
        await cancel_list_dialog(update, context)
        return ConversationHandler.END
    else:
        logger.warning(f"Callback de seleção de lista inválido para marcar/desmarcar item: {callback_data}.")
        try:
            await query.edit_message_text(
                "Ocorreu um erro. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (erro get_list_to_toggle_item). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    "Ocorreu um erro. Por favor, tente novamente.",
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
        return ConversationHandler.END

async def _display_items_for_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, list_id: int) -> int:
    """Função auxiliar para exibir itens para marcar/desmarcar como botões."""
    user_id = update.effective_user.id
    list_info = db.get_list_by_id(list_id, user_id)
    list_name = list_info[1]
    context.user_data['selected_list_id'] = list_id
    context.user_data['selected_list_name'] = list_name

    items = db.get_list_items(list_id)
    message = f"Selecione o item da lista '{list_name}' para marcar/desmarcar:\n\n"
    keyboard = []
    if not items:
        message = "Esta lista está vazia. Não há itens para marcar/desmarcar."
        keyboard.append([InlineKeyboardButton("Voltar ao Menu de Listas", callback_data="list_action:main_menu")])
        keyboard.append([InlineKeyboardButton("Voltar ao Menu Principal", callback_data="help_category:main_menu")])
    else:
        for item_id, item_text, completed in items:
            status_emoji = "✅" if completed else "⬜"
            button_text = f"{status_emoji} {item_text}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"toggle_item_id:{item_id}")])
        keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                message, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (toggle - sem itens). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    message, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
    else:
        await update.effective_message.reply_text(
            message, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        
    if not items: 
        context.user_data.pop('selected_list_id', None)
        context.user_data.pop('selected_list_name', None)
        return ConversationHandler.END
    return GETTING_ITEM_ID_TO_TOGGLE

async def process_toggle_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa o callback de um botão de item para marcar/desmarcar."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    item_id_str = query.data.split(":")[1]
    try:
        item_id = int(item_id_str)
    except ValueError:
        await query.edit_message_text(
            "ID de item inválido. Por favor, tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return ConversationHandler.END 

    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name')

    if not list_id or not list_name:
        await query.edit_message_text(
            "Parece que a lista não foi selecionada corretamente. Por favor, tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return ConversationHandler.END

    item_info = db.get_list_item_by_id(item_id) 
    if not item_info or item_info[0] != list_id: 
        await query.edit_message_text(
            "Item não encontrado nesta lista ou não pertence a ela. Por favor, verifique o ID e tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return ConversationHandler.END
    
    item_text = item_info[1]
    current_status = item_info[2]
    new_status = not current_status

    if db.toggle_list_item(item_id, list_id): 
        status_text = "marcado como completo ✅" if new_status else "desmarcado ⬜"
        await query.edit_message_text(
            f"Item '{item_text}' na lista '{list_name}' foi {status_text} com sucesso!",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    else:
        await query.edit_message_text(
            "Ocorreu um erro ao atualizar o item. Por favor, tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )

    context.user_data.pop('selected_list_id', None)
    context.user_data.pop('selected_list_name', None)
    
    await list_my_lists_menu(update, context) 
    return ConversationHandler.END


# --- Remover Item ---

async def remove_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE, pre_selected_list_id: int = None) -> int:
    """Inicia o diálogo para remover um item da lista."""
    user_id = update.effective_user.id
    logger.info(f"Comando /removeritem recebido de {user_id}.")

    if pre_selected_list_id:
        return await _display_items_for_remove(update, context, pre_selected_list_id)
    else:
        await _send_list_selection_keyboard(update, context, "De qual lista você quer remover um item?")
        return SELECTING_LIST_TO_REMOVE

async def get_list_to_remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista para remover item e mostra seus itens como botões."""
    query = update.callback_query
    user_id = query.from_user.id 
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith("select_list_id_for_action:"):
        list_id = int(callback_data.split(":")[1])
        
        list_info = db.get_list_by_id(list_id, user_id) 
        if not list_info:
            await query.edit_message_text(
                "Lista não encontrada ou você não tem permissão para acessá-la. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
            return ConversationHandler.END
        
        return await _display_items_for_remove(update, context, list_id)
    elif callback_data == "cancel_list_action":
        await cancel_list_dialog(update, context)
        return ConversationHandler.END
    else:
        logger.warning(f"Callback de seleção de lista inválido para remover item: {callback_data}.")
        try:
            await query.edit_message_text(
                "Ocorreu um erro. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (erro get_list_to_remove_item). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    "Ocorreu um erro. Por favor, tente novamente.",
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
        return ConversationHandler.END

async def _display_items_for_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, list_id: int) -> int:
    """Função auxiliar para exibir itens para remover como botões."""
    user_id = update.effective_user.id
    list_info = db.get_list_by_id(list_id, user_id)
    list_name = list_info[1]
    context.user_data['selected_list_id'] = list_id
    context.user_data['selected_list_name'] = list_name

    items = db.get_list_items(list_id)
    message = f"Selecione o item da lista '{list_name}' para remover:\n\n"
    keyboard = []
    if not items:
        message = "Esta lista está vazia. Não há itens para remover."
        keyboard.append([InlineKeyboardButton("Voltar ao Menu de Listas", callback_data="list_action:main_menu")])
        keyboard.append([InlineKeyboardButton("Voltar ao Menu Principal", callback_data="help_category:main_menu")])
    else:
        for item_id, item_text, completed in items:
            status_emoji = "✅" if completed else "⬜"
            button_text = f"{status_emoji} {item_text}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"remove_item_id:{item_id}")])
        keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_list_action")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                message, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (remove - sem itens). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    message, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
    else:
        await update.effective_message.reply_text(
            message, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )

    if not items: 
        context.user_data.pop('selected_list_id', None)
        context.user_data.pop('selected_list_name', None)
        return ConversationHandler.END
    return GETTING_ITEM_ID_TO_REMOVE

async def process_remove_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa o callback de um botão de item para remover."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    item_id_str = query.data.split(":")[1]
    try:
        item_id = int(item_id_str)
    except ValueError:
        await query.edit_message_text(
            "ID de item inválido. Por favor, tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return ConversationHandler.END 

    list_id = context.user_data.get('selected_list_id')
    list_name = context.user_data.get('selected_list_name')

    if not list_id or not list_name:
        await query.edit_message_text(
            "Parece que a lista não foi selecionada corretamente. Por favor, tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return ConversationHandler.END

    item_info = db.get_list_item_by_id(item_id) 
    if not item_info or item_info[0] != list_id:
        await query.edit_message_text(
            "Item não encontrado nesta lista ou não pertence a ela. Por favor, verifique o ID e tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return ConversationHandler.END

    if db.remove_list_item(item_id, list_id): 
        await query.edit_message_text(
            f"Item '{item_info[1]}' removido da lista '{list_name}' com sucesso! 🗑️",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    else:
        await query.edit_message_text(
            "Ocorreu um erro ao remover o item. Por favor, tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )

    context.user_data.pop('selected_list_id', None)
    context.user_data.pop('selected_list_name', None)

    await list_my_lists_menu(update, context) 
    return ConversationHandler.END


# --- Apagar Lista ---

async def delete_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE, pre_selected_list_id: int = None) -> int:
    """Inicia o diálogo para apagar uma lista inteira."""
    user_id = update.effective_user.id
    logger.info(f"Comando /apagarlista recebido de {user_id}.")

    if pre_selected_list_id:
        return await _confirm_delete_list(update, context, pre_selected_list_id)
    else:
        await _send_list_selection_keyboard(update, context, "Qual lista você quer apagar?")
        return SELECTING_LIST_TO_DELETE

async def get_list_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a seleção da lista para apagar e pede confirmação."""
    query = update.callback_query
    user_id = query.from_user.id 
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith("select_list_id_for_action:"):
        list_id = int(callback_data.split(":")[1])
        logger.info(f"Usuário {user_id} selecionou a lista ID {list_id} para exclusão.") 
        
        list_info = db.get_list_by_id(list_id, user_id)
        if not list_info:
            await query.edit_message_text(
                "Lista não encontrada para exclusão ou você não tem permissão para acessá-la. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
            return ConversationHandler.END
        
        return await _confirm_delete_list(update, context, list_id)
    elif callback_data == "cancel_list_action":
        await cancel_list_dialog(update, context)
        return ConversationHandler.END
    else:
        logger.warning(f"Callback de seleção de lista inválido para apagar lista: {callback_data}.")
        try:
            await query.edit_message_text(
                "Ocorreu um erro. Por favor, tente novamente.",
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (erro get_list_to_delete). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    "Ocorreu um erro. Por favor, tente novamente.",
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
        return ConversationHandler.END

async def _confirm_delete_list(update: Update, context: ContextTypes.DEFAULT_TYPE, list_id: int) -> int:
    """Função auxiliar para pedir confirmação de exclusão da lista."""
    user_id = update.effective_user.id
    list_info = db.get_list_by_id(list_id, user_id)
    if not list_info:
        await update.effective_message.reply_text(
            "Lista não encontrada para exclusão ou você não tem permissão para acessá-la. Por favor, tente novamente.",
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
        return ConversationHandler.END
    list_name = list_info[1]
    context.user_data['selected_list_id'] = list_id 
    context.user_data['selected_list_name'] = list_name
    
    keyboard = [[InlineKeyboardButton("Sim, Apagar!", callback_data=f"confirm_delete_list_action:{list_id}")],
                [InlineKeyboardButton("Não, Voltar", callback_data="cancel_list_action")]] 
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"Tem certeza que deseja apagar a lista '{list_name}' e todos os seus itens? Esta ação é irreversível."
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                message_text, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (_confirm_delete_list). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    message_text, 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
    else:
        await update.effective_message.reply_text(
            message_text, 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )
    logger.info(f"Enviando pedido de confirmação para apagar lista ID {list_id} para {user_id}.") 
    return CONFIRM_DELETE_LIST

async def delete_list_confirm_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga a lista."""
    query = update.callback_query
    user_id = query.from_user.id 
    await query.answer()

    callback_data = query.data
    logger.info(f"Callback de confirmação de exclusão recebido de {user_id}: {callback_data}.") 

    if callback_data.startswith("confirm_delete_list_action:"):
        list_id = int(callback_data.split(":")[1])
        logger.info(f"Tentando apagar lista com ID {list_id} para o usuário {user_id}.") 
        
        list_name = None
        list_info = db.get_list_by_id(list_id, user_id)
        if list_info:
            list_name = list_info[1]
        
        if db.delete_list(list_id, user_id): 
            confirmation_message = f"Lista '{list_name or list_id}' e todos os seus itens foram apagados com sucesso! 🗑️"
            logger.info(f"Lista ID {list_id} apagada com sucesso por {user_id}.") 
            try:
                await query.edit_message_text(
                    confirmation_message,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                ) 
            except telegram.error.BadRequest as e:
                if "Message is not modified" in str(e):
                    logger.info("Tentativa de editar mensagem com conteúdo idêntico (delete_list - sucesso). Enviando nova mensagem).")
                    await update.effective_message.reply_text(
                        confirmation_message,
                        parse_mode=ParseMode.HTML # Garantir parse_mode
                    )
                else:
                    raise e
        else:
            error_message = f"Ocorreu um erro ao apagar a lista ID {list_id}. Verifique se a lista existe ou se você tem permissão."
            logger.warning(f"Falha ao apagar lista ID {list_id} por {user_id}.") 
            try:
                await query.edit_message_text(
                    error_message,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            except telegram.error.BadRequest as e:
                if "Message is not modified" in str(e):
                    logger.info("Tentativa de editar mensagem com conteúdo idêntico (delete_list - erro). Enviando nova mensagem).")
                    await update.effective_message.reply_text(
                        error_message,
                        parse_mode=ParseMode.HTML # Garantir parse_mode
                    )
                else:
                    raise e
        
        context.user_data.pop('selected_list_id', None)
        context.user_data.pop('selected_list_name', None)

        await list_my_lists_menu(update, context)
        return ConversationHandler.END
    
    await cancel_list_dialog(update, context)
    return ConversationHandler.END

# --- Handler de Callback Genérico para Ações de Lista (Apenas navegação e cancelamento) ---

async def handle_list_item_action_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Lida com callbacks de ações gerais do menu de listas que NÃO iniciam ConversationHandlers específicos.
    Apenas navegação e cancelamento.
    """
    query = update.callback_query
    user_id = query.from_user.id 
    await query.answer() 
    callback_data = query.data
    logger.info(f"Callback de ação de lista geral recebido de {user_id}: {callback_data}.")

    if callback_data == "list_action:main_menu": 
        await list_my_lists_menu(update, context)
        return ConversationHandler.END 
    elif callback_data == "help_category:main_menu":
        await handlers.send_main_help_menu(update, context)
        return ConversationHandler.END
    elif callback_data == "cancel_list_action":
        await cancel_list_dialog(update, context)
        return ConversationHandler.END
    
    logger.warning(f"Callback de ação de lista desconhecido ou não tratado no handler genérico: {callback_data}.")
    return ConversationHandler.END

# --- Funções de Cancelamento ---

async def cancel_list_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo de lista em andamento."""
    user_id = update.effective_user.id
    logger.info(f"Diálogo de lista cancelado por {user_id}.")
    
    keyboard = [[InlineKeyboardButton("Voltar ao Menu de Listas", callback_data="list_action:main_menu")],
                [InlineKeyboardButton("Voltar ao Menu Principal", callback_data="help_category:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                "Operação de lista cancelada. ✅", 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML # Garantir parse_mode
            )
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Tentativa de editar mensagem com conteúdo idêntico (cancelamento). Enviando nova mensagem).")
                await update.effective_message.reply_text(
                    "Operação de lista cancelada. ✅", 
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML # Garantir parse_mode
                )
            else:
                raise e
    else:
        await update.message.reply_text(
            "Operação de lista cancelada. ✅", 
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML # Garantir parse_mode
        )

    context.user_data.pop('selected_list_id', None)
    context.user_data.pop('selected_list_name', None)
    context.user_data.pop('current_list_flow_state', None)

    return ConversationHandler.END