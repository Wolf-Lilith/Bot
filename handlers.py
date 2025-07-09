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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await send_main_help_menu(update, context, update.message.message_id, update.message.chat_id)
    logging.info(f"Comando /ajuda recebido de {user_id}.")

async def send_main_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id=None, chat_id=None):
    """Função auxiliar para enviar/editar o menu de ajuda principal."""
    keyboard = [
        [InlineKeyboardButton("Frases Personalizadas", callback_data="help_category:phrases")],
        [InlineKeyboardButton("Listas", callback_data="help_category:lists")],
        [InlineKeyboardButton("Lembretes", callback_data="help_category:reminders")],
        [InlineKeyboardButton("Finanças", callback_data="help_category:accounts")], # Adicionado para finanças
        [InlineKeyboardButton("Comandos Gerais", callback_data="help_category:general")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = escape_markdown(
        "👋 Olá! Sou sua assistente pessoal, Lilith. Posso te ajudar com várias coisas! Escolha uma categoria abaixo ou digite / para ver os comandos diretos.", 
        version=2
    )

    if message_id and chat_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logging.error(f"Erro ao editar mensagem do menu principal: {e}")
            await update.effective_message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)


async def handle_help_category_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id # <--- FIX: Correta para CallbackQuery

    category = query.data.split(':')[-1]
    
    commands_map = {
        "phrases": [
            ("/addfrase", "Adiciona uma frase personalizada para eu responder."),
            ("/minhasfrases", "Vê suas frases personalizadas."),
            ("/apagarfrase", "Apaga uma frase personalizada existente.")
        ],
        "lists": [
            ("/novalista", "Cria uma nova lista (ex: de compras, tarefas)."),
            ("/listas", "Vê todas as suas listas."),
            ("/additem", "Adiciona um item a uma lista existente."),
            ("/verlista", "Vê os itens de uma lista específica."),
            ("/marcaritem", "Marca/desmarca um item de lista como concluído."),
            ("/removeritem", "Remove um item de uma lista."),
            ("/apagarlista", "Apaga uma lista inteira.")
        ],
        "reminders": [
            ("/novolembrete", "Cria um novo lembrete."),
            ("/ver_lembretes", "Vê todos os seus lembretes agendados."),
            ("/apagar_lembrete", "Apaga um lembrete existente.")
        ],
        "accounts": [ # Novos comandos de finanças
            ("/addconta", "Adiciona uma nova conta a ser paga."),
            ("/addentrada", "Adiciona um novo rendimento financeiro."),
            ("/minhascontas", "Vê suas contas detalhadas."),
            ("/minhasentradas", "Vê suas entradas detalhadas."),
            ("/marcarpagaconta", "Marca uma conta como paga."),
            ("/apagarconta", "Apaga uma conta existente."),
            ("/apagarentrada", "Apaga uma entrada existente.")
        ],
        "general": [
            ("/start", "Inicia o bot e te cumprimenta."),
            ("/ajuda", "Mostra o menu de ajuda interativo."),
            ("/cancelar", "Cancela qualquer operação em andamento.")
        ]
    }

    message_text = ""
    if category in commands_map:
        message_text += escape_markdown(f"📚 Comandos de {category.capitalize()}:\\n\\n", version=2)
        for cmd, desc in commands_map[category]:
            message_text += escape_markdown(f"*{cmd}*: {desc}\\n", version=2)
    else:
        message_text = escape_markdown("Categoria de ajuda desconhecida.", version=2)

    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="help_category:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=message_markdown,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logging.info(f"Usuário {user_id} visualizou categoria de ajuda: {category}.")


# --- Frases Personalizadas ---

async def new_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar uma nova frase personalizada."""
    user_id = update.effective_user.id
    context.user_data['user_id'] = user_id # Armazena user_id para uso posterior
    await update.message.reply_text("Certo! Qual a *frase ou palavra gatilho* (trigger) que você quer que eu responda?", parse_mode=ParseMode.MARKDOWN)
    logging.info(f"Diálogo de nova frase iniciado por {user_id}.")
    return GETTING_TRIGGER_PHRASE

async def get_trigger_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase gatilho e pede a frase de resposta."""
    trigger_phrase = update.message.text.strip()
    user_id = context.user_data.get('user_id')
    
    if db.get_response_for_trigger(user_id, trigger_phrase):
        await update.message.reply_text(f"⚠️ Essa frase gatilho (`{trigger_phrase}`) já existe. Por favor, escolha outra ou apague a existente com /apagarfrase.", parse_mode=ParseMode.MARKDOWN)
        logging.info(f"Usuário {user_id} tentou adicionar frase gatilho duplicada: '{trigger_phrase}'.")
        context.user_data.clear() # Limpa o diálogo para evitar loop
        return ConversationHandler.END # Encerra a conversa
    
    context.user_data['trigger_phrase'] = trigger_phrase
    await update.message.reply_text(f"Ok, se alguém disser '{trigger_phrase}', o que você quer que eu responda?", parse_mode=ParseMode.MARKDOWN)
    logging.info(f"Frase gatilho '{trigger_phrase}' recebida de {user_id}.")
    return GETTING_RESPONSE_PHRASE

async def get_response_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frase de resposta e salva a frase personalizada."""
    response_phrase = update.message.text.strip()
    user_id = context.user_data.get('user_id')
    trigger_phrase = context.user_data.get('trigger_phrase')

    if db.add_personal_phrase(user_id, trigger_phrase, response_phrase):
        await update.message.reply_text(f"🎉 Entendi! Se alguém disser '{trigger_phrase}', eu responderei: '{response_phrase}'.", parse_mode=ParseMode.MARKDOWN)
        logging.info(f"Frase personalizada '{trigger_phrase}' -> '{response_phrase}' adicionada por {user_id}.")
    else:
        await update.message.reply_text("❌ Ops, não consegui salvar sua frase personalizada. Tente novamente!")
        logging.error(f"Erro ao adicionar frase personalizada para {user_id}.")

    context.user_data.clear() # Limpa os dados do usuário para encerrar o diálogo
    return ConversationHandler.END

async def view_my_phrases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra todas as frases personalizadas do usuário."""
    user_id = update.effective_user.id
    phrases = db.get_personal_phrases(user_id)

    if not phrases:
        await update.message.reply_text("Você ainda não tem nenhuma frase personalizada. Use /addfrase para adicionar uma!")
        logging.info(f"Nenhuma frase personalizada encontrada para {user_id}.")
        return

    message_text = "📖 Suas frases personalizadas:\n\n"
    for phrase_id, trigger, response in phrases:
        message_text += f"**ID: {phrase_id}**\n*Gatilho*: `{trigger}`\n*Resposta*: `{response}`\n\n"
    
    # Escapar o texto da mensagem antes de enviar com MarkdownV2
    message_markdown = escape_markdown(message_text, version=2)
    await update.message.reply_text(message_markdown, parse_mode=ParseMode.MARKDOWN_V2)
    logging.info(f"Frases personalizadas exibidas para {user_id}.")

async def delete_phrase_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar uma frase personalizada."""
    user_id = update.effective_user.id
    context.user_data['user_id'] = user_id
    
    phrases = db.get_personal_phrases(user_id)
    if not phrases:
        await update.message.reply_text("Você não tem nenhuma frase personalizada para apagar.")
        context.user_data.clear()
        return ConversationHandler.END

    message_text = "Qual o *ID* da frase que você quer apagar? (Use /minhasfrases para ver os IDs)\n\n"
    for phrase_id, trigger, response in phrases:
        message_text += f"**ID: {phrase_id}** - `{trigger}`\n"
    
    # Escapar o texto da mensagem antes de enviar com MarkdownV2
    message_markdown = escape_markdown(message_text, version=2)
    await update.message.reply_text(message_markdown, parse_mode=ParseMode.MARKDOWN_V2)
    logging.info(f"Diálogo de apagar frase iniciado por {user_id}.")
    return GETTING_PHRASE_ID_TO_DELETE

async def confirm_delete_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID da frase a ser apagada e confirma a exclusão."""
    user_id = context.user_data.get('user_id')
    
    try:
        phrase_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Por favor, digite um ID de frase válido (um número).")
        return GETTING_PHRASE_ID_TO_DELETE # Volta para o mesmo estado
    
    if db.delete_personal_phrase(phrase_id, user_id):
        await update.message.reply_text(f"🗑️ Frase ID **{phrase_id}** apagada com sucesso!", parse_mode=ParseMode.MARKDOWN_V2)
        logging.info(f"Frase ID {phrase_id} apagada por {user_id}.")
    else:
        await update.message.reply_text(f"❌ Não foi possível apagar a frase ID **{phrase_id}**. Verifique se o ID está correto ou se a frase pertence a você.", parse_mode=ParseMode.MARKDOWN_V2)
        logging.warning(f"Falha ao apagar frase ID {phrase_id} por {user_id}.")

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
    
    logging.info(f"Diálogo cancelado por {update.effective_user.id}.")
    context.user_data.clear() # Limpa quaisquer dados de conversa pendentes
    return ConversationHandler.END