# account_handlers.py

import datetime
import calendar
import logging
import html # Importado para html.escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters, CommandHandler 
from telegram.constants import ParseMode 
from telegram.helpers import escape_markdown 
from handlers import send_main_help_menu # Adicione esta linha
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
CONFIRM_DELETE_RECURRING_ACCOUNT = 121 # NOVO ESTADO: Para confirmar exclusão de conta recorrente

ADD_INCOME_DESCRIPTION = 130
ADD_INCOME_AMOUNT = 131
ADD_INCOME_DATE = 132
GETTING_INCOME_DATE_FROM_CALENDAR = 133

GET_INCOME_ID_TO_DELETE = 140 # Estado para deletar entradas

VIEW_ACCOUNTS_MENU = 150
NAVIGATING_MONTHS = 160 # Estado para lidar com a navegação de meses no resumo/visualização

# --- Função Auxiliar para Enviar/Editar Mensagens ---
async def send_or_edit_message(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = ParseMode.HTML): 
    """
    Envia uma nova mensagem ou edita uma existente, dependendo da origem da atualização (callback_query ou message).
    O texto deve ser pré-formatado com tags HTML.
    """
    final_text = text 

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(final_text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Erro ao editar mensagem textual via callback: {e}. Enviando nova mensagem textual como fallback.")
            await update.callback_query.message.reply_text(final_text, reply_markup=reply_markup, parse_mode=parse_mode)
    elif update.message:
        await update.message.reply_text(final_text, reply_markup=reply_markup, parse_mode=parse_mode)


# --- Funções de Handler para Contas Financeiras ---

async def accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe o menu principal de gerenciamento de contas, agora com navegação por mês e saldo flutuante."""
    user_id = update.effective_user.id
    
    # Recupera o mês e ano do user_data ou usa o atual
    today = datetime.date.today()
    current_month = context.user_data.get('current_accounts_month', today.month)
    current_year = context.user_data.get('current_accounts_year', today.year)

    # Salva o mês e ano atuais no user_data para persistência
    context.user_data['current_accounts_month'] = current_month
    context.user_data['current_accounts_year'] = current_year

    summary = accounts_db.get_financial_summary(user_id, current_month, current_year)

    # Formata o nome do mês
    month_name = datetime.date(current_year, current_month, 1).strftime('%B').capitalize()

    # Lógica para o emoji de status do saldo final
    emoji_status_final_balance = ""
    if summary['final_balance_this_month'] >= 0:
        emoji_status_final_balance = "🎉" # Positivo ou zero
    else:
        emoji_status_final_balance = "⚠️" # Negativo

    # --- NOVO: Lógica para apagar as mensagens anteriores do bot para manter a interface limpa ---
    if update.callback_query:
        try:
            # Apaga a mensagem que o usuário clicou (se for um botão do bot)
            await update.callback_query.message.delete()
        except Exception as e:
            logger.warning(f"Não foi possível deletar a mensagem anterior do menu (callback): {e}")
        
    # --- PRIMEIRO BLOCO: Cabeçalho + Botões de Resumo ---
    # Usando <b> para negrito e o texto literal para parênteses
    header_text_part1 = f"💰 <b>Seu Resumo Financeiro ({month_name}/{current_year}):</b>"

    summary_buttons_data = []

    # Os valores monetários em botões são texto puro e não precisam de escape HTML.
    summary_buttons_data.append(
        [InlineKeyboardButton(f"SALDO ATUAL: R$ {summary['final_balance_this_month']:.2f} {emoji_status_final_balance}", callback_data="ignore_summary_data_balance")]
    )
    summary_buttons_data.append(
        [InlineKeyboardButton("Seu dinheiro acumulado até agora.", callback_data="ignore_summary_data_info")]
    )
    summary_buttons_data.append(
        [InlineKeyboardButton(f"Entradas no Mês: R$ {summary['total_incomes_this_month']:.2f}", callback_data="ignore_summary_data_incomes")]
    )
    summary_buttons_data.append(
        [InlineKeyboardButton(f"Contas Totais do Mês: R$ {summary['total_accounts_due_this_month']:.2f}", callback_data="ignore_summary_data_total_due")]
    )
    
    variation_emoji = "📈" if summary['current_month_net_change'] >= 0 else "📉"
    summary_buttons_data.append(
        [InlineKeyboardButton(f"Variação do Mês: {variation_emoji} R$ {summary['current_month_net_change']:.2f}", callback_data="ignore_summary_data_change")]
    )
    summary_buttons_data.append([
        InlineKeyboardButton(f"✅ Pagas: R$ {summary['paid_accounts_this_month']:.2f}", callback_data="ignore_summary_data_paid"),
        InlineKeyboardButton(f"⏰ Pendentes: R$ {summary['unpaid_accounts_this_month']:.2f}", callback_data="ignore_summary_data_unpaid")
    ])
    summary_buttons_data.append(
        [InlineKeyboardButton(f"Saldo Anterior: R$ {summary['previous_month_balance']:.2f}", callback_data="ignore_summary_data_prev_balance")]
    )

    first_message_reply_markup = InlineKeyboardMarkup(summary_buttons_data)
    
    # Envia a PRIMEIRA MENSAGEM (cabeçalho + botões de resumo)
    if update.callback_query: # Se veio de um callback, envia a nova mensagem no chat do usuário
        await update.effective_chat.send_message(text=header_text_part1, reply_markup=first_message_reply_markup, parse_mode=ParseMode.HTML)
    elif update.message: # Se veio de um comando /contas
        await update.message.reply_text(text=header_text_part1, reply_markup=first_message_reply_markup, parse_mode=ParseMode.HTML)


    # --- SEGUNDO BLOCO: Texto Rodapé + Botões de Ação ---
    footer_text_part2 = "Selecione uma opção abaixo ou navegue pelos meses:"

    action_buttons = [
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
    
    second_message_reply_markup = InlineKeyboardMarkup(action_buttons)

    # Envia a SEGUNDA MENSAGEM (texto do rodapé + botões de ação)
    if update.callback_query: # Se veio de um callback, envia a nova mensagem no chat do usuário
        await update.effective_chat.send_message(text=footer_text_part2, reply_markup=second_message_reply_markup, parse_mode=ParseMode.HTML)
    elif update.message: # Se veio de um comando /contas
        await update.message.reply_text(text=footer_text_part2, reply_markup=second_message_reply_markup, parse_mode=ParseMode.HTML)

    logger.info(f"Menu de contas exibido em duas mensagens para {user_id} para {month_name}/{current_year}.")
    return VIEW_ACCOUNTS_MENU

async def handle_accounts_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com a seleção de opções no menu principal de contas, incluindo navegação de mês."""
    query = update.callback_query
    await query.answer() # Sempre responde ao callback

    data = query.data.split(':')
    action_type = data[0] # Ex: 'accounts_action', 'accounts_nav', 'ignore_summary_data'

    # Se o callback_data for um dos botões de "ignorar", apenas responde ao callback e permanece no estado
    if action_type.startswith("ignore_summary_data"): 
        return VIEW_ACCOUNTS_MENU # Permanece no mesmo estado, sem mudança

    action_value = data[1] # Ação real, se não for ignore_summary_data

    # Ações que exigem recriar a tela de duas mensagens do menu principal
    if action_type == "accounts_action" and action_value in ["back_to_accounts_menu", "main_menu_bot"]:
        # Se for voltar ao menu principal do bot (fim do conversation), limpa user_data
        if action_value == "main_menu_bot":
            await send_or_edit_message(update, "Retornando ao menu principal do bot... 👋", parse_mode=ParseMode.HTML)
            context.user_data.clear() # Limpa TUDO no user_data para um recomeço limpo
            await send_main_help_menu(update, context)
            return ConversationHandler.END
        # Se for apenas voltar para o menu de contas, recria o menu (que enviará duas mensagens)
        return await accounts_menu(update, context) # Recria o menu de duas mensagens

    # Ações que levam a outros fluxos (só um return para o próximo estado/fluxo)
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
    
    elif action_type == "accounts_nav": # Ajustado para navegar no menu principal
        current_month = context.user_data.get('current_accounts_month', datetime.date.today().month)
        current_year = context.user_data.get('current_accounts_year', datetime.date.today().year)

        if action_value == "prev_month":
            current_month, current_year = (12, current_year - 1) if current_month == 1 else (current_month - 1, current_year)
        elif action_value == "next_month":
            current_month, current_year = (1, current_year + 1) if current_month == 12 else (current_month + 1, current_year)
        
        context.user_data['current_accounts_month'] = current_month
        context.user_data['current_accounts_year'] = current_year
        
        return await accounts_menu(update, context) # Recria o menu de duas mensagens

    logger.warning(f"Ação de menu de contas não tratada: {query.data} por {update.effective_user.id}")
    return await accounts_menu(update, context) # Em caso de ação desconhecida, recria o menu

# --- Funções de Calendário ---
def create_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    """Cria um InlineKeyboardMarkup para um calendário."""
    keyboard = []
    # Cabeçalho: Mês e Ano
    keyboard.append([
        InlineKeyboardButton("«", callback_data=f"cal:nav:{year-1}:{month}"), # Ano anterior
        InlineKeyboardButton("<", callback_data=f"cal:nav:{year}:{month-1 if month > 1 else 12}"), # Mês anterior
        InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="cal:ignore"), # Mês e ano (não clicável)
        InlineKeyboardButton(">", callback_data=f"cal:nav:{year}:{month+1 if month < 12 else 1}"), # Próximo mês
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
    # Usar html.escape para strings que podem vir do usuário para evitar problemas com < > &
    escaped_type = html.escape(context.user_data[f'{prefix}_type'])

    text = f"🗓️ Selecione a data para a {escaped_type}:"

    if update.callback_query and update.callback_query.message:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    
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
        await send_or_edit_message(update, "Houve um erro no fluxo do calendário. Por favor, tente novamente do menu principal.", parse_mode=ParseMode.HTML)
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
        import html # Importação adicionada aqui para uso local
        escaped_type = html.escape(context.user_data[f'{prefix}_type'])
        text = f"🗓️ Selecione a data para a {escaped_type}:"

        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return context.user_data[f'{prefix}_next_state_calendar'] # Permanece no estado de espera de clique no calendário

    elif action == "cancel":
        return await cancel_accounts_flow(update, context) # Retorna ao menu principal de contas

    return context.user_data[f'{prefix}_next_state_calendar'] # Permanece no estado atual se for um 'ignore'

# --- Adicionar Conta/Despesa ---
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para adicionar uma nova conta."""
    user_id = update.effective_user.id
    await send_or_edit_message(update, "Qual o nome da conta/despesa (ex: Aluguel, Supermercado)?", parse_mode=ParseMode.HTML)
    logger.info(f"Iniciando add_account_flow para {user_id}.")
    return ADD_ACCOUNT_NAME

async def get_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da conta."""
    context.user_data['account_name'] = update.message.text.strip()
    await send_or_edit_message(update, "Qual o valor dessa conta (ex: 1500.50)?", parse_mode=ParseMode.HTML)
    return ADD_ACCOUNT_AMOUNT

async def get_account_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o valor da conta."""
    try:
        amount = float(update.message.text.strip().replace(',', '.'))
        if amount <= 0:
            await send_or_edit_message(update, "O valor deve ser um número positivo. Tente novamente.", parse_mode=ParseMode.HTML)
            return ADD_ACCOUNT_AMOUNT
        context.user_data['account_amount'] = amount
        
        # Define os dados para o fluxo do calendário
        context.user_data['account_type'] = "conta/despesa"
        context.user_data['account_next_state_calendar'] = GETTING_ACCOUNT_DATE_FROM_CALENDAR
        
        # Chama a função para enviar o calendário
        return await send_calendar_message(update, context, 'account')

    except ValueError:
        await send_or_edit_message(update, "Valor inválido. Por favor, insira um número (ex: 1500.50).", parse_mode=ParseMode.HTML)
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

    await send_or_edit_message(update, "Esta conta é recorrente?", reply_markup, parse_mode=ParseMode.HTML)
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
        await send_or_edit_message(update, "Quantas parcelas (número inteiro)?", parse_mode=ParseMode.HTML)
        return ADD_ACCOUNT_PARCEL_COUNT
    else: # 'none' ou 'indefinite'
        name = context.user_data['account_name']
        amount = context.user_data['account_amount']
        due_date = context.user_data['account_selected_date'] # Data do calendário
        user_id = query.from_user.id

        # Para HTML, a formatação <b> e literal
        message_text = f"🎉 Conta '<b>{name}</b>' (R$ {amount:.2f}) adicionada com sucesso como <b>{recurrence}</b>!"

        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence):
            await send_or_edit_message(update, message_text, parse_mode=ParseMode.HTML)
            logger.info(f"Conta '{name}' adicionada por {user_id}.")
        else:
            await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a conta. Talvez ela já exista ou houve um erro no banco de dados.", parse_mode=ParseMode.HTML)
            logger.warning(f"Falha ao adicionar conta '{name}' para {user_id}.")
        
        # Limpa os dados do user_data específicos deste fluxo
        context.user_data.pop('account_name', None)
        context.user_data.pop('account_amount', None)
        context.user_data.pop('account_selected_date', None)
        context.user_data.pop('account_recurrence', None)
        context.user_data.pop('account_type', None)
        context.user_data.pop('account_next_state_calendar', None)
        context.user_data.pop('calendar_flow_prefix', None)
        context.user_data.pop('account_cal_year', None)
        context.user_data.pop('account_cal_month', None)
        
        return await accounts_menu(update, context) # Retorna para o menu de contas

async def get_account_parcel_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o número de parcelas para contas fixas."""
    try:
        parcel_count = int(update.message.text.strip())
        if parcel_count <= 0:
            await send_or_edit_message(update, "O número de parcelas deve ser um número positivo. Tente novamente.", parse_mode=ParseMode.HTML)
            return ADD_ACCOUNT_PARCEL_COUNT

        context.user_data['account_parcel_count'] = parcel_count

        name = context.user_data['account_name']
        amount = context.user_data['account_amount']
        due_date = context.user_data['account_selected_date'] # Data do calendário
        recurrence = context.user_data['account_recurrence']
        user_id = update.effective_user.id

        message_text = f"🎉 Conta '<b>{name}</b>' (R$ {amount:.2f}) adicionada com sucesso como parcelada em <b>{parcel_count}x</b>!"
        
        # CORREÇÃO CRUCIAL AQUI: Removido 'current_parcel=1' da chamada de add_monthly_account
        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence, parcel_count):
            await send_or_edit_message(update, message_text, parse_mode=ParseMode.HTML)
            logger.info(f"Conta '{name}' adicionada por {user_id} como parcelada.")
        else:
            await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a conta. Talvez ela já exista ou houve um erro no banco de dados.", parse_mode=ParseMode.HTML)
            logger.warning(f"Falha ao adicionar conta parcelada '{name}' para {user_id}.")
        
        # Limpa os dados do user_data específicos deste fluxo
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
        
        return await accounts_menu(update, context) # Retorna para o menu de contas
    except ValueError:
        await send_or_edit_message(update, "Número de parcelas inválido. Por favor, insira um número inteiro.", parse_mode=ParseMode.HTML)
        return ADD_ACCOUNT_PARCEL_COUNT

# --- Marcar Conta como Paga ---
async def mark_account_paid_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para marcar uma conta como paga, listando-as com botões."""
    user_id = update.effective_user.id
    
    logger.debug(f"mark_account_paid_start para user {user_id}")

    current_month = context.user_data.get('current_accounts_month', datetime.date.today().month)
    current_year = context.user_data.get('current_accounts_year', datetime.date.today().year)
    
    accounts = accounts_db.get_monthly_accounts(user_id, current_month, current_year)

    # Filtra apenas as contas PENDENTES para marcar como paga
    pending_accounts = [acc for acc in accounts if not acc[4]] # acc[4] é is_paid

    month_display = datetime.date(current_year, current_month, 1).strftime('%B/%Y')
    message_text = f"✅ <b>Marcar contas como pagas ({month_display}):</b>\n\n"
    keyboard = []

    if not pending_accounts:
        message_text += "Você não tem contas <b>pendentes</b> para marcar como pagas neste mês. 🎉"
    else:
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel, template_id in pending_accounts:
            status = "✅ PAGA" if is_paid else "❌ PENDENTE"
            try:
                # Formato DD/MM para exibição
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m')
            except (ValueError, TypeError): # Lida com due_date sendo None ou formato inválido
                due_date_display = due_date if due_date else "N/A"
            
            recurrence_info = ""
            if recurrence == 'fixed_parcel' and parcel_count:
                recurrence_info = f" ({current_parcel}/{parcel_count}x)"
            elif recurrence == 'indefinite':
                recurrence_info = " (Recorrente)"

            # No HTML, o conteúdo dentro dos botões é tratado como texto simples, então não precisa de tags HTML.
            button_text = f"{name} - R$ {amount:.2f} ({due_date_display}) | {status}{recurrence_info}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"mark_account:{acc_id}")])

    keyboard.append([InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_or_edit_message(update, message_text, reply_markup, parse_mode=ParseMode.HTML)

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
        account_id = int(query.data.split(':')[1])

        if accounts_db.mark_account_paid(account_id, user_id):
            await send_or_edit_message(update, f"🎉 Conta marcada como paga com sucesso! ID: <code>{account_id}</code>", parse_mode=ParseMode.HTML)
            logger.info(f"Conta ID {account_id} marcada como paga por {user_id}.")
        else:
            await send_or_edit_message(update, f"❌ Não foi possível marcar a conta como paga. Verifique se ela já está paga ou se há um erro. ID: <code>{account_id}</code>", parse_mode=ParseMode.HTML)
            logger.warning(f"Falha ao marcar conta ID {account_id} como paga para {user_id}.")
        
        context.user_data.clear()
        return await accounts_menu(update, context) # Retorna para o menu de contas após a operação
    
    # Se chegou aqui, é um callback inesperado, volta para o menu
    return await accounts_menu(update, context)

# --- Funções Auxiliares de Navegação para Visualização e Deleção ---
def build_month_navigation_keyboard(current_year: int, current_month: int, nav_prefix: str) -> list[list[InlineKeyboardButton]]:
    """Cria os botões de navegação de mês (Mês Anterior/Próximo Mês)."""
    # Calcula o mês anterior
    prev_month_dt = datetime.date(current_year, current_month, 1) - datetime.timedelta(days=1)
    prev_month_str = prev_month_dt.strftime('%Y-%m') # Formato 'AAAA-MM' para o callback_data

    # Calcula o próximo mês
    next_month_dt = datetime.date(current_year, current_month, 1) + datetime.timedelta(days=32) # Adiciona 32 dias para garantir que vai para o próximo mês
    next_month_str = next_month_dt.strftime('%Y-%m') # Formato 'AAAA-MM' para o callback_data

    return [
        [
            InlineKeyboardButton("⬅️ Mês Anterior", callback_data=f"{nav_prefix}:{prev_month_str}"),
            InlineKeyboardButton("Próximo Mês ➡️", callback_data=f"{nav_prefix}:{next_month_str}")
        ]
    ]

async def handle_view_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com a navegação de mês nas telas de visualização e deleção."""
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split(':')
    nav_prefix = data_parts[0] # Ex: 'view_accounts_nav', 'delete_accounts_nav'
    selected_month_str = data_parts[1] # Ex: '2025-07'

    year, month = map(int, selected_month_str.split('-'))
    
    # Atualiza o user_data e chama a função de visualização/deleção apropriada
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
    
    logger.warning(f"Ação de menu de contas não tratada: {query.data}")
    # Retorna o estado do menu de contas para manter a conversa ativa
    # Isso é importante porque a navegação de meses em telas detalhadas não finaliza o ConversationHandler.
    return VIEW_ACCOUNTS_MENU 

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

    message_text = f"🗑️ <b>Contas para deletar ({month_name}/{year}):</b>\n\n"
    keyboard_buttons = [] # Lista para os botões das contas

    if not accounts:
        message_text += "Você não tem contas registradas para este mês."
    else:
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel, template_id in accounts:
            status = "✅ PAGA" if is_paid else "❌ PENDENTE"
            try:
                # Formato DD/MM para exibição
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m')
            except (ValueError, TypeError):
                due_date_display = due_date if due_date else "N/A"
            
            recurrence_info = ""
            if recurrence == 'fixed_parcel' and parcel_count:
                recurrence_info = f" ({current_parcel}/{parcel_count}x)"
            elif recurrence == 'indefinite':
                recurrence_info = " (Recorrente)"

            # No HTML, o conteúdo dentro dos botões é tratado como texto simples.
            button_text = f"{name} - R$ {amount:.2f} ({due_date_display}) | {status}{recurrence_info}"
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"delete_account:{acc_id}")])
    
    # Adiciona os botões de navegação de mês e o botão de voltar
    month_nav_keyboard = build_month_navigation_keyboard(year, month, "delete_accounts_nav")
    back_button = [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]

    # Concatena os botões das contas com os botões de navegação e o de voltar
    final_keyboard = keyboard_buttons + month_nav_keyboard + [back_button]
    reply_markup = InlineKeyboardMarkup(final_keyboard)

    await send_or_edit_message(update, message_text, reply_markup, parse_mode=ParseMode.HTML)
    
    logger.info(f"Exibindo contas para deletar para {user_id} para {month_name}/{year}.")
    return GET_ACCOUNT_ID_TO_DELETE # Novo estado para aguardar o clique no botão da conta

