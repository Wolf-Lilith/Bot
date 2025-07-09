import datetime
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

import accounts_db # Certifique-se de que esta linha está aqui!

logger = logging.getLogger(__name__)

# --- Estados para o ConversationHandler de Contas ---
ADD_ACCOUNT_NAME = 10
ADD_ACCOUNT_AMOUNT = 11
ADD_ACCOUNT_DUE_DATE = 12
ADD_ACCOUNT_RECURRENCE = 13
ADD_ACCOUNT_PARCEL_COUNT = 14

GET_ACCOUNT_ID_TO_EDIT = 20
EDIT_ACCOUNT_FIELD = 21
EDIT_ACCOUNT_NEW_VALUE = 22

GET_ACCOUNT_ID_TO_MARK = 30

GET_ACCOUNT_ID_TO_DELETE = 40

ADD_INCOME_DESCRIPTION = 50
ADD_INCOME_AMOUNT = 51
ADD_INCOME_DATE = 52

GET_INCOME_ID_TO_DELETE = 60

VIEW_ACCOUNTS_MENU = 70 # Estado para o menu principal de contas
VIEW_DETAILED_ACCOUNTS = 71 # Novo estado para ver contas detalhadas
VIEW_DETAILED_INCOMES = 72 # Novo estado para ver entradas detalhadas


# --- Funções de Handler para Contas Financeiras ---

async def accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe o menu principal de gerenciamento de contas."""
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("➕ Adicionar Conta", callback_data="accounts_action:add_account")],
        [InlineKeyboardButton("💰 Adicionar Entrada", callback_data="accounts_action:add_income")],
        [InlineKeyboardButton("📊 Ver Resumo Mensal", callback_data="accounts_action:view_summary")],
        # NOVOS BOTÕES AQUI 👇
        [InlineKeyboardButton("📋 Ver Contas Detalhadas", callback_data="accounts_action:view_detailed_accounts")],
        [InlineKeyboardButton("💸 Ver Entradas Detalhadas", callback_data="accounts_action:view_detailed_incomes")],
        # FIM DOS NOVOS BOTÕES 👆
        [InlineKeyboardButton("✏️ Editar Conta", callback_data="accounts_action:edit_account")],
        [InlineKeyboardButton("✅ Marcar Conta como Paga", callback_data="accounts_action:mark_account")],
        [InlineKeyboardButton("❌ Apagar Conta", callback_data="accounts_action:delete_account")],
        [InlineKeyboardButton("🗑️ Apagar Entrada", callback_data="accounts_action:delete_income")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="accounts_action:main_menu_from_finances")] # Mudei o callback_data para evitar conflito com o retorno do ConversationHandler
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "Olá! O que você gostaria de fazer com suas finanças? 💵",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Olá! O que você gostaria de fazer com suas finanças? 💵",
            reply_markup=reply_markup
        )
    logger.info(f"Menu de contas exibido para {user_id}.")
    return VIEW_ACCOUNTS_MENU # Retorna o estado correto para aguardar o callback do menu

async def handle_accounts_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com os callbacks do menu de contas."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "accounts_action:add_account":
        return await add_account_start(update, context)
    elif data == "accounts_action:add_income":
        return await add_income_start(update, context)
    elif data == "accounts_action:view_summary":
        return await view_summary(update, context)
    # NOVOS HANDLERS AQUI 👇
    elif data == "accounts_action:view_detailed_accounts":
        return await view_detailed_accounts(update, context)
    elif data == "accounts_action:view_detailed_incomes":
        return await view_detailed_incomes(update, context)
    # FIM DOS NOVOS HANDLERS 👆
    elif data == "accounts_action:edit_account":
        return await edit_account_start(update, context)
    elif data == "accounts_action:mark_account":
        return await mark_account_start(update, context)
    elif data == "accounts_action:delete_account":
        return await delete_account_start(update, context)
    elif data == "accounts_action:delete_income":
        return await delete_income_start(update, context)
    elif data == "accounts_action:main_menu_from_finances": # Este é o callback do botão de voltar para o menu principal do bot
        # Se for o callback do botão "Voltar ao Menu Principal" (do bot, não das finanças)
        await query.edit_message_text("Voltando ao menu principal... ✅")
        context.user_data.clear() # Limpa os dados da conversa de finanças
        return ConversationHandler.END # Encerra o ConversationHandler de finanças

    elif data == "accounts_action:cancel": # Este é o cancelar genérico do flow de contas
        return await cancel_accounts_flow(update, context)
    
    logger.warning(f"Callback de contas não tratado: {data} por {query.from_user.id}")
    return VIEW_ACCOUNTS_MENU # Permanece no menu de contas se o callback não for tratado especificamente

# --- Fluxo de Adicionar Conta ---
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de adicionar uma nova conta."""
    user_id = update.effective_user.id
    context.user_data['current_account'] = {} # Inicializa dados da conta
    
    # Verifica se a chamada veio de um callback_query para editar a mensagem
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Ok! Qual é o **nome** da conta que você quer adicionar? (Ex: Aluguel, Luz, Cartão de Crédito) 📝")
    else: # Se a chamada veio de um comando ou mensagem direta
        await update.message.reply_text("Ok! Qual é o **nome** da conta que você quer adicionar? (Ex: Aluguel, Luz, Cartão de Crédito) 📝")
    
    logger.info(f"Iniciando adição de conta para {user_id}.")
    return ADD_ACCOUNT_NAME # <--- AVANÇA PARA O PRÓXIMO ESTADO

