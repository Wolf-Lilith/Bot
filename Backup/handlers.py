from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
import logging
import db
import re 


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

GETTING_TRIGGER_PHRASE = 0
GETTING_RESPONSE_PHRASE = 1
GETTING_PHRASE_ID_TO_DELETE = 2

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Olá, {user.mention_html()}! Sou a Lilith, sua assistente pessoal.\\n"
        "Use /ajuda para ver o que eu posso fazer!"
    )
    logging.info(f"Comando /start recebido de {user.id}.")

async def send_main_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id=None, chat_id=None):
    """Função auxiliar para enviar/editar o menu de ajuda principal."""
    keyboard = [
        [InlineKeyboardButton("Frases Personalizadas", callback_data="help_category:phrases")],
        [InlineKeyboardButton("Listas", callback_data="help_category:lists")],
        [InlineKeyboardButton("Lembretes", callback_data="help_category:reminders")],
        [InlineKeyboardButton("Comandos Gerais", callback_data="help_category:general")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = escape_markdown("Aqui está o que eu posso fazer por você. Selecione uma categoria para ver os comandos:", version=2)

    if message_id and chat_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logging.error(f"Erro ao editar mensagem do menu de ajuda principal: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
    elif update.message:
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        logging.error("send_main_help_menu chamado sem message_id/chat_id ou update.message.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra um menu interativo de ajuda com categorias."""
    await send_main_help_menu(update, context)
    logging.info(f"Comando /ajuda recebido de {update.effective_user.id}.")

async def handle_help_category_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lida com os callbacks do menu de ajuda por categoria."""
    query = update.callback_query
    await query.answer() # Sempre responda ao callback

    category = query.data.split(":")[1]
    user_id = query.effective_user.id

    commands = db.get_all_commands()
    category_commands = [cmd for cmd in commands if _get_category_from_command(cmd['command_name']) == category]

    if category_commands:
        response_text = f"*{_get_category_title(category)} Comandos:*\n\n"
        for cmd in category_commands:
            response_text += f"*/{escape_markdown(cmd['command_name'], version=2)}* - {escape_markdown(cmd['description'], version=2)}\n"
    else:
        response_text = escape_markdown(f"Nenhum comando encontrado para a categoria '{_get_category_title(category)}'.", version=2)

    keyboard = [[InlineKeyboardButton("🔙 Voltar ao Menu Principal", callback_data="help_category:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            text=response_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logging.info(f"Usuário {user_id} visualizou comandos da categoria '{category}'.")
    except Exception as e:
        logging.error(f"Erro ao editar mensagem de comandos da categoria para {user_id}: {e}")
        # Se falhar a edição, tenta enviar uma nova mensagem
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=response_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )


def _get_category_from_command(command_name: str) -> str:
    """Mapeia um comando para sua categoria de ajuda."""
    if command_name in ["addfrase", "minhasfrases", "apagarfrase"]:
        return "phrases"
    elif command_name in ["novalista", "listas", "verlista", "additem", "marcaritem", "removeritem", "apagarlista"]:
        return "lists"
    elif command_name in ["add_lembrete", "ver_lembretes", "apagar_lembrete"]:
        return "reminders"
    else:
        return "general" # start, ajuda, cancelar, etc.

def _get_category_title(category_key: str) -> str:
    """Retorna o título formatado da categoria."""
    titles = {
        "phrases": "Frases Personalizadas",
        "lists": "Listas",
        "reminders": "Lembretes",
        "general": "Gerais"
    }
    return titles.get(category_key, "Desconhecido")


# --- Funções para Frases Personalizadas ---
async def add_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de adicionar uma frase personalizada."""
    user_id = update.effective_user.id
    logging.info(f"Comando /addfrase recebido de {user_id}.")
    await update.message.reply_text(escape_markdown("Certo! Qual frase ou palavra deve *ativar* a minha resposta? (Ex: 'bom dia', 'qual a previsão?'). Para cancelar, digite /cancelar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return GETTING_TRIGGER_PHRASE

async def get_trigger_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de gatilho do usuário."""
    trigger = update.message.text.strip()
    if not trigger:
        await update.message.reply_text(escape_markdown("Parece que você não digitou nada. Por favor, digite a frase de gatilho ou /cancelar para cancelar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_TRIGGER_PHRASE # Permanece no mesmo estado
    
    context.user_data['trigger_phrase'] = trigger
    logging.info(f"Gatilho '{trigger}' recebido de {update.effective_user.id}.")
    await update.message.reply_text(escape_markdown(f"Ótimo! E qual deve ser a *minha resposta* para '{trigger}'? (Ex: 'Olá, como posso ajudar?', 'A previsão é de sol!').", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return GETTING_RESPONSE_PHRASE

async def get_response_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de resposta do usuário e salva no DB."""
    response = update.message.text.strip()
    if not response:
        await update.message.reply_text(escape_markdown("Parece que você não digitou nada. Por favor, digite a frase de resposta ou /cancelar para cancelar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_RESPONSE_PHRASE # Permanece no mesmo estado

    user_id = update.effective_user.id
    trigger = context.user_data.get('trigger_phrase')

    if not trigger:
        logging.error(f"Erro: trigger_phrase não encontrada para user {user_id} no estado GETTING_RESPONSE_PHRASE.")
        await update.message.reply_text(escape_markdown("Ocorreu um erro. Por favor, tente novamente com /addfrase.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data.clear()
        return ConversationHandler.END

    phrase_id = db.add_personal_phrase(user_id, trigger, response)
    if phrase_id:
        await update.message.reply_text(escape_markdown(f"✅ Frase personalizada adicionada! Agora, quando alguém disser '{trigger}', eu responderei '{response}'. (ID: `{phrase_id}`).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logging.info(f"Frase personalizada '{trigger}'->'{response}' (ID: {phrase_id}) adicionada por {user_id}.")
    else:
        await update.message.reply_text(escape_markdown(f"⚠️ Essa frase de gatilho ('{trigger}') já existe. Não pude adicionar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logging.warning(f"Tentativa de adicionar frase duplicada para user {user_id} com gatilho '{trigger}'.")

    context.user_data.clear()
    return ConversationHandler.END

async def view_my_phrases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vê as frases personalizadas do usuário."""
    user_id = update.effective_user.id
    phrases = db.get_user_personal_phrases(user_id)

    if phrases:
        text = escape_markdown("*Suas Frases Personalizadas:*\n\n", version=2)
        for p in phrases:
            text += escape_markdown(f"ID: `{p['id']}`\n", version=2)
            text += escape_markdown(f"  Gatilho: '{p['trigger_phrase']}'\n", version=2)
            text += escape_markdown(f"  Resposta: '{p['response_phrase']}'\n\n", version=2)
        
        # Cria botões para apagar as frases
        keyboard = []
        for p in phrases:
            keyboard.append([InlineKeyboardButton(f"Apagar ID {p['id']}: '{p['trigger_phrase']}'", callback_data=f"delete_phrase_id:{p['id']}")])
        keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_delete_phrase")]) # Botão de cancelar
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logging.info(f"Usuário {user_id} visualizou suas frases personalizadas.")
    else:
        await update.message.reply_text(escape_markdown("Você não tem nenhuma frase personalizada ainda. Use /addfrase para adicionar uma!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
async def delete_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de apagar uma frase personalizada, mostrando as opções."""
    user_id = update.effective_user.id
    phrases = db.get_user_personal_phrases(user_id)

    if not phrases:
        await update.message.reply_text(escape_markdown("Você não tem nenhuma frase personalizada para apagar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END # Encerra o diálogo se não houver frases

    text = escape_markdown("*Selecione a frase que deseja apagar:*\n\n", version=2)
    keyboard = []
    for p in phrases:
        text += escape_markdown(f"ID: `{p['id']}` - Gatilho: '{p['trigger_phrase']}'\n", version=2)
        keyboard.append([InlineKeyboardButton(f"Apagar ID {p['id']}", callback_data=f"delete_phrase_id:{p['id']}")])
    
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_delete_phrase")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logging.info(f"Usuário {user_id} iniciou o processo de apagar frase.")
    return GETTING_PHRASE_ID_TO_DELETE

async def delete_phrase_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga a frase personalizada selecionada."""
    query = update.callback_query
    await query.answer() # Confirma o recebimento do callback

    user_id = query.effective_user.id
    
    if query.data.startswith("delete_phrase_id:"):
        phrase_id_str = query.data.split(":")[1]
        try:
            phrase_id = int(phrase_id_str)
        except ValueError:
            await query.edit_message_text(escape_markdown("❌ ID de frase inválido. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            context.user_data.clear()
            return ConversationHandler.END

        if db.delete_personal_phrase(phrase_id, user_id):
            await query.edit_message_text(escape_markdown(f"✅ Frase personalizada (ID: `{phrase_id}`) apagada com sucesso!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logging.info(f"Frase personalizada ID {phrase_id} apagada por {user_id}.")
        else:
            await query.edit_message_text(escape_markdown(f"❌ Não foi possível apagar a frase personalizada com ID `{phrase_id}`. Verifique se ela existe e pertence a você.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logging.warning(f"Falha ao apagar frase personalizada ID {phrase_id} para {user_id}.")
    elif query.data == "cancel_delete_phrase":
        await query.edit_message_text(escape_markdown("Operação de apagar frase cancelada.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text(escape_markdown("Ação desconhecida para apagar frase.", version=2), parse_mode=ParseMode.MARKDOWN_V2)

    context.user_data.clear() # Limpa os dados do usuário para encerrar o diálogo
    return ConversationHandler.END

async def handle_personal_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    user_id = update.effective_user.id

    response_phrase = db.get_response_for_trigger(user_id, text)
    if response_phrase:
        await update.message.reply_text(escape_markdown(response_phrase, version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logging.info(f"Frase personalizada acionada por {user_id}: '{text}' -> '{response_phrase}'.")
        return

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
    
    context.user_data.clear() # Limpa os dados do usuário para encerrar o diálogo
    return ConversationHandler.END