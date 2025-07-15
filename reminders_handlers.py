# reminders_handlers.py

import logging
import datetime
from datetime import timedelta
from dateutil import parser # Mantido caso ainda queira o parsing de texto como fallback ou para a "fuzzy"
import pytz
import re 
import calendar # Adicionado para construir o calendário

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler, JobQueue, Application
from telegram.constants import ParseMode 

import db
import handlers # Importado para chamar send_main_help_menu e cancel_dialog

logger = logging.getLogger(__name__)

# Estados para ConversationHandler (valores altos para evitar conflitos)
GETTING_REMINDER_DESC = 300
GETTING_REMINDER_DATETIME = 301 # Este estado agora iniciará o fluxo de calendário/hora
GETTING_REMINDER_RECURRENCE = 302
GETTING_REMINDER_ID_FOR_DELETE = 303 

# NOVOS ESTADOS PARA SELEÇÃO DE DATA/HORA
GETTING_REMINDER_DATE_FROM_CALENDAR = 307
GETTING_REMINDER_HOUR = 308
GETTING_REMINDER_MINUTE = 309


# NOVOS ESTADOS PARA FOLLOW-UP MENUS
AWAIT_REMINDER_ADD_ACTION = 304
AWAIT_REMINDER_VIEW_ACTION = 305
AWAIT_REMINDER_DELETE_ACTION = 306

# Fuso horário padrão do bot (pode ser ajustado se o usuário tiver uma configuração diferente)
DEFAULT_TIMEZONE = pytz.timezone('America/Sao_Paulo')

# --- Função Auxiliar para Enviar/Editar Mensagens no reminders_handlers ---
async def _send_or_edit_reminder_message(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = ParseMode.HTML):
    """
    Envia uma nova mensagem ou edita uma existente, dependendo da origem da atualização.
    Adaptado para o contexto de lembretes.
    """
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logger.warning(f"Erro ao editar mensagem via callback no reminders_handlers: {e}. Enviando nova mensagem.")
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    elif update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)


# --- Funções Auxiliares para Lembretes ---

