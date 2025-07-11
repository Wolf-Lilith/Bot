# reminders_handlers.py

import logging
import datetime
from datetime import timedelta
from dateutil import parser
import pytz
import re # Importação adicionada para expressões regulares

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler, JobQueue, Application
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

import db

logger = logging.getLogger(__name__)

# Estados para ConversationHandler (valores altos para evitar conflitos)
GETTING_REMINDER_DESC = 300
GETTING_REMINDER_DATETIME = 301
GETTING_REMINDER_RECURRENCE = 302
GETTING_REMINDER_ID_FOR_DELETE = 303

# Fuso horário padrão do bot (pode ser ajustado se o usuário tiver uma configuração diferente)
DEFAULT_TIMEZONE = pytz.timezone('America/Sao_Paulo')

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
                next_time = next_time.replace(year=next_month, day=1) + timedelta(days=-1) # Corrigido para usar next_month
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
        await bot.send_message(user_id, escape_markdown(f"🔔 Lembrete: *{description}*", version=2), parse_mode=ParseMode.MARKDOWN_V2)
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
    await update.message.reply_text(escape_markdown("Qual é o lembrete? (ex: Pagar a conta de luz)", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return GETTING_REMINDER_DESC

async def get_reminder_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a descrição do lembrete."""
    context.user_data['reminder_description'] = update.message.text.strip()
    if not context.user_data['reminder_description']:
        await update.message.reply_text(escape_markdown("A descrição do lembrete não pode ser vazia\\. Por favor, tente novamente\\.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_DESC
    
    # Mensagem de prompt aprimorada para clareza
    await update.message.reply_text(escape_markdown("Para quando é o lembrete? (Ex: 'amanhã 10:00', '15/07/2025 14:30', 'em 5 minutos', 'daqui a 2 horas')", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return GETTING_REMINDER_DATETIME

async def get_reminder_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data/hora do lembrete."""
    date_str = update.message.text.strip().lower()
    scheduled_time = None
    now = datetime.datetime.now(DEFAULT_TIMEZONE)

    # Tenta interpretar como tempo relativo (ex: "em 5 minutos", "daqui a 2 horas")
    match_minutes = re.search(r'em (\d+) minutos?|daqui a (\d+) minutos?', date_str)
    match_hours = re.search(r'em (\d+) horas?|daqui a (\d+) horas?', date_str)
    match_days = re.search(r'em (\d+) dias?|daqui a (\d+) dias?', date_str)

    if match_minutes:
        minutes = int(match_minutes.group(1) or match_minutes.group(2))
        scheduled_time = now + timedelta(minutes=minutes)
    elif match_hours:
        hours = int(match_hours.group(1) or match_hours.group(2))
        scheduled_time = now + timedelta(hours=hours)
    elif match_days:
        days = int(match_days.group(1) or match_days.group(2))
        scheduled_time = now + timedelta(days=days)
    else:
        # Tenta parsear com dayfirst=True para o formato DD/MM/AAAA
        try:
            scheduled_time = parser.parse(date_str, dayfirst=True, fuzzy=False)
            if scheduled_time.tzinfo is None:
                scheduled_time = DEFAULT_TIMEZONE.localize(scheduled_time)
            else:
                scheduled_time = scheduled_time.astimezone(DEFAULT_TIMEZONE)
            
            # Se a data parseada ainda estiver no passado, tenta ajustar para o futuro
            if scheduled_time <= now:
                # Se a data é anterior ao dia atual, tenta mover para o dia atual ou próximo
                if scheduled_time.date() < now.date():
                    temp_time = scheduled_time.replace(year=now.year, month=now.month, day=now.day)
                    if temp_time > now:
                        scheduled_time = temp_time
                    else: # Se mesmo no dia atual a hora já passou, move para o dia seguinte
                        scheduled_time = temp_time + timedelta(days=1)
                # Se é hoje, mas a hora já passou, move para o dia seguinte
                elif scheduled_time.date() == now.date() and scheduled_time.time() <= now.time():
                    scheduled_time += timedelta(days=1)

        except ValueError:
            # Se a primeira tentativa (dayfirst=True) falhar, tenta com fuzzy=True
            try:
                scheduled_time = parser.parse(date_str, fuzzy=True)
                if scheduled_time.tzinfo is None:
                    scheduled_time = DEFAULT_TIMEZONE.localize(scheduled_time)
                else:
                    scheduled_time = scheduled_time.astimezone(DEFAULT_TIMEZONE)
                
                # Validação final: se, após todas as tentativas, ainda está no passado
                if scheduled_time <= now:
                    # Tenta ajustar para o mesmo horário no dia seguinte se for uma data/hora no passado
                    if scheduled_time.date() < now.date():
                        scheduled_time = scheduled_time.replace(year=now.year, month=now.month, day=now.day)
                        if scheduled_time <= now:
                            scheduled_time += timedelta(days=1)
                    elif scheduled_time.date() == now.date() and scheduled_time.time() <= now.time():
                        scheduled_time += timedelta(days=1)

            except ValueError:
                # Se todas as tentativas falharem
                await update.message.reply_text(escape_markdown("Não consegui entender a data/hora\\. Por favor, use um formato claro (ex: 'amanhã 10:00', '15/07/2025 14:30', 'em 5 minutos')\\.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
                return GETTING_REMINDER_DATETIME

    if scheduled_time is None or scheduled_time <= now:
        await update.message.reply_text(escape_markdown("A data/hora do lembrete deve ser no futuro\\. Por favor, tente novamente (ex: 'amanhã 10:00', '15/07/2025 14:30', 'em 5 minutos')\\.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_DATETIME

    context.user_data['scheduled_time'] = scheduled_time

    keyboard = [
        [InlineKeyboardButton("Sem Recorrência", callback_data="none")],
        [InlineKeyboardButton("Diariamente", callback_data="daily")],
        [InlineKeyboardButton("Semanalmente", callback_data="weekly")],
        [InlineKeyboardButton("Mensalmente", callback_data="monthly")],
        [InlineKeyboardButton("Anualmente", callback_data="yearly")],
        [InlineKeyboardButton("Cancelar", callback_data="cancel_reminder_add")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        escape_markdown("Com que frequência você quer que este lembrete se repita?", version=2),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return GETTING_REMINDER_RECURRENCE

async def get_reminder_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a frequência de recorrência e salva o lembrete."""
    query = update.callback_query
    await query.answer()
    recurrence = query.data

    if recurrence == "cancel_reminder_add":
        return await cancel_dialog(update, context)

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

        await query.edit_message_text(
            escape_markdown(f"🎉 Lembrete adicionado!\\n'\\*{description}\\*' em {scheduled_time.strftime('%d/%m/%Y %H:%M')}\\nRecorrência: {recurrence.capitalize()}", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Lembrete '{description}' adicionado e agendado por {user_id} para {scheduled_time} com recorrência {recurrence}.")
    else:
        await query.edit_message_text(escape_markdown("❌ Ops! Não foi possível adicionar o lembrete\\. Por favor, tente novamente\\.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Falha ao adicionar lembrete '{description}' para {user_id}.")
    
    context.user_data.clear()
    return ConversationHandler.END


async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vê todos os lembretes do usuário (ativos e inativos)."""
    user_id = update.effective_user.id
    reminders = db.get_user_reminders(user_id)
    if reminders:
        message_text = "⏰ *Seus Lembretes:*\n\n"
        for r in reminders:
            status = "✅ Ativo" if r['active'] else "❌ Inativo"
            display_time = r['scheduled_time'].astimezone(DEFAULT_TIMEZONE).strftime('%d/%m/%Y %H:%M')
            recurrence_display = r['recurrence'].capitalize()
            
            escaped_description = escape_markdown(r['description'], version=2)
            escaped_display_time = escape_markdown(display_time, version=2)
            escaped_recurrence_display = escape_markdown(recurrence_display, version=2)
            escaped_status = escape_markdown(status, version=2)

            message_text += f"*ID*: `{r['id']}`\n" \
                            f"*Descrição*: {escaped_description}\n" \
                            f"*Quando*: `{escaped_display_time}`\n" \
                            f"*Repete*: {escaped_recurrence_display}\n" \
                            f"*Status*: {escaped_status}\n\n"
        
        await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembretes exibidos para {user_id}.")
    else:
        await update.message.reply_text(escape_markdown("Você ainda não tem lembretes programados\\. Use /add_lembrete para adicionar um!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Nenhum lembrete encontrado para {user_id}.")

async def delete_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar um lembrete."""
    user_id = update.effective_user.id
    logger.info(f"Comando /apagar_lembrete recebido de {user_id}.")
    reminders = db.get_user_reminders(user_id)
    if not reminders:
        await update.message.reply_text(escape_markdown("Você não tem nenhum lembrete para apagar\\.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    reminders_list = "⏰ *Seus Lembretes:*\n\n"
    for r in reminders:
        status = "✅ Ativo" if r['active'] else "❌ Inativo"
        display_time = r['scheduled_time'].astimezone(DEFAULT_TIMEZONE).strftime('%d/%m/%Y %H:%M')
        recurrence_display = r['recurrence'].capitalize()
        
        escaped_description = escape_markdown(r['description'], version=2)
        escaped_display_time = escape_markdown(display_time, version=2)
        escaped_recurrence_display = escape_markdown(recurrence_display, version=2)
        escaped_status = escape_markdown(status, version=2)

        reminders_list += f"*ID*: `{r['id']}`\n" \
                          f"*Descrição*: {escaped_description}\n" \
                          f"*Quando*: `{escaped_display_time}`\n" \
                          f"*Repete*: {escaped_recurrence_display}\n" \
                          f"*Status*: {escaped_status}\n\n"
    
    reminders_list += escape_markdown("Por favor, digite o *ID* do lembrete que deseja apagar\\.", version=2)
    await update.message.reply_text(reminders_list, parse_mode=ParseMode.MARKDOWN_V2)
    return GETTING_REMINDER_ID_FOR_DELETE

async def delete_reminder_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga o lembrete."""
    user_id = update.effective_user.id
    try:
        reminder_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, insira um ID de lembrete válido (um número)\\.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_ID_FOR_DELETE

    if db.delete_reminder(reminder_id, user_id):
        job_name = str(reminder_id)
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"JobQueue: Lembrete '{job_name}' (ID: {reminder_id}) removido do JobQueue.")

        await update.message.reply_text(escape_markdown(f"🗑️ Lembrete ID \\*{reminder_id}\\* apagado com sucesso!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembrete ID {reminder_id} apagado por {user_id}.")
    else:
        await update.message.reply_text(escape_markdown(f"❌ Não foi possível apagar o lembrete ID \\*{reminder_id}\\*\\. Verifique se o ID está correto\\.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Falha ao apagar lembrete ID {reminder_id} por {user_id}.")

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo de lembrete em andamento."""
    if update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.data == "cancel_reminder_add":
            await update.callback_query.edit_message_text(escape_markdown("Operação de adicionar lembrete cancelada\\. 😉", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        elif update.callback_query.data == "cancel_reminder_delete":
            await update.callback_query.edit_message_text(escape_markdown("Operação de apagar lembrete cancelada\\. 😉", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.callback_query.edit_message_text(escape_markdown("Operação de lembrete cancelada\\.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(escape_markdown("Operação de lembrete cancelada\\. Estou à disposição para o que precisar!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Diálogo de lembrete cancelado por {update.effective_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END