async def add_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome da conta e pede o valor."""
    user_id = update.effective_user.id
    account_name = update.message.text.strip()
    
    if not account_name:
        await update.message.reply_text("Por favor, digite um nome válido para a conta.")
        return ADD_ACCOUNT_NAME # Permanece no mesmo estado se o nome for inválido

    context.user_data['current_account']['name'] = account_name
    await update.message.reply_text(f"Certo, '{account_name}'. Agora, qual é o **valor** dessa conta? (Use números, ex: 150.75) 💰")
    logger.info(f"Nome da conta '{account_name}' recebido de {user_id}. Pedindo valor.")
    return ADD_ACCOUNT_AMOUNT # <--- AVANÇA PARA O PRÓXIMO ESTADO

async def add_account_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o valor da conta e pede a data de vencimento."""
    user_id = update.effective_user.id
    try:
        amount = float(update.message.text.replace(',', '.').strip())
        if amount <= 0:
            await update.message.reply_text("Por favor, digite um valor maior que zero para a conta.")
            return ADD_ACCOUNT_AMOUNT
        context.user_data['current_account']['amount'] = amount
        await update.message.reply_text(
            f"Valor de R$ {amount:.2f} registrado. Agora, qual é a **data de vencimento**? "
            f"(Formato: DD/MM/AAAA, ex: 15/07/2025) 📅" # Texto atualizado para o formato DD/MM/AAAA
        )
        logger.info(f"Valor da conta '{amount}' recebido de {user_id}. Pedindo data de vencimento.")
        return ADD_ACCOUNT_DUE_DATE # <--- AVANÇA PARA O PRÓXIMO ESTADO
    except ValueError:
        await update.message.reply_text("Ops! O valor inserido não é um número válido. Por favor, tente novamente (ex: 150.75).")
        return ADD_ACCOUNT_AMOUNT # Permanece no mesmo estado