def calculate_next_occurrence(current_scheduled_time: datetime.datetime, recurrence: str) -> datetime.datetime | None:
    """Calcula a próxima data/hora para um lembrete recorrente, garantindo que seja no futuro."""
    if current_scheduled_time.tzinfo is None:
        logger.error("calculate_next_occurrence: current_scheduled_time não possui informações de fuso horário. Localizando como UTC.")
        current_scheduled_time = pytz.utc.localize(current_scheduled_time)

    next_time = current_scheduled_time

    if recurrence == 'daily':
        next_time = current_scheduled_time + timedelta(days=1)
    elif recurrence == 'weekly':
        next_time = current_scheduled_time + timedelta(weeks=1)
    elif recurrence == 'monthly':
        try:
            next_time = current_scheduled_time.replace(month=current_scheduled_time.month % 12 + 1)
        except ValueError:
            next_month = current_scheduled_time.month % 12 + 1
            next_year = current_scheduled_time.year + (1 if next_month == 1 else 0)
            next_time = current_scheduled_time.replace(year=next_year, month=next_month, day=1) + timedelta(days=-1)
    elif recurrence == 'yearly':
        next_time = current_scheduled_time.replace(year=current_scheduled_time.year + 1)
    elif recurrence == 'none':
        return None
    else:
        logger.warning(f"Recorrência desconhecida: {recurrence}")
        return None

    now = datetime.datetime.now(current_scheduled_time.tzinfo)
    while next_time <= now:
        if recurrence == 'daily':
            next_time += timedelta(days=1)
        elif recurrence == 'weekly':
            next_time += timedelta(weeks=1)
        elif recurrence == 'monthly':
            try:
                next_time = next_time.replace(month=next_time.month % 12 + 1)
            except ValueError:
                next_month = next_time.month % 12 + 1
                next_year = next_time.year + (1 if next_month == 1 else 0)
                next_time = next_time.replace(year=next_month, day=1) + timedelta(days=-1) 
        elif recurrence == 'yearly':
            next_time = next_time.replace(year=next_time.year + 1)
        else:
            break
    
    return next_time


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Função que será executada pelo JobQueue para enviar o lembrete."""
    job = context.job
    reminder_data = job.data
    user_id = reminder_data['user_id']
    description = reminder_data['description']
    reminder_id = reminder_data['id']
    recurrence = reminder_data['recurrence']
    
    bot: Bot = context.bot

    try:
        await bot.send_message(user_id, f"🔔 Lembrete: <b>{description}</b>", parse_mode=ParseMode.HTML)
        logger.info(f"Lembrete '{description}' (ID: {reminder_id}) enviado para user {user_id}.")

        if recurrence != 'none':
            next_scheduled_time = calculate_next_occurrence(job.next_run_time, recurrence)
            if next_scheduled_time:
                new_job = context.job_queue.run_once(
                    send_reminder,
                    next_scheduled_time,
                    data=reminder_data,
                    name=str(reminder_id)
                )
                db.update_reminder_scheduled_time(reminder_id, next_scheduled_time, str(reminder_id))
                logger.info(f"Lembrete '{description}' (ID: {reminder_id}) reagendado para {next_scheduled_time}.")
            else:
                db.deactivate_reminder(reminder_id)
                logger.info(f"Lembrete '{description}' (ID: {reminder_id}) desativado após última ocorrência.")
        else:
            db.deactivate_reminder(reminder_id)
            logger.info(f"Lembrete '{description}' (ID: {reminder_id}) desativado.")
            
    except Exception as e:
        logger.error(f"Erro ao enviar/reagendar lembrete ID {reminder_id} para user {user_id}: {e}")


def schedule_existing_reminders(application: Application):
    """Agenda lembretes que estão no banco de dados ao iniciar o bot."""
    logger.info("Agendando lembretes existentes...")
    job_queue = application.job_queue
    
    active_reminders = db.get_active_reminders()
    for reminder in active_reminders:
        reminder_id = reminder['id']
        user_id = reminder['user_id']
        description = reminder['description']
        scheduled_time = reminder['scheduled_time']
        recurrence = reminder['recurrence']

        if scheduled_time.tzinfo is None:
            scheduled_time = DEFAULT_TIMEZONE.localize(scheduled_time)
        else:
            scheduled_time = scheduled_time.astimezone(DEFAULT_TIMEZONE)

        now = datetime.datetime.now(DEFAULT_TIMEZONE)
        if scheduled_time <= now:
            scheduled_time = calculate_next_occurrence(scheduled_time, recurrence)
            if not scheduled_time:
                db.deactivate_reminder(reminder_id)
                logger.info(f"Lembrete ID {reminder_id} no passado e não recurrente. Desativado.")
                continue

        existing_jobs = job_queue.get_jobs_by_name(str(reminder_id))
        if existing_jobs:
            logger.info(f"Job existente para lembrete ID {reminder_id} encontrado. Removendo para reagendar.")
            for job in existing_jobs:
                job.schedule_removal()

        job_data = {
            'id': reminder_id,
            'user_id': user_id,
            'description': description,
            'recurrence': recurrence,
        }
        
        new_job = job_queue.run_once(
            send_reminder,
            scheduled_time,
            data=job_data,
            name=str(reminder_id)
        )
        db.update_reminder_scheduled_time(reminder_id, scheduled_time, str(reminder_id))
        logger.info(f"Lembrete '{description}' (ID: {reminder_id}) reagendado com sucesso para {scheduled_time}.")
    logger.info("Agendamento de lembretes concluído.")

# --- Handlers para Lembretes ---

async def add_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar um novo lembrete."""
    user_id = update.effective_user.id
    logger.info(f"Comando /add_lembrete recebido de {user_id}.")
    await _send_or_edit_reminder_message(update, "Qual é o lembrete? (ex: Pagar a conta de luz)", parse_mode=ParseMode.HTML) 
    return GETTING_REMINDER_DESC

