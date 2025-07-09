import datetime
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

import accounts_db # Certifique-se de que esta linha está aqui!

logger = logging.getLogger(__name__)

# --- Estados para o ConversationHandler de Contas (RENOMEADOS PARA EVITAR CONFLITOS) ---
ADD_ACCOUNT_NAME = 300
ADD_ACCOUNT_AMOUNT = 301
ADD_ACCOUNT_DUE_DATE = 302
ADD_ACCOUNT_RECURRENCE = 303
ADD_ACCOUNT_PARCEL_COUNT = 304

GET_ACCOUNT_ID_TO_EDIT = 310
EDIT_ACCOUNT_FIELD = 311
EDIT_ACCOUNT_NEW_VALUE = 312

GET_ACCOUNT_ID_TO_MARK = 320

GET_ACCOUNT_ID_TO_DELETE = 330

ADD_INCOME_DESCRIPTION = 340
ADD_INCOME_AMOUNT = 341
ADD_INCOME_DATE = 342

GET_INCOME_ID_TO_DELETE = 350

VIEW_ACCOUNTS_MENU = 360 # Estado para o menu principal de contas
VIEW_DETAILED_ACCOUNTS = 361 # Novo estado para ver contas detalhadas
VIEW_DETAILED_INCOMES = 362 # Novo estado para ver entradas detalhadas


# --- Funções de Handler para Contas Financeiras ---

async def accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe o menu principal de gerenciamento de contas."""
    user_id = update.effective_user.id
    # Obter um resumo financeiro
    summary = accounts_db.get_financial_summary(user_id)

    total_incomes_str = f"R$ {summary['total_incomes']:.2f}"
    total_due_str = f"R$ {summary['unpaid_accounts_this_month']:.2f}"
    balance_str = f"R$ {summary['balance']:.2f}"
    
    # Adicionar o emoji com base no saldo
    balance_emoji = "✅" if summary['balance'] >= 0 else "❌"

    message_text = (
        f"**💰 Menu de Contas Financeiras**\\n\\n"
        f"**Total de Entradas (Mês):** `{total_incomes_str}`\\n"
        f"**Contas a Pagar (Mês):** `{total_due_str}`\\n"
        f"**Saldo Atual:** `{balance_emoji} {balance_str}`\\n\\n"
        "O que você gostaria de fazer?"
    )

    keyboard = [
        [InlineKeyboardButton("👀 Ver Contas Detalhadas", callback_data="accounts_action:view_accounts")],
        [InlineKeyboardButton("👀 Ver Entradas Detalhadas", callback_data="accounts_action:view_incomes")],
        [InlineKeyboardButton("➕ Adicionar Conta", callback_data="accounts_action:add_account")],
        [InlineKeyboardButton("➕ Adicionar Entrada", callback_data="accounts_action:add_income")],
        [InlineKeyboardButton("✅ Marcar Conta como Paga", callback_data="accounts_action:mark_paid")],
        [InlineKeyboardButton("🗑️ Apagar Conta", callback_data="accounts_action:delete_account")],
        [InlineKeyboardButton("🗑️ Apagar Entrada", callback_data="accounts_action:delete_income")],
        [InlineKeyboardButton("↩️ Voltar ao Menu Principal", callback_data="cancel_accounts_flow")] # Botão de cancelar
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    logger.info(f"Menu de contas exibido para {user_id}.")
    return VIEW_ACCOUNTS_MENU

async def handle_accounts_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com a seleção de botões no menu principal de contas."""
    query = update.callback_query
    await query.answer()
    action = query.data.split(':')[1]

    if action == "view_accounts":
        return await view_detailed_accounts(update, context)
    elif action == "view_incomes":
        return await view_detailed_incomes(update, context)
    elif action == "add_account":
        return await add_account_start(update, context)
    elif action == "add_income":
        return await add_income_start(update, context)
    elif action == "mark_paid":
        return await mark_account_paid_start(update, context)
    elif action == "delete_account":
        return await delete_account_start(update, context)
    elif action == "delete_income":
        return await delete_income_start(update, context)
    
    logger.warning(f"Ação de menu de contas desconhecida: {query.data}")
    await query.edit_message_text("Ação desconhecida. Por favor, tente novamente.")
    return VIEW_ACCOUNTS_MENU # Volta para o menu de contas