async def delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Lida com a seleção de conta para exclusão.
    Se a conta for recorrente, pergunta ao usuário como deseja excluir.
    Se não for recorrente, exclui diretamente a instância.
    """
    query = update.callback_query
    await query.answer()

    # Verificar se é um callback do botão "Voltar"
    if query.data == "accounts_action:back_to_accounts_menu":
        return await accounts_menu(update, context)

    # Se for um clique em um botão de conta (ex: "delete_account:123")
    if query.data.startswith("delete_account:"):
        user_id = query.from_user.id
        account_id = int(query.data.split(':')[1])
        
        # Obtém os detalhes da conta para verificar a recorrência e template_id
        # id, name, amount, due_date, is_paid, recurrence_type, current_parcel, total_parcels, template_id
        account_details = accounts_db.get_account_by_id(account_id, user_id)

        if not account_details:
            await send_or_edit_message(update, f"❌ Conta com ID <code>{account_id}</code> não encontrada ou não pertence a você.", parse_mode=ParseMode.HTML)
            logger.warning(f"Tentativa de deletar conta não existente ou não pertencente a {user_id}. ID: {account_id}.")
            return await accounts_menu(update, context)
        
        # Desempacota os detalhes (certifique-se que o get_account_by_id retorna 9 valores)
        _, name, amount, due_date, _, recurrence_type, current_parcel, total_parcels, template_id = account_details

        # Armazena os dados da conta temporariamente para a próxima etapa de confirmação
        context.user_data['account_to_delete'] = {
            'id': account_id,
            'name': name,
            'recurrence_type': recurrence_type,
            'template_id': template_id,
            'amount': amount, 
            'month': datetime.datetime.strptime(due_date, '%Y-%m-%d').month,
            'year': datetime.datetime.strptime(due_date, '%Y-%m-%d').year
        }

        # Verifica se a conta é recorrente ou parcelada
        if recurrence_type == 'none':
            # Se não for recorrente, deleta diretamente a instância
            if accounts_db.delete_monthly_account(account_id, user_id):
                await send_or_edit_message(update, f"🗑️ Conta '<b>{name}</b>' (ID: <code>{account_id}</code>) deletada com sucesso!", parse_mode=ParseMode.HTML)
                logger.info(f"Instância de conta '{name}' (ID: {account_id}) deletada por {user_id} (não recorrente).")
            else:
                await send_or_edit_message(update, f"❌ Não foi possível deletar a conta '<b>{name}</b>' (ID: <code>{account_id}</code>).", parse_mode=ParseMode.HTML)
                logger.warning(f"Falha ao deletar instância de conta '{name}' (ID: {account_id}) para {user_id}.")
            
            # Após a operação, retorna à tela de exclusão para que o usuário possa deletar mais
            context.user_data.pop('account_to_delete', None) # Limpa dados temporários
            return await delete_account_start(update, context)
        else:
            # Se for recorrente, pergunta ao usuário o que deseja deletar
            message_text = f"A conta '<b>{name}</b>' (R$ {amount:.2f}, ID: <code>{account_id}</code>) é uma conta <b>recorrente</b>."
            if recurrence_type == 'fixed_parcel':
                message_text += f"\nEla é a parcela {current_parcel}/{total_parcels}."
            message_text += "\n\nComo você deseja excluí-la?"
            
            keyboard = [
                [InlineKeyboardButton("🗑️ Apenas esta instância (deste mês)", callback_data=f"delete_recurring_choice:instance:{account_id}")],
                [InlineKeyboardButton("🔥 Template e todas as futuras instâncias", callback_data=f"delete_recurring_choice:template:{template_id}")],
                [InlineKeyboardButton("↩️ Voltar (Cancelar)", callback_data="accounts_action:back_to_accounts_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await send_or_edit_message(update, message_text, reply_markup, parse_mode=ParseMode.HTML)
            return CONFIRM_DELETE_RECURRING_ACCOUNT # Muda para o novo estado de confirmação
    
    # Em caso de callback inesperado, volta para o menu de contas
    return await accounts_menu(update, context)

async def handle_delete_recurring_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com a escolha do usuário sobre como deletar uma conta recorrente."""
    query = update.callback_query
    await query.answer()

    choice_parts = query.data.split(':')
    choice_type = choice_parts[1] # 'instance' ou 'template'
    
    user_id = query.from_user.id
    account_data = context.user_data.get('account_to_delete')

    if not account_data:
        await send_or_edit_message(update, "❌ Erro: Dados da conta para exclusão não encontrados. Por favor, tente novamente do menu 'Deletar Conta'.", parse_mode=ParseMode.HTML)
        logger.warning(f"Dados de 'account_to_delete' ausentes para user {user_id} em handle_delete_recurring_choice.")
        return await accounts_menu(update, context)

    account_id = account_data['id']
    template_id = account_data['template_id']
    account_name = account_data['name']
    
    # Se a escolha é 'instance', vamos deletar a instância e marcar como ignorada
    if choice_type == 'instance':
        # Remove a instância do DB. A função delete_monthly_account agora cuidará de adicionar à tabela 'ignored_monthly_instances'
        if accounts_db.delete_monthly_account(account_id, user_id): 
            message = f"🗑️ A instância da conta '<b>{account_name}</b>' (ID: <code>{account_id}</code>) deste mês foi deletada com sucesso! Ela não aparecerá mais neste mês."
            logger.info(f"Instância de conta '{account_name}' (ID: {account_id}) deletada para user {user_id} e marcada para não ser regenerada.")
        else:
            message = f"❌ Não foi possível deletar esta instância da conta '<b>{account_name}</b>' (ID: <code>{account_id}</code>)."
            logger.warning(f"Falha ao deletar instância de conta '{account_name}' (ID: {account_id}) para {user_id}.")
    elif choice_type == 'template':
        if template_id:
            # Deleta o template e todas as instâncias (a função já limpa a tabela de ignorados)
            if accounts_db.delete_account_template_and_future_instances(template_id, user_id):
                message = f"🔥 O template da conta '<b>{account_name}</b>' e <b>todas as suas instâncias futuras</b> foram deletados com sucesso!"
                logger.info(f"Template de conta '{account_name}' (ID: {template_id}) e instâncias futuras deletadas para user {user_id}.")
            else:
                message = f"❌ Não foi possível deletar o template da conta '<b>{account_name}</b>' e suas instâncias futuras."
                logger.warning(f"Falha ao deletar template de conta '{account_name}' (ID: {template_id}) e instâncias futuras para {user_id}.")
        else:
            message = "❌ Erro: Não foi possível encontrar o template para deletar esta conta recorrente."
            logger.error(f"Tentativa de deletar template para conta recorrente {account_id} sem template_id para user {user_id}.")
    
    await send_or_edit_message(update, message, parse_mode=ParseMode.HTML)
    
    context.user_data.pop('account_to_delete', None) # Limpa os dados temporários
    
    # Retorna para a tela de deleção para que o usuário possa continuar a gerenciar as contas
    return await delete_account_start(update, context)


