# account_handlers.py

import datetime
import calendar
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

import accounts_db # Importa o módulo de banco de dados para contas

logger = logging.getLogger(__name__)

# --- Estados para o ConversationHandler de Contas (valores altos para evitar conflitos) ---
ADD_ACCOUNT_NAME = 100
ADD_ACCOUNT_AMOUNT = 101
ADD_ACCOUNT_DUE_DATE = 102
ADD_ACCOUNT_RECURRENCE = 103
ADD_ACCOUNT_PARCEL_COUNT = 104
GETTING_ACCOUNT_DATE_FROM_CALENDAR = 105

GET_ACCOUNT_ID_TO_MARK = 110

GET_ACCOUNT_ID_TO_DELETE = 120 # Estado para deletar contas

ADD_INCOME_DESCRIPTION = 130
ADD_INCOME_AMOUNT = 131
ADD_INCOME_DATE = 132
GETTING_INCOME_DATE_FROM_CALENDAR = 133

GET_INCOME_ID_TO_DELETE = 140 # Estado para deletar entradas

VIEW_ACCOUNTS_MENU = 150
NAVIGATING_MONTHS = 160 # Estado para lidar com a navegação de meses no resumo/visualização

# --- Função Auxiliar para Enviar/Editar Mensagens ---
async def send_or_edit_message(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = ParseMode.MARKDOWN_V2):
    """
    Envia uma nova mensagem ou edita uma existente, dependendo da origem da atualização (callback_query ou message).
    Aplica escape_markdown automaticamente.
    """
    # Escapa apenas os caracteres especiais do Markdown V2
    escaped_text = escape_markdown(text, version=2)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(escaped_text, reply_markup=reply_markup, parse_mode=parse_mode)
    elif update.message:
        await update.message.reply_text(escaped_text, reply_markup=reply_markup, parse_mode=parse_mode)

# --- Funções de Handler para Contas Financeiras ---

async def accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe o menu principal de gerenciamento de contas, agora com navegação por mês e saldo flutuante."""
    user_id = update.effective_user.id
    
    # Recupera o mês e ano do user_data ou usa o atual
    # Usamos datetime.date.today() para pegar a data atual corretamente.
    today = datetime.date.today()
    current_month = context.user_data.get('current_accounts_month', today.month)
    current_year = context.user_data.get('current_accounts_year', today.year)

    # Salva o mês e ano atuais no user_data para persistência
    context.user_data['current_accounts_month'] = current_month
    context.user_data['current_accounts_year'] = current_year

    summary = accounts_db.get_financial_summary(user_id, current_month, current_year)

    # Formata o nome do mês
    month_name = datetime.date(current_year, current_month, 1).strftime('%B').capitalize()

    message_text = (
        f"💰 *Seu Resumo Financeiro ({month_name}/{current_year}):*\n\n"
        f"  *Saldo Inicial do Mês*: `R$ {summary['previous_month_balance']:.2f}`\n"
        f"  *Entradas no Mês*: `R$ {summary['total_incomes_this_month']:.2f}`\n"
        f"  *Contas a Pagar no Mês*: `R$ {summary['total_accounts_due_this_month']:.2f}`\n"
        f"  *Contas Pagas no Mês*: `R$ {summary['paid_accounts_this_month']:.2f}`\n"
        f"  *Contas Pendentes no Mês*: `R$ {summary['unpaid_accounts_this_month']:.2f}`\n"
        f"  *Saldo Líquido do Mês*: `R$ {summary['current_month_net_change']:.2f}`\n" # Apenas o que mudou no mês
        f"  *Saldo Final (Acumulado)*: `R$ {summary['final_balance_this_month']:.2f}`\n\n" # Saldo total acumulado
        "Selecione uma opção abaixo ou navegue pelos meses:"
    )

    keyboard = [
        # Botões de navegação de mês
        [
            InlineKeyboardButton("⬅️ Mês Anterior", callback_data="accounts_nav:prev_month"),
            InlineKeyboardButton("Próximo Mês ➡️", callback_data="accounts_nav:next_month")
        ],
        [InlineKeyboardButton("➕ Adicionar Conta/Despesa", callback_data="accounts_action:add_account")],
        [InlineKeyboardButton("➕ Adicionar Entrada (Salário, Renda)", callback_data="accounts_action:add_income")],
        [InlineKeyboardButton("✅ Marcar Conta como Paga", callback_data="accounts_action:mark_paid")],
        [InlineKeyboardButton("📊 Ver Contas e Saldo", callback_data="accounts_action:view_accounts")],
        [InlineKeyboardButton("💸 Ver Entradas", callback_data="accounts_action:view_incomes")],
        [InlineKeyboardButton("🗑️ Deletar Conta", callback_data="accounts_action:delete_account")],
        [InlineKeyboardButton("🗑️ Deletar Entrada", callback_data="accounts_action:delete_income")],
        [InlineKeyboardButton("↩️ Voltar ao Menu Principal do Bot", callback_data="accounts_action:main_menu_bot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, message_text, reply_markup)
    
    logger.info(f"Menu de contas exibido para {user_id} para {month_name}/{current_year}.")
    return VIEW_ACCOUNTS_MENU

async def handle_accounts_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com a seleção de opções no menu principal de contas, incluindo navegação de mês."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    action_type = data[0] # 'accounts_action' ou 'accounts_nav'
    action_value = data[1]

    if action_type == "accounts_action":
        if action_value == "add_account":
            return await add_account_start(update, context)
        elif action_value == "add_income":
            return await add_income_start(update, context)
        elif action_value == "mark_paid":
            return await mark_account_paid_start(update, context)
        elif action_value == "view_accounts":
            # Passa o mês e ano atuais para a função de visualização
            context.user_data['view_month'] = context.user_data['current_accounts_month']
            context.user_data['view_year'] = context.user_data['current_accounts_year']
            return await view_detailed_accounts(update, context)
        elif action_value == "view_incomes":
            # Passa o mês e ano atuais para a função de visualização
            context.user_data['view_month'] = context.user_data['current_accounts_month']
            context.user_data['view_year'] = context.user_data['current_accounts_year']
            return await view_detailed_incomes(update, context)
        elif action_value == "delete_account":
            # Passa o mês e ano atuais para a função de deleção
            context.user_data['delete_month'] = context.user_data['current_accounts_month']
            context.user_data['delete_year'] = context.user_data['current_accounts_year']
            return await delete_account_start(update, context)
        elif action_value == "delete_income":
            # Passa o mês e ano atuais para a função de deleção
            context.user_data['delete_month'] = context.user_data['current_accounts_month']
            context.user_data['delete_year'] = context.user_data['current_accounts_year']
            return await delete_income_start(update, context)
        elif action_value == "main_menu_bot":
            await send_or_edit_message(update, "Retornando ao menu principal do bot... 👋")
            context.user_data.pop('current_accounts_month', None) # Limpa dados de navegação de mês
            context.user_data.pop('current_accounts_year', None)
            context.user_data.clear() # Limpa outros dados da conversa
            return ConversationHandler.END
        elif action_value == "back_to_accounts_menu": # Botão de voltar de outras telas
            return await accounts_menu(update, context)
    
    elif action_type == "accounts_nav":
        current_month = context.user_data.get('current_accounts_month', datetime.date.today().month)
        current_year = context.user_data.get('current_accounts_year', datetime.date.today().year)

        if action_value == "prev_month":
            if current_month == 1:
                current_month = 12
                current_year -= 1
            else:
                current_month -= 1
        elif action_value == "next_month":
            if current_month == 12:
                current_month = 1
                current_year += 1
            else:
                current_month += 1
        
        context.user_data['current_accounts_month'] = current_month
        context.user_data['current_accounts_year'] = current_year
        
        # Chama o menu novamente com o novo mês/ano
        return await accounts_menu(update, context)

    logger.warning(f"Ação de menu de contas não tratada: {query.data} por {update.effective_user.id}")
    return await accounts_menu(update, context) # Em caso de ação desconhecida, retorna ao menu

# --- Funções de Calendário ---
def create_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    """Cria um InlineKeyboardMarkup para um calendário."""
    keyboard = []
    # Cabeçalho: Mês e Ano
    keyboard.append([
        InlineKeyboardButton("«", callback_data=f"cal:nav:{year-1}:{month}"), # Ano anterior
        InlineKeyboardButton("<", callback_data=f"cal:nav:{year}:{month-1 if month > 1 else 12}:{year-1 if month == 1 else year}"), # Mês anterior
        InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="cal:ignore"), # Mês e ano (não clicável)
        InlineKeyboardButton(">", callback_data=f"cal:nav:{year}:{month+1 if month < 12 else 1}:{year+1 if month == 12 else year}"), # Próximo mês
        InlineKeyboardButton("»", callback_data=f"cal:nav:{year+1}:{month}") # Próximo ano
    ])

    # Dias da semana
    week_days = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    keyboard.append([InlineKeyboardButton(day, callback_data="cal:ignore") for day in week_days])

    # Dias do mês
    cal = calendar.Calendar(firstweekday=6) # 6 = domingo como primeiro dia da semana
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal:ignore")) # Dias vazios
            else:
                row.append(InlineKeyboardButton(str(day), callback_data=f"cal:date:{year}:{month}:{day}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cal:cancel")])
    return InlineKeyboardMarkup(keyboard)

async def send_calendar_message(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    """Envia ou edita a mensagem do calendário."""
    current_date = datetime.datetime.now()
    year = context.user_data.get(f'{prefix}_cal_year', current_date.year)
    month = context.user_data.get(f'{prefix}_cal_month', current_date.month)

    # Armazenar o prefixo para saber qual fluxo de data estamos
    context.user_data['calendar_flow_prefix'] = prefix

    keyboard = create_calendar_keyboard(year, month)
    text = f"🗓️ Selecione a data para a {escape_markdown(context.user_data[f'{prefix}_type'], version=2)}:"

    # Se a mensagem original foi enviada pelo bot, tenta editá-la. Senão, envia uma nova.
    if update.callback_query and update.callback_query.message:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    
    return context.user_data[f'{prefix}_next_state_calendar'] # Retorna o estado de espera de clique no calendário

async def handle_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com os callbacks dos botões do calendário."""
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split(':')
    action = data_parts[1]
    
    # Recupera o prefixo para saber se estamos no fluxo de conta ou entrada
    prefix = context.user_data.get('calendar_flow_prefix')
    if not prefix: # Caso de erro, volta pro menu
        await send_or_edit_message(update, "Houve um erro no fluxo do calendário. Por favor, tente novamente do menu principal.")
        context.user_data.clear()
        return await accounts_menu(update, context)

    if action == "date":
        year = int(data_parts[2])
        month = int(data_parts[3])
        day = int(data_parts[4])
        selected_date = datetime.date(year, month, day)

        context.user_data[f'{prefix}_selected_date'] = selected_date.strftime('%Y-%m-%d')
        
        # Agora, a partir daqui, o fluxo continua para a próxima etapa, que depende do prefixo
        if prefix == 'account':
            return await get_account_recurrence_prompt(update, context)
        elif prefix == 'income':
            return await process_income_data(update, context)

    elif action == "nav":
        # Extrair os componentes de data da callback_data
        year = int(data_parts[2])
        month = int(data_parts[3])

        # Armazenar para persistência na navegação
        context.user_data[f'{prefix}_cal_year'] = year
        context.user_data[f'{prefix}_cal_month'] = month

        keyboard = create_calendar_keyboard(year, month)
        text = f"🗓️ Selecione a data para a {escape_markdown(context.user_data[f'{prefix}_type'], version=2)}:"
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
        return context.user_data[f'{prefix}_next_state_calendar'] # Permanece no estado de espera de clique no calendário

    elif action == "cancel":
        return await cancel_accounts_flow(update, context) # Retorna ao menu principal de contas

    return context.user_data[f'{prefix}_next_state_calendar'] # Permanece no estado atual se for um 'ignore'