async def view_detailed_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe a lista detalhada de contas (despesas)."""
    user_id = update.effective_user.id
    accounts = accounts_db.get_user_accounts(user_id)

    message_text = "**🧾 Suas Contas (Despesas)**\\n\\n"
    if not accounts:
        message_text += "Você não tem nenhuma conta registrada. Use '➕ Adicionar Conta' para adicionar uma."
    else:
        for acc in accounts:
            paid_status = "✅ Paga" if acc['is_paid'] else "❌ A Pagar"
            due_date_display = datetime.datetime.strptime(acc['due_date'], '%Y-%m-%d').strftime('%d/%m/%Y')
            
            recurrence_info = ""
            if acc['recurrence'] == 'indefinite':
                recurrence_info = " (Recorrente: Indefinido)"
            elif acc['recurrence'] == 'fixed_parcel' and acc['parcel_count']:
                recurrence_info = f" (Parcela {acc['current_parcel']}/{acc['parcel_count']})"

            message_text += (
                f"**ID: {acc['id']}** - {acc['name']}\\n"
                f"  `R$ {acc['amount']:.2f} | Vencimento: {due_date_display} | {paid_status}`{recurrence_info}\\n\\n"
            )
    
    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    logger.info(f"Contas detalhadas exibidas para {user_id}.")
    return VIEW_ACCOUNTS_MENU # Retorna ao menu de contas

async def view_detailed_incomes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe a lista detalhada de entradas (rendimentos)."""
    user_id = update.effective_user.id
    incomes = accounts_db.get_user_incomes(user_id)

    message_text = "**💸 Suas Entradas (Rendimentos)**\\n\\n"
    if not incomes:
        message_text += "Você não tem nenhuma entrada registrada. Use '➕ Adicionar Entrada' para adicionar uma."
    else:
        for inc in incomes:
            income_id = inc['id']
            description = inc['description']
            amount = inc['amount']
            income_date_db = inc['income_date']
            income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
            message_text += f"**ID: {income_id}** - {description}\\n  `R$ {amount:.2f} | Data: {income_date_display}`\\n\\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    logger.info(f"Entradas detalhadas exibidas para {user_id}.")
    return VIEW_ACCOUNTS_MENU # Retorna ao menu de contas


# --- Adicionar Conta ---
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar uma nova conta."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Ok! Qual o nome desta conta? (Ex: 'Aluguel', 'Internet', 'Cartão de Crédito')")
    logger.info(f"Diálogo 'add_account' iniciado por {update.effective_user.id}.")
    return ADD_ACCOUNT_NAME

async def get_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['account_name'] = update.message.text.strip()
    await update.message.reply_text("Qual o valor dessa conta? (Ex: '150.00', '79.90')")
    return ADD_ACCOUNT_AMOUNT

async def get_account_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(',', '.').strip())
        if amount <= 0:
            raise ValueError
        context.user_data['account_amount'] = amount
        await update.message.reply_text("Qual a data de vencimento? (Formato: DD/MM/AAAA ou AAAA-MM-DD)")
        return ADD_ACCOUNT_DUE_DATE
    except ValueError:
        await update.message.reply_text("Valor inválido. Por favor, digite um número positivo para o valor da conta.")
        return ADD_ACCOUNT_AMOUNT