# --- Restante das funções (add_income_start, delete_income_start, view_detailed_accounts, view_detailed_incomes, cancel_accounts_flow)
# --- Permanecem inalteradas, mas os textos que elas enviam precisam ser revisados para escapa manual, pois send_or_edit_message não faz mais escape automático.
# --- Vou garantir que todos os textos sejam adequadamente escapados.


async def add_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para adicionar uma nova entrada de rendimento."""
    user_id = update.effective_user.id
    await send_or_edit_message(update, "Qual a descrição da entrada (ex: Salário, Freelance)?", parse_mode=ParseMode.HTML)
    logger.info(f"Iniciando add_income_flow para {user_id}.")
    return ADD_INCOME_DESCRIPTION

async def get_income_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a descrição da entrada."""
    context.user_data['income_description'] = update.message.text.strip()
    await send_or_edit_message(update, "Qual o valor da entrada (ex: 3000.00)?", parse_mode=ParseMode.HTML)
    return ADD_INCOME_AMOUNT

async def get_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o valor da entrada."""
    try:
        amount = float(update.message.text.strip().replace(',', '.'))
        if amount <= 0:
            await send_or_edit_message(update, "O valor deve ser um número positivo. Tente novamente.", parse_mode=ParseMode.HTML)
            return ADD_INCOME_AMOUNT
        context.user_data['income_amount'] = amount
        
        # Define os dados para o fluxo do calendário
        context.user_data['income_type'] = "entrada"
        context.user_data['income_next_state_calendar'] = GETTING_INCOME_DATE_FROM_CALENDAR
        
        # Chama a função para enviar o calendário
        return await send_calendar_message(update, context, 'income')

    except ValueError:
        await send_or_edit_message(update, "Valor inválido. Por favor, insira um número (ex: 3000.00).", parse_mode=ParseMode.HTML)
        return ADD_INCOME_AMOUNT

async def process_income_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa os dados da entrada após a data ser selecionada."""
    description = context.user_data['income_description']
    amount = context.user_data['income_amount']
    income_date_db = context.user_data['income_selected_date'] # Data do calendário
    user_id = update.effective_user.id

    message_text = f"🎉 Entrada '<b>{description}</b>' (R$ {amount:.2f}) adicionada com sucesso!"

    if accounts_db.add_financial_income(user_id, description, amount, income_date_db):
        await send_or_edit_message(update, message_text, parse_mode=ParseMode.HTML)
        logger.info(f"Entrada '{description}' adicionada por {user_id}.")
    else:
        await send_or_edit_message(update, "❌ Ops! Não foi possível adicionar a entrada. Talvez ela já exista ou houve um erro no banco de dados.", parse_mode=ParseMode.HTML)
        logger.warning(f"Falha ao adicionar entrada '{description}' para {user_id}.")
    
    # Limpa os dados do user_data específicos deste fluxo
    context.user_data.pop('income_description', None)
    context.user_data.pop('income_amount', None)
    context.user_data.pop('income_selected_date', None)
    context.user_data.pop('income_type', None)
    context.user_data.pop('income_next_state_calendar', None)
    context.user_data.pop('calendar_flow_prefix', None)
    context.user_data.pop('income_cal_year', None)
    context.user_data.pop('income_cal_month', None)
    
    return await accounts_menu(update, context) # Retorna para o menu de contas