async def get_reminder_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a descrição do lembrete."""
    context.user_data['reminder_description'] = update.message.text.strip()
    if not context.user_data['reminder_description']:
        await update.message.reply_text("A descrição do lembrete não pode ser vazia. Por favor, tente novamente.", parse_mode=ParseMode.HTML)
        return GETTING_REMINDER_DESC
    
    # Após a descrição, vai para a seleção de data via calendário
    return await send_calendar_for_reminder(update, context)


# --- Funções e Handlers para Seleção de Data/Hora (Calendar & Time Picker) ---

def _create_calendar_keyboard_reminders(year: int, month: int) -> InlineKeyboardMarkup:
    """Cria um InlineKeyboardMarkup para um calendário de lembretes."""
    keyboard = []
    # Cabeçalho: Mês e Ano
    keyboard.append([
        InlineKeyboardButton("«", callback_data=f"rem_cal:nav:{year-1}:{month}"), # Ano anterior
        InlineKeyboardButton("<", callback_data=f"rem_cal:nav:{year}:{month-1 if month > 1 else 12}"), # Mês anterior
        InlineKeyboardButton(f"{calendar.month_name[month]} {year}", callback_data="rem_cal:ignore"), # Mês e ano (não clicável)
        InlineKeyboardButton(">", callback_data=f"rem_cal:nav:{year}:{month+1 if month < 12 else 1}"), # Próximo mês
        InlineKeyboardButton("»", callback_data=f"rem_cal:nav:{year+1}:{month}") # Próximo ano
    ])

    # Dias da semana
    week_days = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    keyboard.append([InlineKeyboardButton(day, callback_data="rem_cal:ignore") for day in week_days])

    # Dias do mês
    cal = calendar.Calendar(firstweekday=6) # 6 = domingo como primeiro dia da semana
    for week in cal.monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="rem_cal:ignore")) # Dias vazios
            else:
                row.append(InlineKeyboardButton(str(day), callback_data=f"rem_cal:date:{year}:{month}:{day}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_reminder_add")]) # Usa o cancelar da adição
    return InlineKeyboardMarkup(keyboard)

async def send_calendar_for_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Envia ou edita a mensagem do calendário para o lembrete."""
    current_date = datetime.datetime.now(DEFAULT_TIMEZONE)
    year = context.user_data.get('rem_cal_year', current_date.year)
    month = context.user_data.get('rem_cal_month', current_date.month)

    keyboard = _create_calendar_keyboard_reminders(year, month)
    text = "🗓️ Selecione a data do lembrete:"

    await _send_or_edit_reminder_message(update, text, keyboard, parse_mode=ParseMode.HTML)
    
    return GETTING_REMINDER_DATE_FROM_CALENDAR

