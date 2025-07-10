# account_handlers.py

import datetime
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode # Importado para ParseMode.MARKDOWN_V2
from telegram.helpers import escape_markdown # Importado para escapar texto Markdown

import accounts_db # Certifique-se de que esta linha está aqui!

logger = logging.getLogger(__name__)

# --- Estados para o ConversationHandler de Contas (valores altos para evitar conflitos) ---
ADD_ACCOUNT_NAME = 100
ADD_ACCOUNT_AMOUNT = 101
ADD_ACCOUNT_DUE_DATE = 102
ADD_ACCOUNT_RECURRENCE = 103
ADD_ACCOUNT_PARCEL_COUNT = 104

GET_ACCOUNT_ID_TO_MARK = 110

GET_ACCOUNT_ID_TO_DELETE = 120

ADD_INCOME_DESCRIPTION = 130
ADD_INCOME_AMOUNT = 131
ADD_INCOME_DATE = 132

GET_INCOME_ID_TO_DELETE = 140

VIEW_ACCOUNTS_MENU = 150 # Estado para o menu principal de contas (pode ser usado como retorno)

# --- Funções de Handler para Contas Financeiras ---

async def accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe o menu principal de gerenciamento de contas."""
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("➕ Adicionar Conta/Despesa", callback_data="accounts_action:add_account")],
        [InlineKeyboardButton("➕ Adicionar Entrada (Salário, Renda)", callback_data="accounts_action:add_income")],
        [InlineKeyboardButton("✅ Marcar Conta como Paga", callback_data="accounts_action:mark_paid")],
        [InlineKeyboardButton("📊 Ver Contas e Saldo", callback_data="accounts_action:view_accounts")],
        [InlineKeyboardButton("💸 Ver Entradas", callback_data="accounts_action:view_incomes")],
        [InlineKeyboardButton("🗑️ Deletar Conta", callback_data="accounts_action:delete_account")],
        [InlineKeyboardButton("🗑️ Deletar Entrada", callback_data="accounts_action:delete_income")],
        [InlineKeyboardButton("↩️ Voltar ao Menu Principal", callback_data="help_category:main_menu")] # Integração com menu de ajuda
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    current_month = datetime.datetime.now().month
    current_year = datetime.datetime.now().year
    summary = accounts_db.get_financial_summary(user_id, current_month, current_year)

    message_text = (
        f"💰 *Seu Resumo Financeiro ({current_month}/{current_year}):*\n\n"
        f"  *Total Entradas*: `R$ {summary['total_incomes']:.2f}`\n"
        f"  *Total Contas a Pagar*: `R$ {summary['total_accounts_due_this_month']:.2f}`\n"
        f"  *Contas Pagas*: `R$ {summary['paid_accounts_this_month']:.2f}`\n"
        f"  *Contas Pendentes*: `R$ {summary['unpaid_accounts_this_month']:.2f}`\n"
        f"  *Saldo Atual*: `R$ {summary['balance']:.2f}`\n\n"
        "Selecione uma opção abaixo:"
    )

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text=escape_markdown(message_text, version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    elif update.message:
        await update.message.reply_text(
            text=escape_markdown(message_text, version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    logger.info(f"Menu de contas exibido para {user_id}.")
    return VIEW_ACCOUNTS_MENU # Retorna ao estado do menu principal de contas

async def handle_accounts_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com a seleção de opções no menu principal de contas."""
    query = update.callback_query
    await query.answer()
    action = query.data.split(':')[1]

    # Aqui, você pode ter uma lógica para cada ação que não inicia um ConversationHandler,
    # ou simplesmente retornar ao estado VIEW_ACCOUNTS_MENU se for um "voltar".
    if action == "main_menu":
        # Se for para voltar ao menu principal do bot (ajuda)
        return await accounts_menu(update, context)
    
    # Para outras ações que iniciam ConversationHandlers, eles são gerenciados em main.py
    # Então, este handler apenas confirma e pode manter o usuário no estado VIEW_ACCOUNTS_MENU
    # ou fazer uma transição de estado se necessário.
    
    # Por exemplo, se uma ação não inicia um novo ConversationHandler, mas precisa de uma resposta direta:
    # if action == "some_direct_action":
    #     await query.edit_message_text(escape_markdown("Ação direta realizada!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
    return VIEW_ACCOUNTS_MENU # Permanece no menu de contas após a seleção