# --- Adicionar Conta/Despesa ---
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para adicionar uma nova conta."""
    user_id = update.effective_user.id
    await send_or_edit_message(update, "Qual o nome da conta/despesa (ex: Aluguel, Supermercado)?")
    logger.info(f"Iniciando add_account_flow para {user_id}.")
    return ADD_ACCOUNT_NAME

async def get_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da conta."""
    context.user_data['account_name'] = update.message.text.strip()
    await send_or_edit_message(update, "Qual o valor dessa conta (ex: 1500.50)?")
    return ADD_ACCOUNT_AMOUNT

async def get_account_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o valor da conta."""
    try:
        amount = float(update.message.text.strip().replace(',', '.'))
        if amount <= 0:
            await send_or_edit_message(update, "O valor deve ser um número positivo. Tente novamente.")
            return ADD_ACCOUNT_AMOUNT
        context.user_data['account_amount'] = amount
        
        # Define os dados para o fluxo do calendário
        context.user_data['account_type'] = "conta/despesa"
        context.user_data['account_next_state_calendar'] = GETTING_ACCOUNT_DATE_FROM_CALENDAR
        
        # Chama a função para enviar o calendário
        return await send_calendar_message(update, context, 'account')

    except ValueError:
        await send_or_edit_message(update, "Valor inválido. Por favor, insira um número (ex: 1500.50).")
        return ADD_ACCOUNT_AMOUNT

async def get_account_recurrence_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Após a data ser selecionada, pergunta sobre a recorrência."""
    keyboard = [
        [InlineKeyboardButton("Sem Recorrência", callback_data="none")],
        [InlineKeyboardButton("Mensal (Indefinido)", callback_data="indefinite")],
        [InlineKeyboardButton("Parcelado (Nº de Parcelas)", callback_data="fixed_parcel")],
        [InlineKeyboardButton("Cancelar", callback_data="cal:cancel")] # Usando o cancel do calendário
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, "Esta conta é recorrente?", reply_markup)
    return ADD_ACCOUNT_RECURRENCE