async def get_account_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date_str = update.message.text.strip()
    try:
        # Tenta parsear nos formatos comuns
        if '/' in date_str: # Assume DD/MM/AAAA
            due_date = datetime.datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
        elif '-' in date_str: # Assume AAAA-MM-DD
            due_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
        else:
            raise ValueError("Formato de data inválido.")
        
        context.user_data['account_due_date'] = due_date
        
        keyboard = [
            [InlineKeyboardButton("Não Recorre", callback_data="recurrence:none")],
            [InlineKeyboardButton("Recorrente (Mensal)", callback_data="recurrence:indefinite")],
            [InlineKeyboardButton("Parcelado (Nº de Vezes)", callback_data="recurrence:fixed_parcel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Essa conta é recorrente ou parcelada?", reply_markup=reply_markup)
        return ADD_ACCOUNT_RECURRENCE
    except ValueError:
        await update.message.reply_text("Data inválida. Por favor, use o formato DD/MM/AAAA ou AAAA-MM-DD.")
        return ADD_ACCOUNT_DUE_DATE

async def get_account_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    recurrence = query.data.split(':')[1]
    context.user_data['account_recurrence'] = recurrence

    if recurrence == 'fixed_parcel':
        await query.edit_message_text("Quantas parcelas são? (Ex: '12')")
        return ADD_ACCOUNT_PARCEL_COUNT
    else:
        # Finaliza e salva a conta
        return await save_account(update, context)

async def get_account_parcel_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        parcel_count = int(update.message.text.strip())
        if parcel_count <= 0:
            raise ValueError
        context.user_data['account_parcel_count'] = parcel_count
        return await save_account(update, context)
    except ValueError:
        await update.message.reply_text("Número de parcelas inválido. Por favor, digite um número inteiro positivo.")
        return ADD_ACCOUNT_PARCEL_COUNT

async def save_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    name = context.user_data['account_name']
    amount = context.user_data['account_amount']
    due_date = context.user_data['account_due_date']
    recurrence = context.user_data.get('account_recurrence', 'none')
    parcel_count = context.user_data.get('account_parcel_count')

    if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence, parcel_count):
        response_message = f"Conta '{name}' de R$ {amount:.2f} adicionada com sucesso! ✅"
        logger.info(f"Conta '{name}' adicionada por {user_id}.")
    else:
        response_message = "❌ Erro ao adicionar conta. Por favor, tente novamente."
        logger.error(f"Falha ao adicionar conta '{name}' por {user_id}.")

    if update.callback_query:
        await update.callback_query.edit_message_text(response_message)
    else:
        await update.message.reply_text(response_message)
    
    context.user_data.clear()
    return ConversationHandler.END


# --- Adicionar Entrada (Rendimento) ---
async def add_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Ok! Qual a descrição desta entrada (rendimento)? (Ex: 'Salário', 'Freelance', 'Venda de item')")
    logger.info(f"Diálogo 'add_income' iniciado por {update.effective_user.id}.")
    return ADD_INCOME_DESCRIPTION

async def get_income_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['income_description'] = update.message.text.strip()
    await update.message.reply_text("Qual o valor desta entrada? (Ex: '1200.50')")
    return ADD_INCOME_AMOUNT

async def get_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.replace(',', '.').strip())
        if amount <= 0:
            raise ValueError
        context.user_data['income_amount'] = amount
        await update.message.reply_text("Qual a data que você recebeu esta entrada? (Formato: DD/MM/AAAA ou AAAA-MM-DD)")
        return ADD_INCOME_DATE
    except ValueError:
        await update.message.reply_text("Valor inválido. Por favor, digite um número positivo para o valor da entrada.")
        return ADD_INCOME_AMOUNT

async def get_income_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date_str = update.message.text.strip()
    user_id = update.effective_user.id
    try:
        if '/' in date_str:
            income_date = datetime.datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
        elif '-' in date_str:
            income_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
        else:
            raise ValueError("Formato de data inválido.")
        
        description = context.user_data['income_description']
        amount = context.user_data['income_amount']

        if accounts_db.add_financial_income(user_id, description, amount, income_date):
            await update.message.reply_text(f"Entrada '{description}' de R$ {amount:.2f} em {date_str} adicionada com sucesso! ✅")
            logger.info(f"Entrada '{description}' adicionada por {user_id}.")
        else:
            await update.message.reply_text("❌ Erro ao adicionar entrada. Por favor, tente novamente.")
            logger.error(f"Falha ao adicionar entrada '{description}' por {user_id}.")
        
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Data inválida. Por favor, use o formato DD/MM/AAAA ou AAAA-MM-DD.")
        return ADD_INCOME_DATE

# --- Apagar Conta ---
async def delete_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    accounts = accounts_db.get_user_accounts(user_id)

    if not accounts:
        await query.edit_message_text("Você não tem contas para apagar.")
        return ConversationHandler.END

    message_text = "Selecione a conta que deseja apagar (responda com o ID):\\n\\n"
    for acc in accounts:
        message_text += f"**ID: {acc['id']}** - {acc['name']} (R$ {acc['amount']:.2f})\\n"
    
    await query.edit_message_text(message_text, parse_mode='Markdown')
    logger.info(f"Diálogo 'delete_account' iniciado por {user_id}.")
    return GET_ACCOUNT_ID_TO_DELETE