async def delete_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo para deletar uma entrada, listando-as com botões."""
    user_id = update.effective_user.id
    today = datetime.date.today()
    month = context.user_data.get('delete_month', context.user_data.get('current_accounts_month', today.month))
    year = context.user_data.get('delete_year', context.user_data.get('current_accounts_year', today.year))

    context.user_data['delete_month'] = month
    context.user_data['delete_year'] = year

    incomes = accounts_db.get_financial_incomes(user_id, month, year)
    month_name = datetime.date(year, month, 1).strftime('%B').capitalize()

    message_text = f"💸 <b>Entradas para deletar ({month_name}/{year}):</b>\n\n"
    income_buttons = []
    if not incomes:
        message_text += "Você não tem entradas registradas para este mês."
    else:
        for inc_id, description, amount, income_date_db in incomes:
            try:
                # Formato DD/MM para exibição
                income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m')
            except (ValueError, TypeError):
                income_date_display = income_date_db if income_date_db else "N/A"
            
            # No HTML, o conteúdo dentro dos botões é tratado como texto simples.
            button_text = f"{description} - R$ {amount:.2f} ({income_date_display})"
            income_buttons.append([InlineKeyboardButton(button_text, callback_data=f"delete_income:{inc_id}")])
    
    month_nav_keyboard = build_month_navigation_keyboard(year, month, "delete_incomes_nav")
    back_button = [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]
    
    final_keyboard = income_buttons + month_nav_keyboard + [back_button]
    reply_markup = InlineKeyboardMarkup(final_keyboard)

    await send_or_edit_message(update, message_text, reply_markup, parse_mode=ParseMode.HTML)
    logger.info(f"Exibindo entradas para deletar para {user_id} para {month_name}/{year}.")
    return GET_INCOME_ID_TO_DELETE

async def delete_income_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e deleta a entrada APÓS O CLIQUE NO BOTÃO."""
    query = update.callback_query
    await query.answer()

    if query.data == "accounts_action:back_to_accounts_menu":
        return await accounts_menu(update, context)

    if query.data.startswith("delete_income:"):
        user_id = query.from_user.id
        income_id = int(query.data.split(':')[1])

        if accounts_db.delete_financial_income(income_id, user_id):
            await send_or_edit_message(update, f"🗑️ Entrada deletada com sucesso! ID: <code>{income_id}</code>", parse_mode=ParseMode.HTML)
            logger.info(f"Entrada ID {income_id} deletada por {user_id}.")
        else:
            await send_or_edit_message(update, f"❌ Não foi possível deletar a entrada. Verifique se o ID está correto. ID: <code>{income_id}</code>", parse_mode=ParseMode.HTML)
            logger.warning(f"Falha ao deletar entrada ID {income_id} para {user_id}.")
    
    # Após deletar, retorna para a tela de deleção de entradas para que o usuário possa deletar mais
    return await delete_income_start(update, context)