# --- Adicionar Conta/Despesa ---

async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para adicionar uma nova conta."""
    user_id = update.effective_user.id
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(escape_markdown("Qual o nome da conta/despesa (ex: Aluguel, Supermercado)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
         await update.message.reply_text(escape_markdown("Qual o nome da conta/despesa (ex: Aluguel, Supermercado)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Iniciando add_account_flow para {user_id}.")
    return ADD_ACCOUNT_NAME

async def get_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da conta."""
    context.user_data['account_name'] = update.message.text.strip()
    await update.message.reply_text(escape_markdown("Qual o valor dessa conta (ex: 1500.50)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return ADD_ACCOUNT_AMOUNT

async def get_account_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o valor da conta."""
    try:
        amount = float(update.message.text.strip().replace(',', '.'))
        if amount <= 0:
            await update.message.reply_text(escape_markdown("O valor deve ser um número positivo. Tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            return ADD_ACCOUNT_AMOUNT
        context.user_data['account_amount'] = amount
        await update.message.reply_text(escape_markdown("Qual a data de vencimento (AAAA-MM-DD)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ADD_ACCOUNT_DUE_DATE
    except ValueError:
        await update.message.reply_text(escape_markdown("Valor inválido. Por favor, insira um número (ex: 1500.50).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ADD_ACCOUNT_AMOUNT

async def get_account_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data de vencimento da conta."""
    date_str = update.message.text.strip()
    try:
        # Tenta analisar a data no formato AAAA-MM-DD
        datetime.datetime.strptime(date_str, '%Y-%m-%d')
        context.user_data['account_due_date'] = date_str

        keyboard = [
            [InlineKeyboardButton("Sem Recorrência", callback_data="none")],
            [InlineKeyboardButton("Mensal (Indefinido)", callback_data="indefinite")],
            [InlineKeyboardButton("Parcelado (Nº de Parcelas)", callback_data="fixed_parcel")],
            [InlineKeyboardButton("Cancelar", callback_data="cancel_account_add")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            escape_markdown("Esta conta é recorrente?", version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ADD_ACCOUNT_RECURRENCE
    except ValueError:
        await update.message.reply_text(escape_markdown("Formato de data inválido. Use AAAA-MM-DD (ex: 2025-07-25).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ADD_ACCOUNT_DUE_DATE

async def get_account_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o tipo de recorrência da conta."""
    query = update.callback_query
    await query.answer()
    recurrence = query.data

    context.user_data['account_recurrence'] = recurrence

    if recurrence == 'fixed_parcel':
        await query.edit_message_text(escape_markdown("Quantas parcelas (número inteiro)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ADD_ACCOUNT_PARCEL_COUNT
    else: # 'none' ou 'indefinite'
        name = context.user_data['account_name']
        amount = context.user_data['account_amount']
        due_date = context.user_data['account_due_date']
        user_id = query.from_user.id

        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence):
            await query.edit_message_text(
                escape_markdown(f"🎉 Conta '{name}' (R$ {amount:.2f}) adicionada com sucesso como {recurrence}!", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info(f"Conta '{name}' adicionada por {user_id}.")
        else:
            await query.edit_message_text(
                escape_markdown("❌ Ops! Não foi possível adicionar a conta. Talvez ela já exista.", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.warning(f"Falha ao adicionar conta '{name}' para {user_id}.")
        
        context.user_data.clear()
        return ConversationHandler.END

async def get_account_parcel_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o número de parcelas para contas fixas."""
    try:
        parcel_count = int(update.message.text.strip())
        if parcel_count <= 0:
            await update.message.reply_text(escape_markdown("O número de parcelas deve ser um número inteiro positivo. Tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            return ADD_ACCOUNT_PARCEL_COUNT

        context.user_data['account_parcel_count'] = parcel_count

        name = context.user_data['account_name']
        amount = context.user_data['account_amount']
        due_date = context.user_data['account_due_date']
        recurrence = context.user_data['account_recurrence']
        user_id = update.effective_user.id

        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence, parcel_count, current_parcel=1):
            await update.message.reply_text(
                escape_markdown(f"🎉 Conta '{name}' (R$ {amount:.2f}) adicionada com sucesso como parcelada em {parcel_count}x!", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info(f"Conta '{name}' adicionada por {user_id} como parcelada.")
        else:
            await update.message.reply_text(
                escape_markdown("❌ Ops! Não foi possível adicionar a conta. Talvez ela já exista.", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.warning(f"Falha ao adicionar conta parcelada '{name}' para {user_id}.")
        
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(escape_markdown("Número de parcelas inválido. Por favor, insira um número inteiro.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ADD_ACCOUNT_PARCEL_COUNT

# --- Marcar Conta como Paga ---

async def mark_account_paid_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para marcar uma conta como paga."""
    user_id = update.effective_user.id
    current_month = datetime.datetime.now().month
    current_year = datetime.datetime.now().year
    accounts = accounts_db.get_monthly_accounts(user_id, current_month, current_year)

    if not accounts:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(escape_markdown("Você não tem contas registradas para marcar como pagas neste mês.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        elif update.message:
            await update.message.reply_text(escape_markdown("Você não tem contas registradas para marcar como pagas neste mês.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    message_text = "Selecione a conta para marcar como paga ou digite seu ID:\n\n"
    for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in accounts:
        status = "✅ PAGA" if is_paid else "❌ PENDENTE"
        
        # Formata a data de vencimento
        try:
            due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            due_date_display = due_date # Em caso de erro, exibe a string original
        
        # Adiciona informações de recorrência e parcela se aplicável
        recurrence_info = ""
        if recurrence == 'fixed_parcel' and parcel_count:
            recurrence_info = f" ({current_parcel}/{parcel_count}x)"
        elif recurrence == 'indefinite':
            recurrence_info = " (Recorrente)"

        message_text += escape_markdown(f"**ID: {acc_id}** - {name}\n  `R$ {amount:.2f} | Vencimento: {due_date_display}{recurrence_info} | Status: {status}`\n\n", version=2)
    
    keyboard = [[InlineKeyboardButton("↩️ Voltar", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

    logger.info(f"Iniciando mark_account_paid_flow para {user_id}.")
    return GET_ACCOUNT_ID_TO_MARK

async def mark_account_paid_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e marca a conta como paga."""
    user_id = update.effective_user.id
    try:
        account_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, insira um ID de conta válido (um número).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GET_ACCOUNT_ID_TO_MARK

    if accounts_db.mark_account_paid(account_id, user_id):
        await update.message.reply_text(
            escape_markdown(f"🎉 Conta ID **{account_id}** marcada como paga com sucesso!", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Conta ID {account_id} marcada como paga por {user_id}.")
    else:
        await update.message.reply_text(
            escape_markdown(f"❌ Não foi possível marcar a conta ID **{account_id}** como paga. Verifique se o ID está correto ou se ela já está paga.", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Falha ao marcar conta ID {account_id} como paga para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Deletar Conta ---

async def delete_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para deletar uma conta."""
    user_id = update.effective_user.id
    current_month = datetime.datetime.now().month
    current_year = datetime.datetime.now().year
    accounts = accounts_db.get_monthly_accounts(user_id, current_month, current_year)

    if not accounts:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(escape_markdown("Você não tem contas registradas para deletar neste mês.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        elif update.message:
            await update.message.reply_text(escape_markdown("Você não tem contas registradas para deletar neste mês.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    message_text = "Digite o *ID* da conta que deseja deletar:\n\n"
    for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in accounts:
        status = "✅ PAGA" if is_paid else "❌ PENDENTE"
        try:
            due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            due_date_display = due_date
        
        recurrence_info = ""
        if recurrence == 'fixed_parcel' and parcel_count:
            recurrence_info = f" ({current_parcel}/{parcel_count}x)"
        elif recurrence == 'indefinite':
            recurrence_info = " (Recorrente)"

        message_text += escape_markdown(f"**ID: {acc_id}** - {name}\n  `R$ {amount:.2f} | Vencimento: {due_date_display}{recurrence_info} | Status: {status}`\n\n", version=2)
    
    keyboard = [[InlineKeyboardButton("↩️ Voltar", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Iniciando delete_account_flow para {user_id}.")
    return GET_ACCOUNT_ID_TO_DELETE

async def delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e deleta a conta."""
    user_id = update.effective_user.id
    try:
        account_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, insira um ID de conta válido (um número).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GET_ACCOUNT_ID_TO_DELETE

    if accounts_db.delete_monthly_account(account_id, user_id):
        await update.message.reply_text(
            escape_markdown(f"🗑️ Conta ID **{account_id}** deletada com sucesso!", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Conta ID {account_id} deletada por {user_id}.")
    else:
        await update.message.reply_text(
            escape_markdown(f"❌ Não foi possível deletar a conta ID **{account_id}**. Verifique se o ID está correto.", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Falha ao deletar conta ID {account_id} para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Adicionar Entrada (Rendimento) ---

async def add_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para adicionar uma nova entrada de rendimento."""
    user_id = update.effective_user.id
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(escape_markdown("Qual a descrição da entrada (ex: Salário, Freelance)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(escape_markdown("Qual a descrição da entrada (ex: Salário, Freelance)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Iniciando add_income_flow para {user_id}.")
    return ADD_INCOME_DESCRIPTION

async def get_income_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a descrição da entrada."""
    context.user_data['income_description'] = update.message.text.strip()
    await update.message.reply_text(escape_markdown("Qual o valor da entrada (ex: 3000.00)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return ADD_INCOME_AMOUNT

async def get_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o valor da entrada."""
    try:
        amount = float(update.message.text.strip().replace(',', '.'))
        if amount <= 0:
            await update.message.reply_text(escape_markdown("O valor deve ser um número positivo. Tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            return ADD_INCOME_AMOUNT
        context.user_data['income_amount'] = amount
        await update.message.reply_text(escape_markdown("Qual a data que você recebeu (AAAA-MM-DD)?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ADD_INCOME_DATE
    except ValueError:
        await update.message.reply_text(escape_markdown("Valor inválido. Por favor, insira um número (ex: 3000.00).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ADD_INCOME_AMOUNT

async def get_income_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data da entrada e salva."""
    date_str = update.message.text.strip()
    try:
        datetime.datetime.strptime(date_str, '%Y-%m-%d')
        context.user_data['income_date'] = date_str

        description = context.user_data['income_description']
        amount = context.user_data['income_amount']
        user_id = update.effective_user.id

        if accounts_db.add_financial_income(user_id, description, amount, date_str):
            await update.message.reply_text(
                escape_markdown(f"🎉 Entrada '{description}' (R$ {amount:.2f}) adicionada com sucesso!", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info(f"Entrada '{description}' adicionada por {user_id}.")
        else:
            await update.message.reply_text(
                escape_markdown("❌ Ops! Não foi possível adicionar a entrada. Talvez ela já exista.", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.warning(f"Falha ao adicionar entrada '{description}' para {user_id}.")
        
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(escape_markdown("Formato de data inválido. Use AAAA-MM-DD (ex: 2025-07-01).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ADD_INCOME_DATE

# --- Deletar Entrada ---

async def delete_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para deletar uma entrada de rendimento."""
    user_id = update.effective_user.id
    current_month = datetime.datetime.now().month
    current_year = datetime.datetime.now().year
    incomes = accounts_db.get_financial_incomes(user_id, current_month, current_year)

    if not incomes:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(escape_markdown("Você não tem entradas registradas para deletar neste mês.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        elif update.message:
            await update.message.reply_text(escape_markdown("Você não tem entradas registradas para deletar neste mês.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    message_text = "Digite o *ID* da entrada que deseja deletar:\n\n"
    for inc_id, description, amount, income_date_db in incomes:
        try:
            income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            income_date_display = income_date_db
        message_text += escape_markdown(f"**ID: {inc_id}** - {description}\n  `R$ {amount:.2f} | Data: {income_date_display}`\n\n", version=2)
    
    keyboard = [[InlineKeyboardButton("↩️ Voltar", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Iniciando delete_income_flow para {user_id}.")
    return GET_INCOME_ID_TO_DELETE

async def delete_income_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e deleta a entrada."""
    user_id = update.effective_user.id
    try:
        income_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, insira um ID de entrada válido (um número).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GET_INCOME_ID_TO_DELETE

    if accounts_db.delete_financial_income(income_id, user_id):
        await update.message.reply_text(
            escape_markdown(f"🗑️ Entrada ID **{income_id}** deletada com sucesso!", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Entrada ID {income_id} deletada por {user_id}.")
    else:
        await update.message.reply_text(
            escape_markdown(f"❌ Não foi possível deletar a entrada ID **{income_id}**. Verifique se o ID está correto.", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Falha ao deletar entrada ID {income_id} para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Visualizar Contas Detalhadas ---

async def view_detailed_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe uma lista detalhada das contas/despesas do usuário para o mês atual."""
    user_id = update.effective_user.id
    current_month = datetime.datetime.now().month
    current_year = datetime.datetime.now().year
    accounts = accounts_db.get_monthly_accounts(user_id, current_month, current_year)

    message_text = f"📊 *Suas Contas/Despesas ({current_month}/{current_year}):*\n\n"
    if not accounts:
        message_text += "Você não tem contas registradas para este mês."
    else:
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in accounts:
            status = "✅ PAGA" if is_paid else "❌ PENDENTE"
            
            try:
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                due_date_display = due_date # Em caso de erro, exibe a string original
            
            recurrence_info = ""
            if recurrence == 'fixed_parcel' and parcel_count:
                recurrence_info = f" ({current_parcel}/{parcel_count}x)"
            elif recurrence == 'indefinite':
                recurrence_info = " (Recorrente)"

            message_text += f"**ID: {acc_id}** - {name}\n  `R$ {amount:.2f} | Vencimento: {due_date_display}{recurrence_info} | Status: {status}`\n\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Contas detalhadas exibidas para {user_id}.")
    return VIEW_ACCOUNTS_MENU # Retorna ao menu de contas

# --- Visualizar Entradas Detalhadas ---

async def view_detailed_incomes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe uma lista detalhada das entradas/rendimentos do usuário para o mês atual."""
    user_id = update.effective_user.id
    current_month = datetime.datetime.now().month
    current_year = datetime.datetime.now().year
    incomes = accounts_db.get_financial_incomes(user_id, current_month, current_year)

    message_text = f"💸 *Suas Entradas/Rendimentos ({current_month}/{current_year}):*\n\n"
    if not incomes:
        message_text += "Você não tem entradas registradas para este mês."
    else:
        for income_id, description, amount, income_date_db in incomes:
            try:
                income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                income_date_display = income_date_db
            message_text += f"**ID: {income_id}** - {description}\n  `R$ {amount:.2f} | Data: {income_date_display}`\n\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Entradas detalhadas exibidas para {user_id}.")
    return VIEW_ACCOUNTS_MENU # Retorna ao menu de contas

# --- Função de Cancelamento ---

async def cancel_accounts_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela o fluxo atual de contas financeiras."""
    # Garante que a resposta seja enviada para a origem correta
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(escape_markdown("Operação de contas cancelada. ✅", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(escape_markdown("Operação de contas cancelada. ✅", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Diálogo de contas cancelado por {update.effective_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END # Encerra o ConversationHandler atual