async def add_account_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data de vencimento e pergunta sobre a recorrência."""
    user_id = update.effective_user.id
    due_date_str = update.message.text.strip()
    try:
        # Tenta parsear a data no formato DD/MM/AAAA
        parsed_date = datetime.datetime.strptime(due_date_str, '%d/%m/%Y').date()
        # Salva a data no formato AAAA-MM-DD para consistência no banco de dados
        context.user_data['current_account']['due_date'] = parsed_date.strftime('%Y-%m-%d')

        keyboard = [
            [InlineKeyboardButton("Mensal (Recorrente)", callback_data="recurrence:indefinite")],
            [InlineKeyboardButton("Parcelado (Ex: 3x, 6x)", callback_data="recurrence:fixed_parcel")],
            [InlineKeyboardButton("Única (Não Recorrente)", callback_data="recurrence:none")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Data de vencimento salva. Esta conta é... 🤔",
            reply_markup=reply_markup
        )
        logger.info(f"Data de vencimento '{due_date_str}' recebida de {user_id}. Pedindo recorrência.")
        return ADD_ACCOUNT_RECURRENCE # <--- AVANÇA PARA O PRÓXIMO ESTADO (AGUARDANDO UM CALLBACK)
    except ValueError:
        await update.message.reply_text("Formato de data inválido. Por favor, use DD/MM/AAAA (ex: 15/07/2025).")
        return ADD_ACCOUNT_DUE_DATE # Permanece no mesmo estado

async def add_account_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a recorrência da conta e finaliza ou pede número de parcelas."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    recurrence_data = query.data.split(':')
    recurrence_type = recurrence_data[1]

    context.user_data['current_account']['recurrence'] = recurrence_type

    if recurrence_type == 'fixed_parcel':
        await query.edit_message_text("Ok, conta parcelada! Quantas parcelas são no total? (Ex: 3, 6, 12) 🔢")
        logger.info(f"Recorrência 'parcelada' selecionada por {user_id}. Pedindo número de parcelas.")
        return ADD_ACCOUNT_PARCEL_COUNT # <--- AVANÇA PARA O ESTADO DE PARCELAS
    else:
        # Se não for parcelado, salva a conta imediatamente
        account_data = context.user_data['current_account']
        name = account_data['name']
        amount = account_data['amount']
        due_date = account_data['due_date']
        
        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence_type):
            await query.edit_message_text(f"🎉 Conta '{name}' (R$ {amount:.2f}, Vencimento: {datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m/%Y')}, Recorrência: {recurrence_type}) adicionada com sucesso!")
            logger.info(f"Conta '{name}' adicionada com sucesso para {user_id}.")
        else:
            await query.edit_message_text("❌ Ops! Não consegui adicionar sua conta. Talvez já exista uma conta com o mesmo nome e data de vencimento.")
            logger.warning(f"Falha ao adicionar conta '{name}' para {user_id}.")

        context.user_data.clear() # Limpa os dados da conversa
        return ConversationHandler.END # <--- FINALIZA A CONVERSA


async def add_account_parcel_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o número de parcelas e finaliza a adição da conta."""
    user_id = update.effective_user.id
    try:
        parcel_count = int(update.message.text.strip())
        if parcel_count <= 0:
            await update.message.reply_text("O número de parcelas deve ser um número inteiro positivo. Tente novamente.")
            return ADD_ACCOUNT_PARCEL_COUNT
        
        context.user_data['current_account']['parcel_count'] = parcel_count

        account_data = context.user_data['current_account']
        name = account_data['name']
        amount = account_data['amount']
        due_date = account_data['due_date']
        recurrence_type = account_data['recurrence']
        
        if accounts_db.add_monthly_account(user_id, name, amount, due_date, recurrence_type, parcel_count=parcel_count):
            await update.message.reply_text(
                f"🎉 Conta '{name}' (R$ {amount:.2f}, Vencimento: {datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m/%Y')}, "
                f"Parcelas: {parcel_count}) adicionada com sucesso!"
            )
            logger.info(f"Conta parcelada '{name}' adicionada com sucesso para {user_id}.")
        else:
            await update.message.reply_text("❌ Ops! Não consegui adicionar sua conta. Talvez já exista uma conta com o mesmo nome e data de vencimento.")
            logger.warning(f"Falha ao adicionar conta parcelada '{name}' para {user_id}.")

        context.user_data.clear()
        return ConversationHandler.END # <--- FINALIZA A CONVERSA
    except ValueError:
        await update.message.reply_text("Por favor, digite um número inteiro válido para as parcelas.")
        return ADD_ACCOUNT_PARCEL_COUNT # Permanece no mesmo estado

# --- Funções de Handler para Entradas Financeiras ---
async def add_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de adicionar uma nova entrada."""
    user_id = update.effective_user.id
    context.user_data['current_income'] = {}
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Ok! Qual é a **descrição** da sua entrada? (Ex: Salário, Venda de item) 💰")
    else:
        await update.message.reply_text("Ok! Qual é a **descrição** da sua entrada? (Ex: Salário, Venda de item) 💰")
    logger.info(f"Iniciando adição de entrada para {user_id}.")
    return ADD_INCOME_DESCRIPTION

async def add_income_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a descrição da entrada e pede o valor."""
    user_id = update.effective_user.id
    description = update.message.text.strip()
    if not description:
        await update.message.reply_text("Por favor, digite uma descrição válida para a entrada.")
        return ADD_INCOME_DESCRIPTION
    context.user_data['current_income']['description'] = description
    await update.message.reply_text(f"Certo, '{description}'. Agora, qual é o **valor** dessa entrada? (Use números, ex: 1000.50) 💲")
    logger.info(f"Descrição da entrada '{description}' recebida de {user_id}. Pedindo valor.")
    return ADD_INCOME_AMOUNT