async def view_detailed_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    today = datetime.date.today()
    month = context.user_data.get('view_month', context.user_data.get('current_accounts_month', today.month))
    year = context.user_data.get('view_year', context.user_data.get('current_accounts_year', today.year))

    accounts = accounts_db.get_detailed_monthly_accounts(user_id, month, year)
    month_name = datetime.date(year, month, 1).strftime('%B').capitalize()

    message_text = f"📊 <b>Suas Contas/Despesas ({month_name}/{year}):</b>\n\n"
    if not accounts:
        message_text += "Você não tem contas registradas para este mês."
    else:
        for acc_id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel, template_id in accounts:
            status = "✅ PAGA" if is_paid else "❌ PENDENTE"
            try:
                due_date_display = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                due_date_display = due_date if due_date else "N/A"
            
            recurrence_info = ""
            if recurrence == 'fixed_parcel' and parcel_count:
                recurrence_info = f" ({current_parcel}/{parcel_count}x)"
            elif recurrence == 'indefinite':
                recurrence_info = " (Recorrente)"
            
            # Para HTML, usar tags <b> para negrito e <code> para código.
            # O python-telegram-bot lida automaticamente com o escape de <, >, & dentro das tags.
            # Não é necessário usar escape_markdown aqui.
            message_text += f"<b>ID: {acc_id}</b> - <b>{name}</b>\n  <code>R$ {amount:.2f} | Vencimento: {due_date_display}{recurrence_info} | Status: {status}</code>\n\n"
    
    month_nav_keyboard = build_month_navigation_keyboard(year, month, "view_accounts_nav")
    back_button = [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]
    
    final_keyboard = month_nav_keyboard + [back_button] # Navegação e botão de voltar

    reply_markup = InlineKeyboardMarkup(final_keyboard)

    await send_or_edit_message(update, message_text, reply_markup, parse_mode=ParseMode.HTML)
    logger.info(f"Contas detalhadas exibidas para {user_id} para {month_name}/{year}.")
    return VIEW_ACCOUNTS_MENU