async def get_account_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o tipo de recorrência da conta."""
    query = update.callback_query
    await query.answer()
    recurrence = query.data

    if recurrence == "cal:cancel": # Botão de cancelar do calendário
        return await cancel_accounts_flow(update, context)

    context.user_data['account_recurrence'] = recurrence

    if recurrence == 'fixed_parcel':
        await send_or_edit_message(update, "Quantas parcelas (número inteiro)?")
        return ADD_ACCOUNT_PARCEL_COUNT
    else: # 'none' ou 'indefinite'
        name = context.user_data['account_name']
        amount = context.user_data['account_amount']
        due_date = context.user_data['account_selected_date'] # Data do calendário
        user_id = query.from_user.id

        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence):
            await send_or_edit_message(update, f"🎉 Conta '{name}' (R$ {amount:.2f}) adicionada com sucesso como {recurrence}!")
            logger.info(f"Conta '{name}' adicionada por {user_id}.")
        else:
            await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a conta. Talvez ela já exista ou houve um erro no banco de dados.")
            logger.warning(f"Falha ao adicionar conta '{name}' para {user_id}.")
        
        context.user_data.clear()
        return await accounts_menu(update, context) # Retorna para o menu de contas

async def get_account_parcel_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o número de parcelas para contas fixas."""
    try:
        parcel_count = int(update.message.text.strip())
        if parcel_count <= 0:
            await send_or_edit_message(update, "O número de parcelas deve ser um número inteiro positivo. Tente novamente.")
            return ADD_ACCOUNT_PARCEL_COUNT

        context.user_data['account_parcel_count'] = parcel_count

        name = context.user_data['account_name']
        amount = context.user_data['account_amount']
        due_date = context.user_data['account_selected_date'] # Data do calendário
        recurrence = context.user_data['account_recurrence']
        user_id = update.effective_user.id

        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence, parcel_count, current_parcel=1):
            await send_or_edit_message(update, f"🎉 Conta '{name}' (R$ {amount:.2f}) adicionada com sucesso como parcelada em {parcel_count}x!")
            logger.info(f"Conta '{name}' adicionada por {user_id} como parcelada.")
        else:
            await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a conta. Talvez ela já exista ou houve um erro no banco de dados.")
            logger.warning(f"Falha ao adicionar conta parcelada '{name}' para {user_id}.")
        
        context.user_data.clear()
        return await accounts_menu(update, context) # Retorna para o menu de contas
    except ValueError:
        await send_or_edit_message(update, "Número de parcelas inválido. Por favor, insira um número inteiro.")
        return ADD_ACCOUNT_PARCEL_COUNT

# --- Marcar Conta como Paga ---
async def mark_account_paid_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para marcar uma conta como paga, listando-as com botões."""
    user_id = update.effective_user.id
    current_month = datetime.date.today().month
    current_year = datetime.date.today().year
    accounts = accounts_db.get_monthly_accounts(user_id, current_month, current_year)

    # Filtra apenas as contas PENDENTES para marcar como paga
    pending_accounts = [acc for acc in accounts if not acc[4]] # acc[4] é is_paid

    if not pending_accounts:
        await send_or_edit_message(update, "Você não tem contas *pendentes* para marcar como pagas neste mês. ✅")
        return await accounts_menu(update, context) # Retorna ao menu de contas

    message_text = "Selecione a conta para marcar como paga:\n\n"
    keyboard = []

    for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in pending_accounts:
        try:
            due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m') # Apenas dia/mês
        except ValueError:
            due_date_display = due_date
        
        recurrence_info = ""
        if recurrence == 'fixed_parcel' and parcel_count:
            recurrence_info = f" ({current_parcel}/{parcel_count}x)"
        elif recurrence == 'indefinite':
            recurrence_info = " (Recorrente)"

        # O botão agora tem o ID da conta no callback_data e um rótulo amigável
        button_text = f"{name} - R$ {amount:.2f} ({due_date_display}){recurrence_info}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"mark_account:{acc_id}")])

    keyboard.append([InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, message_text, reply_markup)

    logger.info(f"Exibindo contas para marcar como pagas para {user_id}.")
    return GET_ACCOUNT_ID_TO_MARK # Novo estado para aguardar o clique no botão da conta

async def mark_account_paid_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e marca a conta como paga APÓS O CLIQUE NO BOTÃO."""
    query = update.callback_query
    await query.answer() # Responda ao callback imediatamente

    # Verificar se é um callback do botão "Voltar"
    if query.data == "accounts_action:back_to_accounts_menu":
        return await accounts_menu(update, context)

    # Se for um clique em um botão de conta (ex: "mark_account:123")
    if query.data.startswith("mark_account:"):
        user_id = query.from_user.id
        account_id = int(query.data.split(':')[1]) # Extrai o ID da conta do callback_data

        if accounts_db.mark_account_paid(account_id, user_id):
            await send_or_edit_message(update, f"🎉 Conta marcada como paga com sucesso! ID: `{account_id}`")
            logger.info(f"Conta ID {account_id} marcada como paga por {user_id}.")
        else:
            await send_or_edit_message(update, f"❌ Não foi possível marcar a conta como paga. Verifique se ela já está paga ou se há um erro. ID: `{account_id}`")
            logger.warning(f"Falha ao marcar conta ID {account_id} como paga para {user_id}.")
        
        context.user_data.clear()
        return await accounts_menu(update, context) # Retorna para o menu de contas após a operação
    
    # Se chegou aqui, é um callback inesperado, volta para o menu
    return await accounts_menu(update, context)

# --- Deletar Conta ---
async def delete_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para deletar uma conta, listando-as com botões."""
    user_id = update.effective_user.id
    
    # Usa o mês e ano do user_data para a visualização/deleção
    today = datetime.date.today()
    month = context.user_data.get('delete_month', context.user_data.get('current_accounts_month', today.month))
    year = context.user_data.get('delete_year', context.user_data.get('current_accounts_year', today.year))
    
    # Salva o mês e ano para a navegação neste fluxo de deleção
    context.user_data['delete_month'] = month
    context.user_data['delete_year'] = year

    accounts = accounts_db.get_monthly_accounts(user_id, month, year) # Filtra por mês e ano

    month_name = datetime.date(year, month, 1).strftime('%B').capitalize()

    message_text = f"🗑️ *Contas para deletar ({month_name}/{year}):*\n\n"
    if not accounts:
        message_text += "Você não tem contas registradas para este mês."
    else:
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in accounts:
            status = "✅ PAGA" if is_paid else "❌ PENDENTE"
            try:
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m') # Apenas dia/mês
            except ValueError:
                due_date_display = due_date
            
            recurrence_info = ""
            if recurrence == 'fixed_parcel' and parcel_count:
                recurrence_info = f" ({current_parcel}/{parcel_count}x)"
            elif recurrence == 'indefinite':
                recurrence_info = " (Recorrente)"

            # O botão agora tem o ID da conta no callback_data
            button_text = f"{name} - R$ {amount:.2f} ({due_date_display}) | {status}{recurrence_info}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_account:{acc_id}")])
    
    keyboard = [
        # Botões de navegação de mês para a deleção de contas
        [
            InlineKeyboardButton("⬅️ Mês Anterior", callback_data="delete_accounts_nav:prev_month"),
            InlineKeyboardButton("Próximo Mês ➡️", callback_data="delete_accounts_nav:next_month")
        ],
        [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]
    ]
    # Adiciona os botões de contas se houver alguma
    if accounts:
        accounts_buttons = []
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in accounts:
            status = "✅ PAGA" if is_paid else "❌ PENDENTE"
            try:
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m')
            except ValueError:
                due_date_display = due_date
            recurrence_info = ""
            if recurrence == 'fixed_parcel' and parcel_count:
                recurrence_info = f" ({current_parcel}/{parcel_count}x)"
            elif recurrence == 'indefinite':
                recurrence_info = " (Recorrente)"
            button_text = f"{name} - R$ {amount:.2f} ({due_date_display}) | {status}{recurrence_info}"
            accounts_buttons.append([InlineKeyboardButton(button_text, callback_data=f"delete_account:{acc_id}")])
        keyboard = accounts_buttons + keyboard # Coloca os botões das contas acima da navegação
        
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, message_text, reply_markup)
    
    logger.info(f"Exibindo contas para deletar para {user_id} para {month_name}/{year}.")
    return GET_ACCOUNT_ID_TO_DELETE # Novo estado para aguardar o clique no botão da conta

async def delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e deleta a conta APÓS O CLIQUE NO BOTÃO."""
    query = update.callback_query
    await query.answer() # Responda ao callback imediatamente

    # Verificar se é um callback do botão "Voltar"
    if query.data == "accounts_action:back_to_accounts_menu":
        return await accounts_menu(update, context)

    # Se for um clique em um botão de conta (ex: "delete_account:123")
    if query.data.startswith("delete_account:"):
        user_id = query.from_user.id
        account_id = int(query.data.split(':')[1]) # Extrai o ID da conta do callback_data

        if accounts_db.delete_monthly_account(account_id, user_id):
            await send_or_edit_message(update, f"🗑️ Conta deletada com sucesso! ID: `{account_id}`")
            logger.info(f"Conta ID {account_id} deletada por {user_id}.")
        else:
            await send_or_edit_message(update, f"❌ Não foi possível deletar a conta. Verifique se o ID está correto. ID: `{account_id}`")
            logger.warning(f"Falha ao deletar conta ID {account_id} para {user_id}.")
        
        context.user_data.pop('delete_month', None) # Limpa dados de navegação de deleção
        context.user_data.pop('delete_year', None)
        return await accounts_menu(update, context) # Retorna para o menu de contas após a operação
    
    # Se chegou aqui, é um callback inesperado, volta para o menu
    return await accounts_menu(update, context)