async def add_income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o valor da entrada e pede a data."""
    user_id = update.effective_user.id
    try:
        amount = float(update.message.text.replace(',', '.').strip())
        if amount <= 0:
            await update.message.reply_text("Por favor, digite um valor maior que zero para a entrada.")
            return ADD_INCOME_AMOUNT
        context.user_data['current_income']['amount'] = amount
        await update.message.reply_text(
            f"Valor de R$ {amount:.2f} registrado. Agora, qual foi a **data** dessa entrada? "
            f"(Formato: DD/MM/AAAA, ex: 01/07/2025) 🗓️" # Texto atualizado para DD/MM/AAAA
        )
        logger.info(f"Valor da entrada '{amount}' recebido de {user_id}. Pedindo data.")
        return ADD_INCOME_DATE
    except ValueError:
        await update.message.reply_text("Ops! O valor inserido não é um número válido. Por favor, tente novamente (ex: 1000.50).")
        return ADD_INCOME_AMOUNT

async def add_income_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data da entrada e finaliza a adição."""
    user_id = update.effective_user.id
    income_date_str = update.message.text.strip()
    try:
        # Tenta parsear a data no formato DD/MM/AAAA
        parsed_date = datetime.datetime.strptime(income_date_str, '%d/%m/%Y').date()
        # Salva a data no formato AAAA-MM-DD para consistência no banco de dados
        context.user_data['current_income']['income_date'] = parsed_date.strftime('%Y-%m-%d')

        income_data = context.user_data['current_income']
        description = income_data['description']
        amount = income_data['amount']
        
        if accounts_db.add_financial_income(user_id, description, amount, context.user_data['current_income']['income_date']): # Usa a data já convertida
            await update.message.reply_text(f"🎉 Entrada '{description}' (R$ {amount:.2f}, Data: {income_date_str}) adicionada com sucesso!")
            logger.info(f"Entrada '{description}' adicionada com sucesso para {user_id}.")
        else:
            await update.message.reply_text("❌ Ops! Não consegui adicionar sua entrada.")
            logger.warning(f"Falha ao adicionar entrada '{description}' para {user_id}.")

        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Formato de data inválido. Por favor, use DD/MM/AAAA (ex: 01/07/2025).")
        return ADD_INCOME_DATE

# --- Funções de Edição de Conta ---