# --- Visualizar Entradas Detalhadas ---
async def view_detailed_incomes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    today = datetime.date.today()
    month = context.user_data.get('view_month', context.user_data.get('current_accounts_month', today.month))
    year = context.user_data.get('view_year', context.user_data.get('current_accounts_year', today.month))
    
    incomes = accounts_db.get_detailed_financial_incomes(user_id, month, year)
    month_name = datetime.date(year, month, 1).strftime('%B').capitalize()

    message_text = f"💸 <b>Suas Entradas/Rendimentos ({month_name}/{year}):</b>\n\n"
    if not incomes:
        message_text += "Você não tem entradas registradas para este mês."
    else:
        for inc_id, description, amount, income_date_db in incomes:
            try:
                income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m')
            except (ValueError, TypeError):
                income_date_display = income_date_db if income_date_db else "N/A"
            
            # Para HTML, usar tags <b> para negrito e <code> para código.
            message_text += f"<b>ID: {inc_id}</b> - <b>{description}</b>\n  <code>R$ {amount:.2f} | Data: {income_date_display}</code>\n\n"
    
    month_nav_keyboard = build_month_navigation_keyboard(year, month, "view_incomes_nav")
    back_button = [InlineKeyboardButton("↩️ Voltar ao Menu de Contas", callback_data="accounts_action:back_to_accounts_menu")]

    final_keyboard = month_nav_keyboard + [back_button] # Navegação e botão de voltar
    reply_markup = InlineKeyboardMarkup(final_keyboard)

    await send_or_edit_message(update, message_text, reply_markup, parse_mode=ParseMode.HTML)
    logger.info(f"Entradas detalhadas exibidas para {user_id} para {month_name}/{year}.")
    return VIEW_ACCOUNTS_MENU