async def confirm_delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    try:
        account_id = int(update.message.text.strip())
        account = accounts_db.get_account_by_id(account_id, user_id)
        if not account:
            await update.message.reply_text("ID da conta não encontrado ou não pertence a você. Por favor, tente novamente.")
            return GET_ACCOUNT_ID_TO_DELETE

        if accounts_db.delete_monthly_account(account_id, user_id):
            await update.message.reply_text(f"Conta '{account['name']}' (ID: {account_id}) apagada com sucesso! 🗑️")
            logger.info(f"Conta ID {account_id} apagada por {user_id}.")
        else:
            await update.message.reply_text("❌ Não foi possível apagar a conta. Por favor, tente novamente.")
            logger.error(f"Falha ao apagar conta ID {account_id} por {user_id}.")
    except ValueError:
        await update.message.reply_text("ID inválido. Por favor, digite um número.")
        return GET_ACCOUNT_ID_TO_DELETE
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Apagar Entrada ---
async def delete_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    incomes = accounts_db.get_user_incomes(user_id)

    if not incomes:
        await query.edit_message_text("Você não tem entradas para apagar.")
        return ConversationHandler.END

    message_text = "Selecione a entrada que deseja apagar (responda com o ID):\\n\\n"
    for inc in incomes:
        message_text += f"**ID: {inc['id']}** - {inc['description']} (R$ {inc['amount']:.2f})\\n"
    
    await query.edit_message_text(message_text, parse_mode='Markdown')
    logger.info(f"Diálogo 'delete_income' iniciado por {user_id}.")
    return GET_INCOME_ID_TO_DELETE

async def confirm_delete_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    try:
        income_id = int(update.message.text.strip())
        income = accounts_db.get_income_by_id(income_id, user_id)
        if not income:
            await update.message.reply_text("ID da entrada não encontrado ou não pertence a você. Por favor, tente novamente.")
            return GET_INCOME_ID_TO_DELETE

        if accounts_db.delete_financial_income(income_id, user_id):
            await update.message.reply_text(f"Entrada '{income['description']}' (ID: {income_id}) apagada com sucesso! 🗑️")
            logger.info(f"Entrada ID {income_id} apagada por {user_id}.")
        else:
            await update.message.reply_text("❌ Não foi possível apagar a entrada. Por favor, tente novamente.")
            logger.error(f"Falha ao apagar entrada ID {income_id} por {user_id}.")
    except ValueError:
        await update.message.reply_text("ID inválido. Por favor, digite um número.")
        return GET_INCOME_ID_TO_DELETE
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Marcar Conta como Paga ---
async def mark_account_paid_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    unpaid_accounts = accounts_db.get_unpaid_accounts(user_id)

    if not unpaid_accounts:
        await query.edit_message_text("Você não tem contas a pagar no momento. Todas as contas estão em dia! 🎉")
        return ConversationHandler.END

    message_text = "Selecione a conta que deseja marcar como PAGA (responda com o ID):\\n\\n"
    for acc in unpaid_accounts:
        due_date_display = datetime.datetime.strptime(acc['due_date'], '%Y-%m-%d').strftime('%d/%m/%Y')
        message_text += f"**ID: {acc['id']}** - {acc['name']} (R$ {acc['amount']:.2f}) - Vencimento: {due_date_display}\\n"
    
    await query.edit_message_text(message_text, parse_mode='Markdown')
    logger.info(f"Diálogo 'mark_paid' iniciado por {user_id}.")
    return GET_ACCOUNT_ID_TO_MARK

async def confirm_mark_account_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    try:
        account_id = int(update.message.text.strip())
        account = accounts_db.get_account_by_id(account_id, user_id)
        if not account:
            await update.message.reply_text("ID da conta não encontrado ou não pertence a você. Por favor, tente novamente.")
            return GET_ACCOUNT_ID_TO_MARK

        if accounts_db.mark_account_as_paid(account_id, user_id):
            await update.message.reply_text(f"Conta '{account['name']}' (ID: {account_id}) marcada como PAGA! ✅")
            logger.info(f"Conta ID {account_id} marcada como paga por {user_id}.")
        else:
            await update.message.reply_text("❌ Não foi possível marcar a conta como paga. Por favor, tente novamente.")
            logger.error(f"Falha ao marcar conta ID {account_id} como paga por {user_id}.")
    except ValueError:
        await update.message.reply_text("ID inválido. Por favor, digite um número.")
        return GET_ACCOUNT_ID_TO_MARK
    
    context.user_data.clear()
    return ConversationHandler.END


# --- Função de Cancelamento ---

async def cancel_accounts_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela o fluxo atual de contas financeiras."""
    # Garante que a resposta seja enviada para a origem correta
    if update.callback_query:
        await update.callback_query.answer()
        # Se for um callback de "Voltar ao Menu Principal", chamamos a função principal
        if update.callback_query.data == "accounts_action:main_menu" or update.callback_query.data == "cancel_accounts_flow":
            await accounts_menu(update, context) # Retorna para o menu principal de contas
        else:
            await update.callback_query.edit_message_text("Operação de contas cancelada. ✅")
    elif update.message:
        await update.message.reply_text("Operação de contas cancelada. ✅")
    
    logger.info(f"Diálogo de contas cancelado por {update.effective_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END