async def edit_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de edição de uma conta."""
    user_id = update.effective_user.id
    accounts = accounts_db.get_user_monthly_accounts(user_id)
    if not accounts:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Você não tem contas registradas para editar. Use '➕ Adicionar Conta' primeiro!")
        else:
            await update.message.reply_text("Você não tem contas registradas para editar. Use '➕ Adicionar Conta' primeiro!")
        return VIEW_ACCOUNTS_MENU # Retorna para o menu de contas

    message_text = "Selecione a conta para editar ou digite o ID: 👇\n\n"
    keyboard = []
    for account_id, name, amount, due_date_db, is_paid, recurrence, parcel_count, current_parcel in accounts:
        # Converte a data do DB (AAAA-MM-DD) para exibição (DD/MM/AAAA)
        due_date_display = datetime.datetime.strptime(due_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
        status = "✅ Paga" if is_paid else "❌ A Pagar"
        details = f"R$ {amount:.2f} | Venc: {due_date_display} | Rec: {recurrence}"
        if recurrence == 'fixed_parcel' and parcel_count:
            details += f" | {current_parcel}/{parcel_count} parcelas"
        
        message_text += f"**ID: {account_id}** - {name} ({details}) [{status}]\n"
        keyboard.append([InlineKeyboardButton(f"{name} (ID: {account_id})", callback_data=f"edit_account_id:{account_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    logger.info(f"Exibindo contas para edição para {user_id}.")
    return GET_ACCOUNT_ID_TO_EDIT # Avança para o estado de seleção de ID

async def get_account_id_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID da conta a ser editada e pede qual campo editar."""
    user_id = update.effective_user.id
    account_id = None
    response_target = update.callback_query or update.message

    if update.callback_query:
        await update.callback_query.answer()
        data = update.callback_query.data
        if data.startswith("edit_account_id:"):
            account_id = int(data.split(":")[1])
        elif data == "accounts_action:main_menu":
            return await accounts_menu(update, context) # Volta para o menu principal de finanças
    elif update.message:
        try:
            account_id = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Por favor, digite um ID numérico válido para a conta.")
            return GET_ACCOUNT_ID_TO_EDIT

    if account_id is None:
        return GET_ACCOUNT_ID_TO_EDIT # Não faça nada se o ID não foi obtido

    account = accounts_db.get_monthly_account_by_id(account_id, user_id)
    if not account:
        await response_target.reply_text("Conta não encontrada ou não pertence a você. Por favor, tente novamente.")
        return GET_ACCOUNT_ID_TO_EDIT
    
    context.user_data['editing_account_id'] = account_id
    context.user_data['current_account_data'] = {
        'id': account[0], 'name': account[1], 'amount': account[2], 
        'due_date': account[3], 'is_paid': bool(account[4]), 
        'recurrence': account[5], 'parcel_count': account[6], 'current_parcel': account[7]
    }

    keyboard = [
        [InlineKeyboardButton("Nome", callback_data="edit_field:name")],
        [InlineKeyboardButton("Valor", callback_data="edit_field:amount")],
        [InlineKeyboardButton("Data de Vencimento", callback_data="edit_field:due_date")],
        [InlineKeyboardButton("Recorrência", callback_data="edit_field:recurrence")],
    ]
    if account[5] == 'fixed_parcel': # Se for parcelado, permite editar parcelas
        keyboard.append([InlineKeyboardButton("Total de Parcelas", callback_data="edit_field:parcel_count")])
        keyboard.append([InlineKeyboardButton("Parcela Atual", callback_data="edit_field:current_parcel")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Usa edit_message_text se for um callback, senão reply_text
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"Ok, você selecionou a conta '{account[1]}'. Qual campo você gostaria de editar? ✍️",
            reply_markup=reply_markup,
            parse_mode='Markdown' # Garante que o Markdown seja interpretado
        )
    else:
        await update.message.reply_text(
            f"Ok, você selecionou a conta '{account[1]}'. Qual campo você gostaria de editar? ✍️",
            reply_markup=reply_markup,
            parse_mode='Markdown' # Garante que o Markdown seja interpretado
        )
    logger.info(f"Usuário {user_id} selecionou conta {account_id} para editar.")
    return EDIT_ACCOUNT_FIELD # Avança para o estado de seleção do campo


async def edit_account_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o campo a ser editado e pede o novo valor."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    field_to_edit = query.data.split(":")[1]
    
    context.user_data['field_to_edit'] = field_to_edit
    
    field_name_map = {
        'name': 'o **novo nome**',
        'amount': 'o **novo valor** (ex: 150.75)',
        'due_date': 'a **nova data de vencimento** (DD/MM/AAAA)', # Atualizado
        'recurrence': 'a **nova recorrência**',
        'parcel_count': 'o **novo total de parcelas**',
        'current_parcel': 'a **nova parcela atual**'
    }
    prompt = field_name_map.get(field_to_edit, 'o novo valor')

    if field_to_edit == 'recurrence':
        keyboard = [
            [InlineKeyboardButton("Mensal (Recorrente)", callback_data="new_value:indefinite")],
            [InlineKeyboardButton("Parcelado (Ex: 3x, 6x)", callback_data="new_value:fixed_parcel")],
            [InlineKeyboardButton("Única (Não Recorrente)", callback_data="new_value:none")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Qual é a {prompt} para esta conta? 🤔", reply_markup=reply_markup, parse_mode='Markdown')
        logger.info(f"Usuário {user_id} editando recorrência para conta {context.user_data['editing_account_id']}.")
        # Fica no mesmo estado, mas aguarda um callback com 'new_value'
        return EDIT_ACCOUNT_NEW_VALUE 
    else:
        await query.edit_message_text(f"Por favor, digite {prompt} para esta conta.", parse_mode='Markdown')
        logger.info(f"Usuário {user_id} editando campo '{field_to_edit}' para conta {context.user_data['editing_account_id']}.")
        return EDIT_ACCOUNT_NEW_VALUE


async def edit_account_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o novo valor do campo e atualiza a conta."""
    user_id = update.effective_user.id
    account_id = context.user_data.get('editing_account_id')
    field_to_edit = context.user_data.get('field_to_edit')
    
    new_value_raw = None # Valor bruto do input
    response_target = update.callback_query or update.message # Define o target para a resposta

    if update.message:
        new_value_raw = update.message.text.strip()
    elif update.callback_query:
        await update.callback_query.answer()
        data = update.callback_query.data
        if data.startswith("new_value:"):
            new_value_raw = data.split(":")[1]
        elif data == "accounts_action:main_menu":
            return await accounts_menu(update, context) # Permite voltar ao menu
    
    if new_value_raw is None:
        await response_target.reply_text("Valor inválido. Por favor, tente novamente.")
        return EDIT_ACCOUNT_NEW_VALUE # Permanece no estado

    new_value_for_db = new_value_raw # Valor a ser salvo no DB, pode ser convertido

    try:
        # Tenta converter o valor para o tipo correto, se necessário
        if field_to_edit == 'amount':
            new_value_for_db = float(new_value_raw.replace(',', '.'))
            if new_value_for_db <= 0:
                raise ValueError("Valor deve ser maior que zero.")
        elif field_to_edit in ['parcel_count', 'current_parcel']:
            new_value_for_db = int(new_value_raw)
            if new_value_for_db <= 0:
                raise ValueError("Número deve ser positivo.")
        elif field_to_edit == 'due_date':
            # Converte DD/MM/AAAA para AAAA-MM-DD para salvar no DB
            parsed_date = datetime.datetime.strptime(new_value_raw, '%d/%m/%Y').date()
            new_value_for_db = parsed_date.strftime('%Y-%m-%d')

        if accounts_db.update_monthly_account(account_id, user_id, **{field_to_edit: new_value_for_db}): # Usa new_value_for_db
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    f"✅ Campo '{field_to_edit}' da conta ID {account_id} atualizado para '{new_value_raw}' com sucesso!.", # Exibe o valor original para o user
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"✅ Campo '{field_to_edit}' da conta ID {account_id} atualizado para '{new_value_raw}' com sucesso!.", # Exibe o valor original para o user
                    parse_mode='Markdown'
                )
            logger.info(f"Campo '{field_to_edit}' da conta ID {account_id} atualizado para '{new_value_for_db}' (input: '{new_value_raw}') por {user_id}.")
        else:
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ Ops! Não consegui atualizar a conta.")
            else:
                await update.message.reply_text("❌ Ops! Não consegui atualizar a conta.")
            logger.warning(f"Falha ao atualizar campo '{field_to_edit}' da conta ID {account_id} para {new_value_for_db} por {user_id}.")

    except ValueError as e:
        error_msg = f"Erro no formato: {e}. Por favor, tente novamente com o formato correto."
        if field_to_edit == 'due_date':
            error_msg = "Formato de data inválido. Por favor, use DD/MM/AAAA (ex: 15/07/2025)."
        elif field_to_edit == 'amount':
            error_msg = "Valor inválido. Por favor, use números (ex: 150.75)."
        elif field_to_edit in ['parcel_count', 'current_parcel']:
            error_msg = "Número inválido. Por favor, use um número inteiro positivo."

        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return EDIT_ACCOUNT_NEW_VALUE
    except Exception as e:
        if update.callback_query:
            await update.callback_query.edit_message_text(f"Ocorreu um erro inesperado: {e}")
        else:
            await update.message.reply_text(f"Ocorreu um erro inesperado: {e}")
        logger.error(f"Erro inesperado ao editar conta: {e}")

    context.user_data.clear()
    return ConversationHandler.END # Finaliza a conversa de edição

# --- Fluxo de Marcar Conta como Paga ---
async def mark_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de marcar/desmarcar uma conta como paga."""
    user_id = update.effective_user.id
    accounts = accounts_db.get_user_monthly_accounts(user_id)
    if not accounts:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Você não tem contas registradas para marcar. Use '➕ Adicionar Conta' primeiro!")
        else:
            await update.message.reply_text("Você não tem contas registradas para marcar. Use '➕ Adicionar Conta' primeiro!")
        return VIEW_ACCOUNTS_MENU

    message_text = "Selecione a conta para marcar/desmarcar como paga ou digite o ID: 👇\n\n"
    keyboard = []
    for account_id, name, amount, due_date_db, is_paid, recurrence, parcel_count, current_parcel in accounts:
        # Converte a data do DB (AAAA-MM-DD) para exibição (DD/MM/AAAA)
        due_date_display = datetime.datetime.strptime(due_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
        status = "✅ Paga" if is_paid else "❌ A Pagar"
        details = f"R$ {amount:.2f} | Venc: {due_date_display} | Rec: {recurrence}"
        if recurrence == 'fixed_parcel' and parcel_count:
            details += f" | {current_parcel}/{parcel_count} parcelas"
        
        message_text += f"**ID: {account_id}** - {name} ({details}) [{status}]\n"
        keyboard.append([InlineKeyboardButton(f"{name} (ID: {account_id})", callback_data=f"mark_account_id:{account_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    logger.info(f"Exibindo contas para marcar/desmarcar para {user_id}.")
    return GET_ACCOUNT_ID_TO_MARK

async def mark_account_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID da conta e alterna o status de pagamento."""
    user_id = update.effective_user.id
    account_id = None
    response_target = update.callback_query or update.message

    if update.callback_query:
        await update.callback_query.answer()
        data = update.callback_query.data
        if data.startswith("mark_account_id:"):
            account_id = int(data.split(":")[1])
        elif data == "accounts_action:main_menu":
            return await accounts_menu(update, context) # Volta para o menu principal
    elif update.message:
        try:
            account_id = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Por favor, digite um ID numérico válido para a conta.")
            return GET_ACCOUNT_ID_TO_MARK

    if account_id is None:
        return GET_ACCOUNT_ID_TO_MARK

    account = accounts_db.get_monthly_account_by_id(account_id, user_id)
    if not account:
        await response_target.reply_text("Conta não encontrada ou não pertence a você. Por favor, tente novamente.")
        return GET_ACCOUNT_ID_TO_MARK
    
    current_status = bool(account[4])
    new_status = not current_status # Inverte o status

    if accounts_db.update_monthly_account_status(account_id, user_id, new_status):
        status_text = "PAGA" if new_status else "A PAGAR"
        if update.callback_query:
            await update.callback_query.edit_message_text(
                f"✅ Status da conta '{account[1]}' (ID: {account_id}) alterado para **{status_text}**!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"✅ Status da conta '{account[1]}' (ID: {account_id}) alterado para **{status_text}**!",
                parse_mode='Markdown'
            )
        logger.info(f"Status da conta ID {account_id} alterado para {status_text} por {user_id}.")
    else:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ Ops! Não consegui alterar o status da conta.")
        else:
            await update.message.reply_text("❌ Ops! Não consegui alterar o status da conta.")
        logger.warning(f"Falha ao alterar status da conta ID {account_id} para {new_status} por {user_id}.")

    context.user_data.clear()
    return ConversationHandler.END # Finaliza a conversa de marcar

# --- Fluxo de Apagar Conta ---
async def delete_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de apagar uma conta."""
    user_id = update.effective_user.id
    accounts = accounts_db.get_user_monthly_accounts(user_id)
    if not accounts:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Você não tem contas registradas para apagar.")
        else:
            await update.message.reply_text("Você não tem contas registradas para apagar.")
        return VIEW_ACCOUNTS_MENU

    message_text = "Selecione a conta para apagar ou digite o ID: 👇\n\n"
    keyboard = []
    for account_id, name, amount, due_date_db, is_paid, recurrence, parcel_count, current_parcel in accounts:
        # Converte a data do DB (AAAA-MM-DD) para exibição (DD/MM/AAAA)
        due_date_display = datetime.datetime.strptime(due_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
        status = "✅ Paga" if is_paid else "❌ A Pagar"
        details = f"R$ {amount:.2f} | Venc: {due_date_display} | Rec: {recurrence}"
        if recurrence == 'fixed_parcel' and parcel_count:
            details += f" | {current_parcel}/{parcel_count} parcelas"
        
        message_text += f"**ID: {account_id}** - {name} ({details}) [{status}]\n"
        keyboard.append([InlineKeyboardButton(f"{name} (ID: {account_id})", callback_data=f"delete_account_id:{account_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    logger.info(f"Exibindo contas para apagar para {user_id}.")
    return GET_ACCOUNT_ID_TO_DELETE

async def delete_selected_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID da conta a ser apagada e a deleta."""
    user_id = update.effective_user.id
    account_id = None
    response_target = update.callback_query or update.message

    if update.callback_query:
        await update.callback_query.answer()
        data = update.callback_query.data
        if data.startswith("delete_account_id:"):
            account_id = int(data.split(":")[1])
        elif data == "accounts_action:main_menu":
            return await accounts_menu(update, context) # Volta para o menu principal
    elif update.message:
        try:
            account_id = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Por favor, digite um ID numérico válido para a conta.")
            return GET_ACCOUNT_ID_TO_DELETE

    if account_id is None:
        return GET_ACCOUNT_ID_TO_DELETE

    if accounts_db.delete_monthly_account(account_id, user_id):
        if update.callback_query:
            await update.callback_query.edit_message_text(f"🗑️ Conta ID **{account_id}** apagada com sucesso!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"🗑️ Conta ID **{account_id}** apagada com sucesso!", parse_mode='Markdown')
        logger.info(f"Conta ID {account_id} deletada por {user_id}.")
    else:
        if update.callback_query:
            await update.callback_query.edit_message_text(f"❌ Não foi possível apagar a conta ID **{account_id}**. Verifique se o ID está correto.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Não foi possível apagar a conta ID **{account_id}**. Verifique se o ID está correto.", parse_mode='Markdown')
        logger.warning(f"Falha ao apagar conta ID {account_id} por {user_id}.")

    context.user_data.clear()
    return ConversationHandler.END # Finaliza a conversa de apagar

# --- Fluxo de Apagar Entrada ---
async def delete_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de apagar uma entrada."""
    user_id = update.effective_user.id
    incomes = accounts_db.get_user_financial_incomes(user_id)
    if not incomes:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Você não tem entradas registradas para apagar.")
        else:
            await update.message.reply_text("Você não tem entradas registradas para apagar.")
        return VIEW_ACCOUNTS_MENU

    message_text = "Selecione a entrada para apagar ou digite o ID: 👇\n\n"
    keyboard = []
    for income_id, description, amount, income_date_db in incomes:
        # Converte a data do DB (AAAA-MM-DD) para exibição (DD/MM/AAAA)
        income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
        message_text += f"**ID: {income_id}** - {description} (R$ {amount:.2f} | Data: {income_date_display})\n"
        keyboard.append([InlineKeyboardButton(f"{description} (ID: {income_id})", callback_data=f"delete_income_id:{income_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    logger.info(f"Exibindo entradas para apagar para {user_id}.")
    return GET_INCOME_ID_TO_DELETE

async def delete_selected_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o ID da entrada a ser apagada e a deleta."""
    user_id = update.effective_user.id
    income_id = None
    response_target = update.callback_query or update.message

    if update.callback_query:
        await update.callback_query.answer()
        data = update.callback_query.data
        if data.startswith("delete_income_id:"):
            income_id = int(data.split(":")[1])
        elif data == "accounts_action:main_menu":
            return await accounts_menu(update, context) # Volta para o menu principal
    elif update.message:
        try:
            income_id = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Por favor, digite um ID numérico válido para a entrada.")
            return GET_INCOME_ID_TO_DELETE

    if income_id is None:
        return GET_INCOME_ID_TO_DELETE

    if accounts_db.delete_financial_income(income_id, user_id):
        if update.callback_query:
            await update.callback_query.edit_message_text(f"🗑️ Entrada ID **{income_id}** apagada com sucesso!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"🗑️ Entrada ID **{income_id}** apagada com sucesso!", parse_mode='Markdown')
        logger.info(f"Entrada ID {income_id} deletada por {user_id}.")
    else:
        if update.callback_query:
            await update.callback_query.edit_message_text(f"❌ Não foi possível apagar a entrada ID **{income_id}**. Verifique se o ID está correto.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Não foi possível apagar a entrada ID **{income_id}**. Verifique se o ID está correto.", parse_mode='Markdown')
        logger.warning(f"Falha ao apagar entrada ID {income_id} por {user_id}.")

    context.user_data.clear()
    return ConversationHandler.END

# --- Resumo Mensal ---

async def view_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe um resumo financeiro mensal."""
    user_id = update.effective_user.id
    today = datetime.date.today()
    summary = accounts_db.get_monthly_summary(user_id, today.year, today.month)

    total_incomes = summary['total_incomes']
    total_accounts = summary['total_accounts_due_this_month']
    paid_accounts = summary['paid_accounts_this_month']
    unpaid_accounts = summary['unpaid_accounts_this_month']
    balance = summary['balance']

    message_text = (
        f"**📊 Resumo Financeiro de {today.strftime('%B de %Y')}**\n\n"
        f"➡️ Total de Entradas: R$ {total_incomes:.2f}\n"
        f"➡️ Total de Contas (ativas no mês): R$ {total_accounts:.2f}\n"
        f"   ✅ Contas Pagas: R$ {paid_accounts:.2f}\n"
        f"   ❌ Contas a Pagar: R$ {unpaid_accounts:.2f}\n\n"
        f"**Saldo Atual (Entradas - Total Contas Ativas): R$ {balance:.2f}**\n\n" # Texto ajustado aqui
        f"Use as opções abaixo para mais detalhes!" # Texto ajustado
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    return VIEW_ACCOUNTS_MENU # Retorna para o estado do menu de contas


# --- NOVAS FUNÇÕES PARA VISUALIZAR DETALHES ---

async def view_detailed_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exibe uma lista detalhada de todas as contas do usuário."""
    user_id = update.effective_user.id
    accounts = accounts_db.get_user_monthly_accounts(user_id)

    if not accounts:
        message_text = "Você não tem nenhuma conta registrada. Que tal adicionar uma? 😉"
    else:
        message_text = "**📋 Suas Contas Registradas:**\n\n"
        for account_id, name, amount, due_date_db, is_paid, recurrence, parcel_count, current_parcel in accounts:
            due_date_display = datetime.datetime.strptime(due_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
            status = "✅ Paga" if is_paid else "❌ A Pagar"
            details = f"R$ {amount:.2f} | Venc: {due_date_display} | Rec: {recurrence}"
            if recurrence == 'fixed_parcel' and parcel_count:
                details += f" | {current_parcel}/{parcel_count} parcelas"
            
            message_text += f"**ID: {account_id}** - {name}\n  `{details}` [{status}]\n\n"
    
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
    """Exibe uma lista detalhada de todas as entradas financeiras do usuário."""
    user_id = update.effective_user.id
    incomes = accounts_db.get_user_financial_incomes(user_id)

    if not incomes:
        message_text = "Você não tem nenhuma entrada registrada. Que tal adicionar uma? 😉"
    else:
        message_text = "**💸 Suas Entradas Registradas:**\n\n"
        for income_id, description, amount, income_date_db in incomes:
            income_date_display = datetime.datetime.strptime(income_date_db, '%Y-%m-%d').strftime('%d/%m/%Y')
            message_text += f"**ID: {income_id}** - {description}\n  `R$ {amount:.2f} | Data: {income_date_display}`\n\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu de Contas", callback_data="accounts_action:main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    logger.info(f"Entradas detalhadas exibidas para {user_id}.")
    return VIEW_ACCOUNTS_MENU # Retorna ao menu de contas

# --- Função de Cancelamento ---

async def cancel_accounts_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela o fluxo atual de contas financeiras."""
    # Garante que a resposta seja enviada para a origem correta
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Operação de contas cancelada. ✅")
    elif update.message:
        await update.message.reply_text("Operação de contas cancelada. ✅")
    
    context.user_data.clear() # Limpa dados da conversa
    logger.info(f"Fluxo de contas cancelado por {update.effective_user.id}.")
    return ConversationHandler.END