# --- Função de Cancelamento ---
async def cancel_accounts_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela o fluxo atual e retorna ao menu principal de contas, limpando dados temporários."""
    await send_or_edit_message(update, "Operação de contas cancelada. ✅", parse_mode=ParseMode.HTML)
    
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
    """Configura e retorna o ConversationHandler para o gerenciamento de contas."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("contas", accounts_menu), # Comando para entrar no menu de contas
            CallbackQueryHandler(accounts_menu, pattern="^accounts_action:open_menu$") # Caso seja chamado por um botão 'abrir menu de contas' de outro lugar
        ],
        states={
            VIEW_ACCOUNTS_MENU: [
                # Este handler agora é mais específico para as ações do menu principal
                # Também processará o 'ignore_summary_data' e seus variantes.
                CallbackQueryHandler(handle_accounts_menu_selection, pattern=r"^accounts_action:|^accounts_nav:|^ignore_summary_data"), 
                # Este handler para a navegação de meses nas telas de visualização/deleção que podem levar ao VIEW_ACCOUNTS_MENU
                CallbackQueryHandler(handle_view_navigation, pattern=r"^(view_accounts_nav|view_incomes_nav|delete_accounts_nav|delete_incomes_nav):"), 
            ],
            
            # --- Fluxo de Adicionar Conta ---
            ADD_ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_account_name)],
            ADD_ACCOUNT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_account_amount)],
            GETTING_ACCOUNT_DATE_FROM_CALENDAR: [
                CallbackQueryHandler(handle_calendar_callback, pattern=r"^cal:"), # Qualquer clique no calendário
            ],
            ADD_ACCOUNT_RECURRENCE: [
                CallbackQueryHandler(get_account_recurrence, pattern="^(none|indefinite|fixed_parcel|cal:cancel)$") # Inclui o cancelar do calendário
            ],
            ADD_ACCOUNT_PARCEL_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_account_parcel_count)],

            # --- Fluxo de Marcar Conta como Paga ---
            GET_ACCOUNT_ID_TO_MARK: [
                CallbackQueryHandler(mark_account_paid_confirm, pattern=r"^mark_account:\d+$"),
                CallbackQueryHandler(mark_account_paid_confirm, pattern=r"^accounts_action:back_to_accounts_menu$"),
            ],

            # --- Fluxo de Deletar Conta (com navegação de mês) ---
            GET_ACCOUNT_ID_TO_DELETE: [
                CallbackQueryHandler(delete_account_confirm, pattern=r"^delete_account:\d+$"), # Chama delete_account_confirm primeiro
                CallbackQueryHandler(handle_view_navigation, pattern=r"^(delete_accounts_nav):"), # Para navegação de mês
                CallbackQueryHandler(handle_accounts_menu_selection, pattern=r"^accounts_action:back_to_accounts_menu$") # Botão voltar
            ],
            CONFIRM_DELETE_RECURRING_ACCOUNT: [ # NOVO ESTADO: Lida com a escolha do usuário
                CallbackQueryHandler(handle_delete_recurring_choice, pattern=r"^delete_recurring_choice:(instance|template):\d+$"),
                CallbackQueryHandler(handle_accounts_menu_selection, pattern=r"^accounts_action:back_to_accounts_menu$") # Botão voltar
            ],


            # --- Fluxo de Adicionar Entrada ---
            ADD_INCOME_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_income_description)],
            ADD_INCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_income_amount)],
            GETTING_INCOME_DATE_FROM_CALENDAR: [
                CallbackQueryHandler(handle_calendar_callback, pattern=r"^cal:"), # Qualquer clique no calendário
            ],

            # --- Fluxo de Deletar Entrada (com navegação de mês) ---
            GET_INCOME_ID_TO_DELETE: [
                CallbackQueryHandler(delete_income_confirm, pattern=r"^delete_income:\d+$"),
                CallbackQueryHandler(handle_view_navigation, pattern=r"^(delete_incomes_nav):"), # Para navegação de mês
                CallbackQueryHandler(handle_accounts_menu_selection, pattern=r"^accounts_action:back_to_accounts_menu$")
            ],
            
            # Estado para lidar com a navegação de meses em telas detalhadas (mantendo o estado para que os botões funcionam)
            # Este estado captura as navegações de mês de dentro de view_accounts e view_detailed_incomes, etc.
            NAVIGATING_MONTHS: [CallbackQueryHandler(handle_view_navigation, pattern=r"^(view_accounts_nav|view_incomes_nav|delete_accounts_nav|delete_incomes_nav):")],

        },
        fallbacks=[
            CallbackQueryHandler(cancel_accounts_flow, pattern="^cal:cancel$"), # Para cancelar fluxos com calendário
            CommandHandler("cancelar", cancel_accounts_flow), # Cancelar em qualquer ponto da conversa de contas
            # Se algo inesperado acontecer, volta para o menu principal do bot
            # Certifique-se de que este fallback não intercepte mensagens que deveriam ir para outros handlers
            MessageHandler(filters.TEXT & ~filters.COMMAND, accounts_menu) 
        ],
        allow_reentry=True,
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END # Retorna ao menu principal do bot
        }
    )