# --- Adicionar Entrada (Rendimento) ---
async def add_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para adicionar uma nova entrada de rendimento."""
    user_id = update.effective_user.id
    await send_or_edit_message(update, "Qual a descrição da entrada (ex: Salário, Freelance)?")
    logger.info(f"Iniciando add_income_flow para {user_id}.")
    return ADD_INCOME_DESCRIPTION

async def get_income_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a descrição da entrada."""
    context.user_data['income_description'] = update.message.text.strip()
    await send_or_edit_message(update, "Qual o valor da entrada (ex: 3000.00)?")
    return ADD_INCOME_AMOUNT

async def get_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o valor da entrada."""
    try:
        amount = float(update.message.text.strip().replace(',', '.'))
        if amount <= 0:
            await send_or_edit_message(update, "O valor deve ser um número positivo. Tente novamente.")
            return ADD_INCOME_AMOUNT
        context.user_data['income_amount'] = amount
        
        # Define os dados para o fluxo do calendário
        context.user_data['income_type'] = "entrada"
        context.user_data['income_next_state_calendar'] = GETTING_INCOME_DATE_FROM_CALENDAR
        
        # Chama a função para enviar o calendário
        return await send_calendar_message(update, context, 'income')

    except ValueError:
        await send_or_edit_message(update, "Valor inválido. Por favor, insira um número (ex: 3000.00).")
        return ADD_INCOME_AMOUNT

async def process_income_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa os dados da entrada após a data ser selecionada."""
    description = context.user_data['income_description']
    amount = context.user_data['income_amount']
    income_date_db = context.user_data['income_selected_date'] # Data do calendário
    user_id = update.effective_user.id

    if accounts_db.add_financial_income(user_id, description, amount, income_date_db):
        await send_or_edit_message(update, f"🎉 Entrada '{description}' (R$ {amount:.2f}) adicionada com sucesso!")
        logger.info(f"Entrada '{description}' adicionada por {user_id}.")
    else:
        await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a entrada. Talvez ela já exista ou houve um erro no banco de dados.")
        logger.warning(f"Falha ao adicionar entrada '{description}' para {user_id}.")
    
    context.user_data.clear()
    return await accounts_menu(update, context) # Retorna para o menu de contas

import datetime
import calendar
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

import accounts_db

logger = logging.getLogger(__name__)

# --- Estados para o ConversationHandler de Contas ---
ADD_ACCOUNT_NAME = 100
ADD_ACCOUNT_AMOUNT = 101
ADD_ACCOUNT_DUE_DATE = 102
ADD_ACCOUNT_RECURRENCE = 103
ADD_ACCOUNT_PARCEL_COUNT = 104
GETTING_ACCOUNT_DATE_FROM_CALENDAR = 105

GET_ACCOUNT_ID_TO_MARK = 110

GET_ACCOUNT_ID_TO_DELETE = 120

ADD_INCOME_DESCRIPTION = 130
ADD_INCOME_AMOUNT = 131
ADD_INCOME_DATE = 132
GETTING_INCOME_DATE_FROM_CALENDAR = 133

GET_INCOME_ID_TO_DELETE = 140

VIEW_ACCOUNTS_MENU = 150
NAVIGATING_MONTHS = 160

