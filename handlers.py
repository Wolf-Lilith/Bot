# handlers.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
import logging
import db
import re

# Usar o logger configurado em main.py
logger = logging.getLogger(__name__)

# --- Estados para ConversationHandler (certifique-se de que são únicos globalmente) ---
GETTING_TRIGGER_PHRASE = 0
GETTING_RESPONSE_PHRASE = 1
GETTING_PHRASE_ID_TO_DELETE = 2

# --- Handlers de Comandos e Funções Auxiliares ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia o bot e cumprimenta o usuário."""
    user = update.effective_user
    await update.message.reply_html(
        f"Olá, {user.mention_html()}! Sou a Lilith, sua assistente pessoal.\n"
        "Use /ajuda para ver o que eu posso fazer!"
    )
    logger.info(f"Comando /start recebido de {user.id}.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o menu de ajuda principal."""
    user_id = update.effective_user.id
    # Quando o comando /ajuda é chamado, sempre envia uma NOVA mensagem de ajuda.
    # A função send_main_help_menu decide se edita ou envia com base no 'update'.
    await send_main_help_menu(update, context)
    logger.info(f"Comando /ajuda recebido de {user_id}.")

async def send_main_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Função auxiliar para enviar/editar o menu de ajuda principal."""
    keyboard = [
        [InlineKeyboardButton("Frases Personalizadas", callback_data="help_category:phrases")],
        [InlineKeyboardButton("Listas", callback_data="help_category:lists")],
        [InlineKeyboardButton("Lembretes", callback_data="help_category:reminders")],
        [InlineKeyboardButton("Comandos Gerais", callback_data="help_category:general")],
        [InlineKeyboardButton("Contas Financeiras", callback_data="help_category:accounts")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    commands = db.get_all_commands()
    help_message = "Aqui estão os comandos que eu conheço:\n\n"
    if commands:
        for cmd_name, desc in commands:
            # Escapa o MarkdownV2 para garantir que não quebre a formatação
            display_cmd = escape_markdown(cmd_name.replace("_", r"\_"), version=2)
            display_desc = escape_markdown((desc or ""), version=2)
            help_message += f"*{display_cmd}*: {display_desc}\n"
    else:
        help_message += "Nenhum comando registrado no momento."

    # Decide se edita uma mensagem existente (de um callback) ou envia uma nova (de um comando)
    if update.callback_query:
        query = update.callback_query
        await query.answer() # Confirma que o callback foi recebido
        await query.edit_message_text( # Edita a mensagem de onde o callback veio
            text=escape_markdown(help_message, version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Menu de ajuda editado via callback para {query.from_user.id}.")
    elif update.message:
        await update.message.reply_text( # Envia uma nova mensagem em resposta ao comando
            text=escape_markdown(help_message, version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Menu de ajuda enviado via comando para {update.effective_user.id}.")
    else:
        logger.warning("send_main_help_menu foi chamado sem update.message ou update.callback_query.")

async def send_help_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mostra o menu de ajuda para categorias específicas."""
    query = update.callback_query
    await query.answer()
    category = query.data.split(':')[1] # help_category:phrases -> phrases

    category_message = ""
    # Define os comandos e a mensagem para cada categoria
    if category == "phrases":
        category_message = (
            "⚙️ *Frases Personalizadas:*\n"
            "* `/addfrase` - Adiciona uma nova frase que eu devo responder.\n"
            "* `/minhasfrases` - Vê todas as frases que você me ensinou.\n"
            "* `/apagarfrase` - Apaga uma das suas frases personalizadas.\n\n"
            "Eu responderei automaticamente quando vir a sua frase de gatilho!"
        )
    elif category == "lists":
        category_message = (
            "📝 *Listas:*\n"
            "* `/novalista` - Cria uma nova lista (ex: compras, tarefas).\n"
            "* `/listas` - Vê todas as suas listas.\n"
            "* `/verlista` - Vê os itens de uma lista específica.\n"
            "* `/additem` - Adiciona um item a uma lista existente.\n"
            "* `/marcaritem` - Marca um item da lista como completo ou incompleto.\n"
            "* `/removeritem` - Remove um item de uma lista.\n"
            "* `/apagarlista` - Apaga uma lista inteira.\n\n"
            "Organize suas tarefas e compras facilmente!"
        )
    elif category == "reminders":
        category_message = (
            "⏰ *Lembretes:*\n"
            "* `/add_lembrete` - Adiciona um novo lembrete com data e hora.\n"
            "* `/ver_lembretes` - Vê todos os seus lembretes.\n"
            "* `/apagar_lembrete` - Apaga um lembrete existente.\n\n"
            "Nunca mais esqueça de nada importante!"
        )
    elif category == "general":
        category_message = (
            "✨ *Comandos Gerais:*\n"
            "* `/start` - Inicia uma conversa comigo e te cumprimenta.\n"
            "* `/ajuda` - Mostra este menu de ajuda.\n"
            "* `/cancelar` - Cancela qualquer operação em andamento.\n\n"
            "Estou sempre aprendendo e disponível para te ajudar!"
        )
    elif category == "accounts":
        category_message = (
            "💰 *Contas Financeiras:*\n"
            "* `/contas` - Abre o menu de gerenciamento de contas.\n"
            "  * Adicionar conta/despesa\n"
            "  * Adicionar entrada (salário, renda extra)\n"
            "  * Marcar conta como paga\n"
            "  * Ver saldo e contas\n"
            "  * Deletar contas/entradas\n\n"
            "Mantenha suas finanças organizadas!"
        )
    else:
        category_message = "Categoria de ajuda desconhecida."

    keyboard = [
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="help_category:main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=escape_markdown(category_message, version=2),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logger.info(f"Menu de ajuda da categoria '{category}' enviado para {query.from_user.id}.")
    return ConversationHandler.END


# --- Funções para Frases Personalizadas ---

async def new_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar uma nova frase."""
    user_id = update.effective_user.id
    logger.info(f"Comando /addfrase recebido de {user_id}.")
    await update.message.reply_text("Qual frase ou palavra deve *ativar* a minha resposta?")
    return GETTING_TRIGGER_PHRASE

async def get_trigger_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de gatilho e pede a frase de resposta."""
    user_id = update.effective_user.id
    trigger_phrase = update.message.text.strip()
    if not trigger_phrase:
        await update.message.reply_text("A frase de gatilho não pode ser vazia. Tente novamente.")
        return GETTING_TRIGGER_PHRASE

    context.user_data['trigger_phrase'] = trigger_phrase
    logger.info(f"Gatilho '{trigger_phrase}' recebido de {user_id}.")
    await update.message.reply_text(f"Entendi! E qual deve ser a minha *resposta* para '{escape_markdown(trigger_phrase, version=2)}'?")
    return GETTING_RESPONSE_PHRASE

async def get_response_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de resposta e salva a frase personalizada."""
    user_id = update.effective_user.id
    response_phrase = update.message.text.strip()
    trigger_phrase = context.user_data.get('trigger_phrase')

    if not response_phrase:
        await update.message.reply_text("A frase de resposta não pode ser vazia. Tente novamente.")
        return GETTING_RESPONSE_PHRASE # CORRIGIDO AQUI: Typo de "PHASE" para "PHRASE"

    if db.add_personal_phrase(user_id, trigger_phrase, response_phrase):
        await update.message.reply_text(
            escape_markdown(f"🎉 Frase personalizada adicionada!\nQuando você disser: '{trigger_phrase}'\nEu responderei: '{response_phrase}'", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Frase personalizada adicionada por {user_id}: '{trigger_phrase}' -> '{response_phrase}'.")
    else:
        await update.message.reply_text(
            escape_markdown("❌ Ops! Já existe uma frase com esse gatilho. Use /minhasfrases para ver suas frases.", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Falha ao adicionar frase, gatilho '{trigger_phrase}' já existe para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

async def view_my_phrases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vê as frases personalizadas do usuário."""
    user_id = update.effective_user.id
    phrases = db.get_user_personal_phrases(user_id)
    if phrases:
        message_text = "📚 Suas frases personalizadas:\n\n"
        for phrase_id, trigger, response in phrases:
            # Escapa o MarkdownV2 para garantir a exibição correta
            escaped_trigger = escape_markdown(trigger, version=2)
            escaped_response = escape_markdown(response, version=2)
            message_text += f"**ID: {phrase_id}**\n`Gatilho`: {escaped_trigger}\n`Resposta`: {escaped_response}\n\n"
        await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Frases personalizadas exibidas para {user_id}.")
    else:
        await update.message.reply_text("Você ainda não adicionou nenhuma frase personalizada. Use /addfrase para adicionar uma!")
        logger.info(f"Nenhuma frase personalizada encontrada para {user_id}.")

async def delete_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar uma frase."""
    user_id = update.effective_user.id
    logger.info(f"Comando /apagarfrase recebido de {user_id}.")
    phrases = db.get_user_personal_phrases(user_id)
    if not phrases:
        await update.message.reply_text("Você não tem nenhuma frase personalizada para apagar.")
        return ConversationHandler.END

    phrases_list = "📚 Suas frases personalizadas:\n\n"
    for phrase_id, trigger, response in phrases:
        escaped_trigger = escape_markdown(trigger, version=2)
        escaped_response = escape_markdown(response, version=2)
        phrases_list += f"**ID: {phrase_id}**\n`Gatilho`: {escaped_trigger}\n`Resposta`: {escaped_response}\n\n"
    
    phrases_list += "Por favor, me diga o *ID* da frase que você quer apagar."
    await update.message.reply_text(phrases_list, parse_mode=ParseMode.MARKDOWN_V2)
    return GETTING_PHRASE_ID_TO_DELETE

async def delete_phrase_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga a frase personalizada."""
    user_id = update.effective_user.id
    try:
        phrase_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            escape_markdown("Por favor, insira um ID de frase válido (um número).", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return GETTING_PHRASE_ID_TO_DELETE

    if db.delete_personal_phrase(phrase_id, user_id):
        await update.message.reply_text(
            escape_markdown(f"🗑️ Frase ID **{phrase_id}** apagada com sucesso!", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Frase ID {phrase_id} apagada por {user_id}.")
    else:
        await update.message.reply_text(
            escape_markdown(f"❌ Não foi possível apagar a frase ID **{phrase_id}**. Verifique se o ID está correto.", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Falha ao apagar frase ID {phrase_id} por {user_id}.")

    context.user_data.clear()
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
    # update.callback_query pode vir de um botão "Cancelar"
    if update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.data == "help_category:main_menu":
            # Se for para voltar ao menu principal de ajuda via callback, chama a função correta
            await send_main_help_menu(update, context)
        else:
            await update.callback_query.edit_message_text(escape_markdown("Operação cancelada.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(escape_markdown("Operação cancelada. Estou à disposição para o que precisar!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Diálogo cancelado por {update.effective_user.id}.")
    context.user_data.clear() # Limpa os dados do usuário para encerrar o diálogo
    return ConversationHandler.END