async def handle_calendar_callback_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com os callbacks dos botões do calendário para lembretes."""
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split(':')
    action = data_parts[1]
    
    if action == "date":
        year = int(data_parts[2])
        month = int(data_parts[3])
        day = int(data_parts[4])
        
        selected_date = datetime.date(year, month, day)
        context.user_data['selected_reminder_date'] = selected_date.strftime('%Y-%m-%d')
        
        # Após a data, vai para a seleção da hora
        return await send_hour_picker_for_reminder(update, context)

    elif action == "nav":
        year = int(data_parts[2])
        month = int(data_parts[3])

        context.user_data['rem_cal_year'] = year
        context.user_data['rem_cal_month'] = month

        keyboard = _create_calendar_keyboard_reminders(year, month)
        text = "🗓️ Selecione a data do lembrete:"
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return GETTING_REMINDER_DATE_FROM_CALENDAR

    elif action == "ignore": # Clicou em mês/ano ou dia da semana
        return GETTING_REMINDER_DATE_FROM_CALENDAR 

    # O "cancel_reminder_add" é tratado diretamente no ConversationHandler

    return GETTING_REMINDER_DATE_FROM_CALENDAR

async def send_hour_picker_for_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Envia um teclado inline para seleção de hora."""
    keyboard = []
    for hour in range(24):
        keyboard.append(InlineKeyboardButton(f"{hour:02d}h", callback_data=f"rem_hour:{hour:02d}"))
    
    # Organiza em 4 colunas
    organized_keyboard = [keyboard[i:i + 4] for i in range(0, len(keyboard), 4)]
    
    organized_keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_reminder_add")])
    reply_markup = InlineKeyboardMarkup(organized_keyboard)

    selected_date_str = context.user_data['selected_reminder_date']
    display_date = datetime.datetime.strptime(selected_date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    text = f"📅 Data selecionada: <b>{display_date}</b>\n\nAgora, selecione a hora do lembrete:"
    await _send_or_edit_reminder_message(update, text, reply_markup, parse_mode=ParseMode.HTML)
    
    return GETTING_REMINDER_HOUR

async def get_reminder_hour(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a hora selecionada e avança para a seleção de minuto."""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split(':')
    action = data_parts[0]

    if action == "cancel_reminder_add": # Se clicou em cancelar
        return await handlers.cancel_dialog(update, context)

    if action == "rem_hour":
        selected_hour = int(data_parts[1])
        context.user_data['selected_reminder_hour'] = selected_hour
        return await send_minute_picker_for_reminder(update, context)
    
    return GETTING_REMINDER_HOUR

async def send_minute_picker_for_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Envia um teclado inline para seleção de minuto (intervalos de 5 minutos)."""
    keyboard = []
    for minute in range(0, 60, 5): # 0, 5, 10, ..., 55
        keyboard.append(InlineKeyboardButton(f"{minute:02d}min", callback_data=f"rem_minute:{minute:02d}"))
    
    organized_keyboard = [keyboard[i:i + 4] for i in range(0, len(keyboard), 4)]
    
    organized_keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_reminder_add")])
    reply_markup = InlineKeyboardMarkup(organized_keyboard)

    selected_date_str = context.user_data['selected_reminder_date']
    selected_hour = context.user_data['selected_reminder_hour']
    
    display_date = datetime.datetime.strptime(selected_date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    text = f"📅 Data: <b>{display_date}</b>\n⏰ Hora selecionada: <b>{selected_hour:02d}h</b>\n\nAgora, selecione o minuto do lembrete:"
    await _send_or_edit_reminder_message(update, text, reply_markup, parse_mode=ParseMode.HTML)
    
    return GETTING_REMINDER_MINUTE

async def get_reminder_minute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o minuto selecionado e finaliza a construção da data/hora."""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split(':')
    action = data_parts[0]

    if action == "cancel_reminder_add": 
        return await handlers.cancel_dialog(update, context)

    if action == "rem_minute":
        selected_minute = int(data_parts[1])
        context.user_data['selected_reminder_minute'] = selected_minute

        selected_date_str = context.user_data['selected_reminder_date']
        selected_hour = context.user_data['selected_reminder_hour']
        selected_minute = context.user_data['selected_reminder_minute']
        
        # Constrói o objeto datetime final
        final_datetime_str = f"{selected_date_str} {selected_hour:02d}:{selected_minute:02d}:00"
        
        try:
            scheduled_time = parser.parse(final_datetime_str)
            scheduled_time = DEFAULT_TIMEZONE.localize(scheduled_time) # Localiza com o fuso horário padrão
            
            now = datetime.datetime.now(DEFAULT_TIMEZONE)
            if scheduled_time <= now:
                # Se a data/hora final estiver no passado, ajusta para o dia seguinte
                scheduled_time += timedelta(days=1)
                await _send_or_edit_reminder_message(update, "A data e hora selecionadas já passaram. O lembrete será agendado para o mesmo horário no dia seguinte.", parse_mode=ParseMode.HTML)

            context.user_data['scheduled_time'] = scheduled_time
            
            # Prossegue para a seleção de recorrência
            keyboard = [
                [InlineKeyboardButton("Sem Recorrência", callback_data="none")],
                [InlineKeyboardButton("Diariamente", callback_data="daily")],
                [InlineKeyboardButton("Semanalmente", callback_data="weekly")],
                [InlineKeyboardButton("Mensalmente", callback_data="monthly")],
                [InlineKeyboardButton("Anualmente", callback_data="yearly")],
                [InlineKeyboardButton("Cancelar", callback_data="cancel_reminder_add")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await _send_or_edit_reminder_message(
                update,
                f"Data e hora do lembrete: <b>{scheduled_time.strftime('%d/%m/%Y %H:%M')}</b>\n\nCom que frequência você quer que este lembrete se repita?",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            
            # Limpa os dados temporários de seleção de data/hora
            context.user_data.pop('selected_reminder_date', None)
            context.user_data.pop('selected_reminder_hour', None)
            context.user_data.pop('selected_reminder_minute', None)
            context.user_data.pop('rem_cal_year', None)
            context.user_data.pop('rem_cal_month', None)

            return GETTING_REMINDER_RECURRENCE

        except ValueError:
            await _send_or_edit_reminder_message(update, "Erro ao processar a data/hora selecionada. Por favor, tente novamente.", parse_mode=ParseMode.HTML)
            return await send_calendar_for_reminder(update, context) # Volta para o início da seleção de data
    
    return GETTING_REMINDER_MINUTE # Permanece no estado atual se não for um clique de minuto válido


# O restante dos handlers (get_reminder_recurrence, handle_add_reminder_action, view_reminders,
# handle_view_reminder_action, delete_reminder_start, delete_reminder_confirm, handle_delete_reminder_action)
# permanece inalterado em sua lógica de follow-up, mas pode ter tido algumas chamadas atualizadas
# para _send_or_edit_reminder_message quando necessário.


async def get_reminder_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frequência de recorrência e salva o lembrete."""
    query = update.callback_query
    await query.answer()
    recurrence = query.data

    if recurrence == "cancel_reminder_add":
        return await handlers.cancel_dialog(update, context) 

    description = context.user_data['reminder_description']
    scheduled_time = context.user_data['scheduled_time']
    user_id = query.from_user.id

    reminder_id = db.add_reminder(user_id, description, scheduled_time, recurrence)

    if reminder_id:
        job_data = {
            'id': reminder_id,
            'user_id': user_id,
            'description': description,
            'recurrence': recurrence,
        }
        
        job = context.job_queue.run_once(
            send_reminder,
            scheduled_time,
            data=job_data,
            name=str(reminder_id)
        )
        db.update_reminder_scheduled_time(reminder_id, scheduled_time, str(reminder_id))

        await _send_or_edit_reminder_message( 
            update,
            f"🎉 Lembrete adicionado!\n<b>{description}</b> em {scheduled_time.strftime('%d/%m/%Y %H:%M')}\nRecorrência: {recurrence.capitalize()}", 
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Lembrete '{description}' adicionado e agendado por {user_id} para {scheduled_time} com recorrência {recurrence}.")
        
        keyboard = [
            [InlineKeyboardButton("➕ Adicionar Outro Lembrete", callback_data="reminder_add_action:add_another")],
            [InlineKeyboardButton("📚 Ver Meus Lembretes", callback_data="reminder_add_action:view_all")],
            [InlineKeyboardButton("↩️ Voltar ao Menu de Lembretes", callback_data="reminder_add_action:main_menu")],
            [InlineKeyboardButton("🏠 Voltar ao Menu Principal", callback_data="help_category:main_menu")],
            [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else: 
            await update.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        
        context.user_data.clear() 
        return AWAIT_REMINDER_ADD_ACTION 

    else:
        await _send_or_edit_reminder_message( 
            update,
            "❌ Ops! Não foi possível adicionar o lembrete. Por favor, tente novamente.", 
            parse_mode=ParseMode.HTML
        )
        logger.warning(f"Falha ao adicionar lembrete '{description}' para {user_id}.")
        context.user_data.clear()
        return ConversationHandler.END


async def handle_add_reminder_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com as opções do menu de follow-up após adicionar um lembrete."""
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "reminder_add_action:add_another":
        return await add_reminder_start(update, context)
    elif action == "reminder_add_action:view_all":
        return await view_reminders(update, context) 
    elif action == "reminder_add_action:main_menu":
        await handlers.reminders_menu(update, context) 
        return ConversationHandler.END 
    elif action == "help_category:main_menu": 
        await handlers.send_main_help_menu(update, context)
        return ConversationHandler.END
    elif action == "cancel_dialog_action":
        await handlers.cancel_dialog(update, context)
        return ConversationHandler.END
    
    return ConversationHandler.END


async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: 
    """Vê todos os lembretes do usuário (ativos e inativos)."""
    user_id = update.effective_user.id
    reminders = db.get_user_reminders(user_id)
    if reminders:
        message_text = "⏰ <b>Seus Lembretes:</b>\n\n" 
        for r in reminders:
            status = "✅ Ativo" if r['active'] else "❌ Inativo"
            display_time = r['scheduled_time'].astimezone(DEFAULT_TIMEZONE).strftime('%d/%m/%Y %H:%M')
            recurrence_display = r['recurrence'].capitalize()
            
            message_text += f"<b>ID</b>: <code>{r['id']}</code>\n" \
                            f"<b>Descrição</b>: {r['description']}\n" \
                            f"<b>Quando</b>: <code>{display_time}</code>\n" \
                            f"<b>Repete</b>: {recurrence_display}\n" \
                            f"<b>Status</b>: {status}\n\n" 
        
        await _send_or_edit_reminder_message(update, message_text, parse_mode=ParseMode.HTML) 
        logger.info(f"Lembretes exibidos para {user_id}.")
    else:
        no_reminders_text = "Você ainda não tem lembretes programados. Use /add_lembrete para adicionar um!"
        await _send_or_edit_reminder_message(update, no_reminders_text, parse_mode=ParseMode.HTML) 
        logger.info(f"Nenhum lembrete encontrado para {user_id}.")

    keyboard = [
        [InlineKeyboardButton("↩️ Voltar ao Menu de Lembretes", callback_data="reminder_view_action:main_menu")],
        [InlineKeyboardButton("🏠 Voltar ao Menu Principal", callback_data="help_category:main_menu")],
        [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    return AWAIT_REMINDER_VIEW_ACTION


async def handle_view_reminder_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com as opções do menu de follow-up após ver lembretes."""
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "reminder_view_action:main_menu":
        await handlers.reminders_menu(update, context) 
        return ConversationHandler.END 
    elif action == "help_category:main_menu": 
        await handlers.send_main_help_menu(update, context)
        return ConversationHandler.END
    elif action == "cancel_dialog_action":
        await handlers.cancel_dialog(update, context)
        return ConversationHandler.END
    
    return ConversationHandler.END 


async def delete_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar um lembrete, listando-os com botões."""
    user_id = update.effective_user.id
    logger.info(f"Comando /apagar_lembrete recebido de {user_id}.")
    reminders = db.get_user_reminders(user_id)
    
    if not reminders:
        no_reminders_text = "Você não tem nenhum lembrete para apagar."
        await _send_or_edit_reminder_message(update, no_reminders_text, parse_mode=ParseMode.HTML) 
        
        keyboard = [
            [InlineKeyboardButton("➕ Adicionar Lembrete", callback_data="reminder_delete_action:add_new")],
            [InlineKeyboardButton("↩️ Voltar ao Menu de Lembretes", callback_data="reminder_delete_action:main_menu")],
            [InlineKeyboardButton("🏠 Voltar ao Menu Principal", callback_data="help_category:main_menu")],
            [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        
        return AWAIT_REMINDER_DELETE_ACTION
        
    reminders_list_text = "⏰ <b>Seus Lembretes:</b>\n\nSelecione o lembrete que deseja apagar:\n\n"
    keyboard_buttons = []
    for r in reminders:
        status = "✅ Ativo" if r['active'] else "❌ Inativo"
        display_time = r['scheduled_time'].astimezone(DEFAULT_TIMEZONE).strftime('%d/%m/%Y %H:%M')
        recurrence_display = r['recurrence'].capitalize()
        
        button_text = f"ID {r['id']}: {r['description']} ({display_time}) | Status: {status} | Repete: {recurrence_display}"
        if len(button_text) > 60:
            button_text = button_text[:57] + "..."
        keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"delete_reminder_id:{r['id']}")])
    
    keyboard_buttons.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel_reminder_delete_op")]) 
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    await _send_or_edit_reminder_message(update, reminders_list_text, reply_markup, parse_mode=ParseMode.HTML) 
    
    return GETTING_REMINDER_ID_FOR_DELETE 

async def delete_reminder_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga o lembrete selecionado via botão."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data

    if callback_data == "cancel_reminder_delete_op": 
        await _send_or_edit_reminder_message(update, "Operação de apagar lembrete cancelada.", parse_mode=ParseMode.HTML)
        context.user_data.clear()
        keyboard = [
            [InlineKeyboardButton("↩️ Voltar ao Menu de Lembretes", callback_data="reminder_delete_action:main_menu")],
            [InlineKeyboardButton("🏠 Voltar ao Menu Principal", callback_data="help_category:main_menu")],
            [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return AWAIT_REMINDER_DELETE_ACTION


    if not callback_data.startswith("delete_reminder_id:"):
        await _send_or_edit_reminder_message(update, "Seleção inválida. Por favor, tente novamente.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END 

    reminder_id = int(callback_data.split(':')[1])
    user_id = query.from_user.id

    if db.delete_reminder(reminder_id, user_id):
        job_name = str(reminder_id)
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"JobQueue: Lembrete '{job_name}' (ID: {reminder_id}) removido do JobQueue.")

        await _send_or_edit_reminder_message(update, f"🗑️ Lembrete ID <b>{reminder_id}</b> apagado com sucesso!", parse_mode=ParseMode.HTML)
        logger.info(f"Lembrete ID {reminder_id} apagado por {user_id}.")
    else:
        await _send_or_edit_reminder_message(update, f"❌ Não foi possível apagar o lembrete ID <b>{reminder_id}</b>. Verifique se o ID está correto.", parse_mode=ParseMode.HTML)
        logger.warning(f"Falha ao apagar lembrete ID {reminder_id} por {user_id}.")

    keyboard = [
        [InlineKeyboardButton("🗑️ Apagar Outro Lembrete", callback_data="reminder_delete_action:delete_another")],
        [InlineKeyboardButton("📚 Ver Meus Lembretes", callback_data="reminder_delete_action:view_all")],
        [InlineKeyboardButton("↩️ Voltar ao Menu de Lembretes", callback_data="reminder_delete_action:main_menu")],
        [InlineKeyboardButton("🏠 Voltar ao Menu Principal", callback_data="help_category:main_menu")],
        [InlineKeyboardButton("❌ Sair", callback_data="cancel_dialog_action")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text("O que você gostaria de fazer agora?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    context.user_data.clear() 
    return AWAIT_REMINDER_DELETE_ACTION 


async def handle_delete_reminder_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com as opções do menu de follow-up após apagar um lembrete."""
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "reminder_delete_action:delete_another":
        return await delete_reminder_start(update, context)
    elif action == "reminder_delete_action:view_all":
        return await view_reminders(update, context) 
    elif action == "reminder_delete_action:add_new":
        return await add_reminder_start(update, context)
    elif action == "reminder_delete_action:main_menu":
        await handlers.reminders_menu(update, context)
        return ConversationHandler.END
    elif action == "help_category:main_menu":
        await handlers.send_main_help_menu(update, context)
        return ConversationHandler.END
    elif action == "cancel_dialog_action":
        await handlers.cancel_dialog(update, context)
        return ConversationHandler.END
    
    return ConversationHandler.END