# --- Função Auxiliar para Enviar/Editar Mensagens ---
async def send_or_edit_message(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = ParseMode.MARKDOWN_V2):
    escaped_text = escape_markdown(text, version=2)
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(escaped_text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Erro ao editar mensagem: {e}. Enviando nova mensagem.")
            await update.callback_query.message.reply_text(escaped_text, reply_markup=reply_markup, parse_mode=parse_mode)
    elif update.message:
        await update.message.reply_text(escaped_text, reply_markup=reply_markup, parse_mode=parse_mode)

# --- Funções de Handler para Contas Financeiras ---
async def accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    today = datetime.date.today()
    current_month = context.user_data.get('current_accounts_month', today.month)
    current_year = context.user_data.get('current_accounts_year', today.year)

    context.user_data['current_accounts_month'] = current_month
    context.user_data['current_accounts_year'] = current_year

    summary = accounts_db.get_financial_summary(user_id, current_month, current_year)
    month_name = datetime.date(current_year, current_month, 1).strftime('%B').capitalize()

    message_text = (
        f"💰 *Seu Resumo Financeiro ({month_name}/{current_year}):*\n\n"
        f"  *Saldo Inicial do Mês*: `R$ {summary['previous_month_balance']:.2f}`\n"
        f"  *Entradas no Mês*: `R$ {summary['total_incomes_this_month']:.2f}`\n"
        f"  *Contas a Pagar no Mês*: `R$ {summary['total_accounts_due_this_month']:.2f}`\n"
        f"  *Contas Pagas no Mês*: `R$ {summary['paid_accounts_this_month']:.2f}`\n"
        f"  *Contas Pendentes no Mês*: `R$ {summary['unpaid_accounts_this_month']:.2f}`\n"
        f"  *Saldo Líquido do Mês*: `R$ {summary['current_month_net_change']:.2f}`\n"
        f"  *Saldo Final (Acumulado)*: `R$ {summary['final_balance_this_month']:.2f}`\n\n"
        "Selecione uma opção abaixo ou navegue pelos meses:"
    )

    keyboard = [
        [
            InlineKeyboardButton("⬅️ Mês Anterior", callback_data="accounts_nav:prev_month"),
            InlineKeyboardButton("Próximo Mês ➡️", callback_data="accounts_nav:next_month")
        ],
        [InlineKeyboardButton("➕ Adicionar Conta/Despesa", callback_data="accounts_action:add_account")],
        [InlineKeyboardButton("➕ Adicionar Entrada (Salário, Renda)", callback_data="accounts_action:add_income")],
        [InlineKeyboardButton("✅ Marcar Conta como Paga", callback_data="accounts_action:mark_paid")],
        [InlineKeyboardButton("📊 Ver Contas e Saldo", callback_data="accounts_action:view_accounts")],
        [InlineKeyboardButton("💸 Ver Entradas", callback_data="accounts_action:view_incomes")],
        [InlineKeyboardButton("🗑️ Deletar Conta", callback_data="accounts_action:delete_account")],
        [InlineKeyboardButton("🗑️ Deletar Entrada", callback_data="accounts_action:delete_income")],
        [InlineKeyboardButton("↩️ Voltar ao Menu Principal do Bot", callback_data="accounts_action:main_menu_bot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, message_text, reply_markup)
    logger.info(f"Menu de contas exibido para {user_id} para {month_name}/{current_year}.")
    return VIEW_ACCOUNTS_MENU

async def handle_accounts_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    action_type = data[0]
    action_value = data[1]

    if action_type == "accounts_action":
        if action_value == "add_account":
            return await add_account_start(update, context)
        elif action_value == "add_income":
            return await add_income_start(update, context)
        elif action_value == "mark_paid":
            return await mark_account_paid_start(update, context)
        elif action_value == "view_accounts":
            context.user_data['view_month'] = context.user_data['current_accounts_month']
            context.user_data['view_year'] = context.user_data['current_accounts_year']
            return await view_detailed_accounts(update, context)
        elif action_value == "view_incomes":
            context.user_data['view_month'] = context.user_data['current_accounts_month']
            context.user_data['view_year'] = context.user_data['current_accounts_year']
            return await view_detailed_incomes(update, context)
        elif action_value == "delete_account":
            context.user_data['delete_month'] = context.user_data['current_accounts_month']
            context.user_data['delete_year'] = context.user_data['current_accounts_year']
            return await delete_account_start(update, context)
        elif action_value == "delete_income":
            context.user_data['delete_month'] = context.user_data['current_accounts_month']
            context.user_data['delete_year'] = context.user_data['current_accounts_year']
            return await delete_income_start(update, context)
        elif action_value == "main_menu_bot":
            await send_or_edit_message(update, "Retornando ao menu principal do bot... 👋")
            context.user_data.pop('current_accounts_month', None)
            context.user_data.pop('current_accounts_year', None)
            context.user_data.pop('view_month', None)
            context.user_data.pop('view_year', None)
            context.user_data.pop('delete_month', None)
            context.user_data.pop('delete_year', None)
            return ConversationHandler.END
        elif action_value == "back_to_accounts_menu":
            return await accounts_menu(update, context)
    
    elif action_type == "accounts_nav":
        current_month = context.user_data.get('current_accounts_month', datetime.date.today().month)
        current_year = context.user_data.get('current_accounts_year', datetime.date.today().year)

        if action_value == "prev_month":
            current_month, current_year = (12, current_year - 1) if current_month == 1 else (current_month - 1, current_year)
        elif action_value == "next_month":
            current_month, current_year = (1, current_year + 1) if current_month == 12 else (current_month + 1, current_year)
        
        context.user_data['current_accounts_month'] = current_month
        context.user_data['current_accounts_year'] = current_year
        return await accounts_menu(update, context)

    logger.warning(f"Ação de menu de contas não tratada: {query.data} por {update.effective_user.id}")
    return await accounts_menu(update, context)

# --- Funções de Calendário ---
def create_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    keyboard = []
    keyboard.append([
        InlineKeyboardButton("«", callback_data=f"cal:nav:{year-1}:{month}"),
        InlineKeyboardButton("<", callback_data=f"cal:nav:{year}:{month-1 if month > 1 else 12}"),
        InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="cal:ignore"),
        InlineKeyboardButton(">", callback_data=f"cal:nav:{year}:{month+1 if month < 12 else 1}"),
        InlineKeyboardButton("»", callback_data=f"cal:nav:{year+1}:{month}")
    ])
    week_days = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    keyboard.append([InlineKeyboardButton(day, callback_data="cal:ignore") for day in week_days])

    cal = calendar.Calendar(firstweekday=6)
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            row.append(InlineKeyboardButton(" " if day == 0 else str(day), callback_data=f"cal:date:{year}:{month}:{day}" if day != 0 else "cal:ignore"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cal:cancel")])
    return InlineKeyboardMarkup(keyboard)

async def send_calendar_message(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> int:
    current_date = datetime.datetime.now()
    year = context.user_data.get(f'{prefix}_cal_year', current_date.year)
    month = context.user_data.get(f'{prefix}_cal_month', current_date.month)

    context.user_data['calendar_flow_prefix'] = prefix

    keyboard = create_calendar_keyboard(year, month)
    text = f"🗓️ Selecione a data para a {escape_markdown(context.user_data[f'{prefix}_type'], version=2)}:"

    if update.callback_query and update.callback_query.message:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    
    return context.user_data[f'{prefix}_next_state_calendar']

async def handle_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split(':')
    action = data_parts[1]
    
    prefix = context.user_data.get('calendar_flow_prefix')
    if not prefix:
        await send_or_edit_message(update, "Houve um erro no fluxo do calendário. Por favor, tente novamente do menu principal.")
        context.user_data.clear()
        return await accounts_menu(update, context)

    if action == "date":
        year, month, day = int(data_parts[2]), int(data_parts[3]), int(data_parts[4])
        selected_date = datetime.date(year, month, day)
        context.user_data[f'{prefix}_selected_date'] = selected_date.strftime('%Y-%m-%d')
        
        if prefix == 'account':
            return await get_account_recurrence_prompt(update, context)
        elif prefix == 'income':
            return await process_income_data(update, context)

    elif action == "nav":
        year, month = int(data_parts[2]), int(data_parts[3])
        context.user_data[f'{prefix}_cal_year'] = year
        context.user_data[f'{prefix}_cal_month'] = month

        keyboard = create_calendar_keyboard(year, month)
        text = f"🗓️ Selecione a data para a {escape_markdown(context.user_data[f'{prefix}_type'], version=2)}:"
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
        return context.user_data[f'{prefix}_next_state_calendar']

    elif action == "cancel":
        return await cancel_accounts_flow(update, context)

    return context.user_data[f'{prefix}_next_state_calendar']

# --- Adicionar Conta/Despesa ---
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    await send_or_edit_message(update, "Qual o nome da conta/despesa (ex: Aluguel, Supermercado)?")
    logger.info(f"Iniciando add_account_flow para {user_id}.")
    return ADD_ACCOUNT_NAME

async def get_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['account_name'] = update.message.text.strip()
    await send_or_edit_message(update, "Qual o valor dessa conta (ex: 1500.50)?")
    return ADD_ACCOUNT_AMOUNT

async def get_account_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip().replace(',', '.'))
        if amount <= 0:
            await send_or_edit_message(update, "O valor deve ser um número positivo. Tente novamente.")
            return ADD_ACCOUNT_AMOUNT
        context.user_data['account_amount'] = amount
        
        context.user_data['account_type'] = "conta/despesa"
        context.user_data['account_next_state_calendar'] = GETTING_ACCOUNT_DATE_FROM_CALENDAR
        
        return await send_calendar_message(update, context, 'account')
    except ValueError:
        await send_or_edit_message(update, "Valor inválido. Por favor, insira um número (ex: 1500.50).")
        return ADD_ACCOUNT_AMOUNT

async def get_account_recurrence_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("Sem Recorrência", callback_data="none")],
        [InlineKeyboardButton("Mensal (Indefinido)", callback_data="indefinite")],
        [InlineKeyboardButton("Parcelado (Nº de Parcelas)", callback_data="fixed_parcel")],
        [InlineKeyboardButton("Cancelar", callback_data="cal:cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, "Esta conta é recorrente?", reply_markup)
    return ADD_ACCOUNT_RECURRENCE

async def get_account_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    recurrence = query.data

    if recurrence == "cal:cancel":
        return await cancel_accounts_flow(update, context)

    context.user_data['account_recurrence'] = recurrence

    if recurrence == 'fixed_parcel':
        await send_or_edit_message(update, "Quantas parcelas (número inteiro)?")
        return ADD_ACCOUNT_PARCEL_COUNT
    else:
        name = context.user_data['account_name']
        amount = context.user_data['account_amount']
        due_date = context.user_data['account_selected_date']
        user_id = query.from_user.id

        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence):
            await send_or_edit_message(update, f"🎉 Conta '{name}' (R$ {amount:.2f}) adicionada com sucesso como *{recurrence}*!")
            logger.info(f"Conta '{name}' adicionada por {user_id}.")
        else:
            await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a conta. Talvez ela já exista ou houve um erro no banco de dados.")
            logger.warning(f"Falha ao adicionar conta '{name}' para {user_id}.")
        
        context.user_data.pop('account_name', None)
        context.user_data.pop('account_amount', None)
        context.user_data.pop('account_selected_date', None)
        context.user_data.pop('account_recurrence', None)
        context.user_data.pop('account_type', None)
        context.user_data.pop('account_next_state_calendar', None)
        context.user_data.pop('calendar_flow_prefix', None)
        context.user_data.pop('account_cal_year', None)
        context.user_data.pop('account_cal_month', None)
        
        return await accounts_menu(update, context)

async def get_account_parcel_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        parcel_count = int(update.message.text.strip())
        if parcel_count <= 0:
            await send_or_edit_message(update, "O número de parcelas deve ser um número inteiro positivo. Tente novamente.")
            return ADD_ACCOUNT_PARCEL_COUNT

        context.user_data['account_parcel_count'] = parcel_count

        name = context.user_data['account_name']
        amount = context.user_data['account_amount']
        due_date = context.user_data['account_selected_date']
        recurrence = context.user_data['account_recurrence']
        user_id = update.effective_user.id

        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence, parcel_count, current_parcel=1):
            await send_or_edit_message(update, f"🎉 Conta '{name}' (R$ {amount:.2f}) adicionada com sucesso como parcelada em *{parcel_count}x*!")
            logger.info(f"Conta '{name}' adicionada por {user_id} como parcelada.")
        else:
            await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a conta. Talvez ela já exista ou houve um erro no banco de dados.")
            logger.warning(f"Falha ao adicionar conta parcelada '{name}' para {user_id}.")
        
        context.user_data.pop('account_name', None)
        context.user_data.pop('account_amount', None)
        context.user_data.pop('account_selected_date', None)
        context.user_data.pop('account_recurrence', None)
        context.user_data.pop('account_parcel_count', None)
        context.user_data.pop('account_type', None)
        context.user_data.pop('account_next_state_calendar', None)
        context.user_data.pop('calendar_flow_prefix', None)
        context.user_data.pop('account_cal_year', None)
        context.user_data.pop('account_cal_month', None)
        
        return await accounts_menu(update, context)
    except ValueError:
        await send_or_edit_message(update, "Número de parcelas inválido. Por favor, insira um número inteiro.")
        return ADD_ACCOUNT_PARCEL_COUNT

# --- Marcar Conta como Paga ---
async def mark_account_paid_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    current_month = context.user_data.get('current_accounts_month', datetime.date.today().month)
    current_year = context.user_data.get('current_accounts_year', datetime.date.today().year)
    
    accounts = accounts_db.get_monthly_accounts(user_id, current_month, current_year)
    pending_accounts = [acc for acc in accounts if not acc[4]]

    message_text = f"✅ *Marcar contas como pagas ({datetime.date(current_year, current_month, 1).strftime('%B/%Y')}):*\n\n"
    keyboard = []

    if not pending_accounts:
        message_text += "Você não tem contas *pendentes* para marcar como pagas neste mês. 🎉"
    else:
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in pending_accounts:
            try:
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m')
            except (ValueError, TypeError):
                due_date_display = due_date if due_date else "N/A"
            
            recurrence_info = f" ({current_parcel}/{parcel_count}x)" if recurrence == 'fixed_parcel' and parcel_count else (" (Recorrente)" if recurrence == 'indefinite' else "")
            button_text = f"{name} - R$ {amount:.2f} ({due_date_display}){recurrence_info}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"mark_account:{acc_id}")])

    keyboard.append([InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, message_text, reply_markup)
    logger.info(f"Exibindo contas para marcar como pagas para {user_id}.")
    return GET_ACCOUNT_ID_TO_MARK

async def mark_account_paid_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "accounts_action:back_to_accounts_menu":
        return await accounts_menu(update, context)

    if query.data.startswith("mark_account:"):
        user_id = query.from_user.id
        account_id = int(query.data.split(':')[1])

        if accounts_db.mark_account_paid(account_id, user_id):
            await send_or_edit_message(update, f"🎉 Conta marcada como paga com sucesso! ID: `{account_id}`")
            logger.info(f"Conta ID {account_id} marcada como paga por {user_id}.")
        else:
            await send_or_edit_message(update, f"❌ Não foi possível marcar a conta como paga. Verifique se ela já está paga ou se há um erro. ID: `{account_id}`")
            logger.warning(f"Falha ao marcar conta ID {account_id} como paga para {user_id}.")
        
        return await mark_account_paid_start(update, context)
        
    return await accounts_menu(update, context)

# --- Funções Auxiliares de Navegação para Visualização e Deleção ---
def build_month_navigation_keyboard(current_year: int, current_month: int, nav_prefix: str) -> list[list[InlineKeyboardButton]]:
    prev_month_dt = datetime.date(current_year, current_month, 1) - datetime.timedelta(days=1)
    prev_month_str = prev_month_dt.strftime('%Y-%m')

    next_month_dt = datetime.date(current_year, current_month, 1) + datetime.timedelta(days=32)
    next_month_str = next_month_dt.strftime('%Y-%m')

    return [
        [
            InlineKeyboardButton("⬅️ Mês Anterior", callback_data=f"{nav_prefix}:{prev_month_str}"),
            InlineKeyboardButton("Próximo Mês ➡️", callback_data=f"{nav_prefix}:{next_month_str}")
        ]
    ]

async def handle_view_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split(':')
    nav_prefix = data_parts[0]
    selected_month_str = data_parts[1]

    year, month = map(int, selected_month_str.split('-'))
    
    if nav_prefix.startswith("view_accounts"):
        context.user_data['view_month'] = month
        context.user_data['view_year'] = year
        return await view_detailed_accounts(update, context)
    elif nav_prefix.startswith("view_incomes"):
        context.user_data['view_month'] = month
        context.user_data['view_year'] = year
        return await view_detailed_incomes(update, context)
    elif nav_prefix.startswith("delete_accounts"):
        context.user_data['delete_month'] = month
        context.user_data['delete_year'] = year
        return await delete_account_start(update, context)
    elif nav_prefix.startswith("delete_incomes"):
        context.user_data['delete_month'] = month
        context.user_data['delete_year'] = year
        return await delete_income_start(update, context)
    
    logger.warning(f"Navegação de visualização/deleção não tratada: {query.data}")
    return ConversationHandler.NEXT

# --- Deletar Conta ---
async def delete_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    today = datetime.date.today()
    month = context.user_data.get('delete_month', context.user_data.get('current_accounts_month', today.month))
    year = context.user_data.get('delete_year', context.user_data.get('current_accounts_year', today.year))
    
    context.user_data['delete_month'] = month
    context.user_data['delete_year'] = year

    accounts = accounts_db.get_monthly_accounts(user_id, month, year)
    month_name = datetime.date(year, month, 1).strftime('%B').capitalize()

    message_text = f"🗑️ *Contas para deletar ({month_name}/{year}):*\n\n"
    keyboard_buttons = [] 

    if not accounts:
        message_text += "Você não tem contas registradas para este mês."
    else:
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in accounts:
            status = "✅ PAGA" if is_paid else "❌ PENDENTE"
            try:
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m')
            except (ValueError, TypeError):
                due_date_display = due_date if due_date else "N/A"
            
            recurrence_info = f" ({current_parcel}/{parcel_count}x)" if recurrence == 'fixed_parcel' and parcel_count else (" (Recorrente)" if recurrence == 'indefinite' else "")
            button_text = f"{name} - R$ {amount:.2f} ({due_date_display}) | {status}{recurrence_info}"
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"delete_account:{acc_id}")])
    
    month_nav_keyboard = build_month_navigation_keyboard(year, month, "delete_accounts_nav")
    back_button = [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]

    final_keyboard = keyboard_buttons + month_nav_keyboard + [back_button]
    reply_markup = InlineKeyboardMarkup(final_keyboard)

    await send_or_edit_message(update, message_text, reply_markup)
    logger.info(f"Exibindo contas para deletar para {user_id} para {month_name}/{year}.")
    return GET_ACCOUNT_ID_TO_DELETE

async def delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "accounts_action:back_to_accounts_menu":
        return await accounts_menu(update, context)

    if query.data.startswith("delete_account:"):
        user_id = query.from_user.id
        account_id = int(query.data.split(':')[1])

        if accounts_db.delete_monthly_account(account_id, user_id):
            await send_or_edit_message(update, f"🗑️ Conta deletada com sucesso! ID: `{account_id}`")
            logger.info(f"Conta ID {account_id} deletada por {user_id}.")
        else:
            await send_or_edit_message(update, f"❌ Não foi possível deletar a conta. Verifique se o ID está correto. ID: `{account_id}`")
            logger.warning(f"Falha ao deletar conta ID {account_id} para {user_id}.")
        
        return await delete_account_start(update, context)
        
    return await accounts_menu(update, context)

# --- Adicionar Entrada (Rendimento) ---
async def add_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    await send_or_edit_message(update, "Qual a descrição da entrada (ex: Salário, Freelance)?")
    logger.info(f"Iniciando add_income_flow para {user_id}.")
    return ADD_INCOME_DESCRIPTION

async def get_income_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['income_description'] = update.message.text.strip()
    await send_or_edit_message(update, "Qual o valor da entrada (ex: 3000.00)?")
    return ADD_INCOME_AMOUNT

async def get_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip().replace(',', '.'))
        if amount <= 0:
            await send_or_edit_message(update, "O valor deve ser um número positivo. Tente novamente.")
            return ADD_INCOME_AMOUNT
        context.user_data['income_amount'] = amount
        
        context.user_data['income_type'] = "entrada"
        context.user_data['income_next_state_calendar'] = GETTING_INCOME_DATE_FROM_CALENDAR
        
        return await send_calendar_message(update, context, 'income')
    except ValueError:
        await send_or_edit_message(update, "Valor inválido. Por favor, insira um número (ex: 3000.00).")
        return ADD_INCOME_AMOUNT

async def process_income_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = context.user_data['income_description']
    amount = context.user_data['income_amount']
    income_date_db = context.user_data['income_selected_date']
    user_id = update.effective_user.id

    if accounts_db.add_financial_income(user_id, description, amount, income_date_db):
        await send_or_edit_message(update, f"🎉 Entrada '{description}' (R$ {amount:.2f}) adicionada com sucesso!")
        logger.info(f"Entrada '{description}' adicionada por {user_id}.")
    else:
        await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a entrada. Talvez ela já exista ou houve um erro no banco de dados.")
        logger.warning(f"Falha ao adicionar entrada '{description}' para {user_id}.")
    
    context.user_data.pop('income_description', None)
    context.user_data.pop('income_amount', None)
    context.user_data.pop('income_selected_date', None)
    context.user_data.pop('income_type', None)
    context.user_data.pop('income_next_state_calendar', None)
    context.user_data.pop('calendar_flow_prefix', None)
    context.user_data.pop('income_cal_year', None)
    context.user_data.pop('income_cal_month', None)
    
    return await accounts_menu(update, context)

# --- Deletar Entrada ---
async def delete_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    today = datetime.date.today()
    month = context.user_data.get('delete_month', context.user_data.get('current_accounts_month', today.month))
    year = context.user_data.get('delete_year', context.user_data.get('current_accounts_year', today.year))

    context.user_data['delete_month'] = month
    context.user_data['delete_year'] = year

    incomes = accounts_db.get_financial_incomes(user_id, month, year)
    month_name = datetime.date(year, month, 1).strftime('%B').capitalize()

    message_text = f"💸 *Entradas para deletar ({month_name}/{year}):*\n\n"
    income_buttons = []
    if not incomes:
        message_text += "Você não tem entradas registradas para este mês."
    else:
        for inc_id, description, amount, income_date_db in incomes:
            try:
                income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m')
            except (ValueError, TypeError):
                income_date_display = income_date_db if income_date_db else "N/A"
            
            button_text = f"{description} - R$ {amount:.2f} ({income_date_display})"
            income_buttons.append([InlineKeyboardButton(button_text, callback_data=f"delete_income:{inc_id}")])
    
    month_nav_keyboard = build_month_navigation_keyboard(year, month, "delete_incomes_nav")
    back_button = [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]
    
    final_keyboard = income_buttons + month_nav_keyboard + [back_button]
    reply_markup = InlineKeyboardMarkup(final_keyboard)

    await send_or_edit_message(update, message_text, reply_markup)
    logger.info(f"Exibindo entradas para deletar para {user_id} para {month_name}/{year}.")
    return GET_INCOME_ID_TO_DELETE

async def delete_income_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "accounts_action:back_to_accounts_menu":
        return await accounts_menu(update, context)

    if query.data.startswith("delete_income:"):
        user_id = query.from_user.id
        income_id = int(query.data.split(':')[1])

        if accounts_db.delete_financial_income(income_id, user_id):
            await send_or_edit_message(update, f"🗑️ Entrada deletada com sucesso! ID: `{income_id}`")
            logger.info(f"Entrada ID {income_id} deletada por {user_id}.")
        else:
            await send_or_edit_message(update, f"❌ Não foi possível deletar a entrada. Verifique se o ID está correto. ID: `{income_id}`")
            logger.warning(f"Falha ao deletar entrada ID {income_id} para {user_id}.")
    
    # Após deletar, retorna para a tela de deleção de entradas para que o usuário possa deletar mais
    return await delete_income_start(update, context)

# --- Visualizar Contas Detalhadas ---
async def view_detailed_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    today = datetime.date.today()
    month = context.user_data.get('view_month', context.user_data.get('current_accounts_month', today.month))
    year = context.user_data.get('view_year', context.user_data.get('current_accounts_year', today.year))

    accounts = accounts_db.get_detailed_monthly_accounts(user_id, month, year)
    month_name = datetime.date(year, month, 1).strftime('%B').capitalize()

    message_text = f"📊 *Suas Contas/Despesas ({month_name}/{year}):*\n\n"
    if not accounts:
        message_text += "Você não tem contas registradas para este mês."
    else:
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel in accounts:
            status = "✅ PAGA" if is_paid else "❌ PENDENTE"
            try:
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                due_date_display = due_date if due_date else "N/A"
            
            recurrence_info = f" ({current_parcel}/{parcel_count}x)" if recurrence == 'fixed_parcel' and parcel_count else (" (Recorrente)" if recurrence == 'indefinite' else "")

            message_text += f"**ID: {acc_id}** - {name}\n  `R$ {amount:.2f} | Vencimento: {due_date_display}{recurrence_info} | Status: {status}`\n\n"
    
    month_nav_keyboard = build_month_navigation_keyboard(year, month, "view_accounts_nav")
    back_button = [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]
    
    final_keyboard = month_nav_keyboard + [back_button] # Navegação e botão de voltar

    reply_markup = InlineKeyboardMarkup(final_keyboard)

    await send_or_edit_message(update, message_text, reply_markup)
    logger.info(f"Contas detalhadas exibidas para {user_id} para {month_name}/{year}.")
    return VIEW_ACCOUNTS_MENU

# --- Visualizar Entradas Detalhadas ---
async def view_detailed_incomes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    today = datetime.date.today()
    month = context.user_data.get('view_month', context.user_data.get('current_accounts_month', today.month))
    year = context.user_data.get('view_year', context.user_data.get('current_accounts_year', today.year))
    
    incomes = accounts_db.get_detailed_financial_incomes(user_id, month, year)
    month_name = datetime.date(year, month, 1).strftime('%B').capitalize()

    message_text = f"💸 *Suas Entradas/Rendimentos ({month_name}/{year}):*\n\n"
    if not incomes:
        message_text += "Você não tem entradas registradas para este mês."
    else:
        for income_id, description, amount, income_date_db in incomes:
            try:
                income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                income_date_display = income_date_db if income_date_db else "N/A"
            message_text += f"**ID: {income_id}** - {description}\n  `R$ {amount:.2f} | Data: {income_date_display}`\n\n"
    
    month_nav_keyboard = build_month_navigation_keyboard(year, month, "view_incomes_nav")
    back_button = [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]

    final_keyboard = month_nav_keyboard + [back_button] # Navegação e botão de voltar
    reply_markup = InlineKeyboardMarkup(final_keyboard)

    await send_or_edit_message(update, message_text, reply_markup)
    logger.info(f"Entradas detalhadas exibidas para {user_id} para {month_name}/{year}.")
    return VIEW_ACCOUNTS_MENU

# --- Função de Cancelamento ---
async def cancel_accounts_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_or_edit_message(update, "Operação de contas cancelada. ✅")
    
    logger.info(f"Diálogo de contas cancelado por {update.effective_user.id}.")
    # Limpa apenas os dados relevantes ao fluxo de contas para evitar interferência em outras conversas
    keys_to_pop = [
        'account_name', 'account_amount', 'account_selected_date', 'account_recurrence',
        'account_parcel_count', 'account_type', 'account_next_state_calendar',
        'income_description', 'income_amount', 'income_selected_date', 'income_type',
        'income_next_state_calendar', 'calendar_flow_prefix',
        'account_cal_year', 'account_cal_month', 'income_cal_year', 'income_cal_month',
        # Não limpar current_accounts_month/year, view_month/year, delete_month/year aqui,
        # pois eles são usados para persistir a navegação entre chamadas do menu principal.
    ]
    for key in keys_to_pop:
        context.user_data.pop(key, None)
        
    return await accounts_menu(update, context) # Retorna ao menu de contas financeiras


# --- Setup dos Handlers de Contas ---
def setup_accounts_handlers():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(accounts_menu, pattern="^accounts_action:open_menu$")
        ],
        states={
            VIEW_ACCOUNTS_MENU: [
                CallbackQueryHandler(handle_accounts_menu_selection, pattern="^accounts_action:"),
                CallbackQueryHandler(handle_accounts_menu_selection, pattern="^accounts_nav:"),
            ],
            # Adicionar Conta
            ADD_ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_account_name)],
            ADD_ACCOUNT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_account_amount)],
            GETTING_ACCOUNT_DATE_FROM_CALENDAR: [CallbackQueryHandler(handle_calendar_callback, pattern="^cal:")],
            ADD_ACCOUNT_RECURRENCE: [CallbackQueryHandler(get_account_recurrence, pattern="^(none|indefinite|fixed_parcel|cal:cancel)$")],
            ADD_ACCOUNT_PARCEL_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_account_parcel_count)],

            # Marcar Conta como Paga
            GET_ACCOUNT_ID_TO_MARK: [CallbackQueryHandler(mark_account_paid_confirm, pattern="^mark_account:|^accounts_action:back_to_accounts_menu$")],

            # Deletar Conta
            GET_ACCOUNT_ID_TO_DELETE: [
                CallbackQueryHandler(delete_account_confirm, pattern="^delete_account:"),
                CallbackQueryHandler(handle_view_navigation, pattern="^delete_accounts_nav:"), # Para navegação de mês
                CallbackQueryHandler(handle_accounts_menu_selection, pattern="^accounts_action:back_to_accounts_menu$")
            ],

            # Adicionar Entrada
            ADD_INCOME_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_income_description)],
            ADD_INCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_income_amount)],
            GETTING_INCOME_DATE_FROM_CALENDAR: [CallbackQueryHandler(handle_calendar_callback, pattern="^cal:")],

            # Deletar Entrada
            GET_INCOME_ID_TO_DELETE: [
                CallbackQueryHandler(delete_income_confirm, pattern="^delete_income:"),
                CallbackQueryHandler(handle_view_navigation, pattern="^delete_incomes_nav:"), # Para navegação de mês
                CallbackQueryHandler(handle_accounts_menu_selection, pattern="^accounts_action:back_to_accounts_menu$")
            ],
            
            # Navegação de Visualização (mantendo o estado para que os botões funcionem)
            NAVIGATING_MONTHS: [CallbackQueryHandler(handle_view_navigation, pattern="^(view_accounts_nav|view_incomes_nav):")],

        },
        fallbacks=[
            CallbackQueryHandler(cancel_accounts_flow, pattern="^cal:cancel$"), # Para cancelar fluxos com calendário
            MessageHandler(filters.COMMAND('cancel'), cancel_accounts_flow),
            CallbackQueryHandler(accounts_menu, pattern="^accounts_action:back_to_accounts_menu$"), # Garante que o botão voltar funciona em qualquer estado
        ],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END # Retorna ao menu principal do bot
        }
    )