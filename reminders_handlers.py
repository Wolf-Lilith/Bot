# reminders_handlers.py

import logging
import datetime
from datetime import timedelta
from dateutil import parser
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, ConversationHandler, JobQueue
from telegram.constants import ParseMode # Importação adicionada
from telegram.helpers import escape_markdown # Importação adicionada

import db # Importa o módulo db para interagir com o banco de dados

# Usar o logger configurado em main.py
logger = logging.getLogger(__name__)

# Estados para ConversationHandler (valores altos para evitar conflitos)
GETTING_REMINDER_DESC = 300
GETTING_REMINDER_DATETIME = 301
GETTING_REMINDER_RECURRENCE = 302
GETTING_REMINDER_ID_FOR_DELETE = 303 # Para obter o ID do lembrete a ser apagado

# Fuso horário padrão do bot (pode ser ajustado se o usuário tiver uma configuração diferente)
DEFAULT_TIMEZONE = pytz.timezone('America/Sao_Paulo') # Exemplo. Mantenha o que você usa.

# --- Funções Auxiliares para Lembretes ---

def calculate_next_occurrence(current_scheduled_time: datetime.datetime, recurrence: str) -> datetime.datetime | None:
    """Calcula a próxima data/hora para um lembrete recorrente, garantindo que seja no futuro."""
    # Garante que o scheduled_time tenha informações de fuso horário
    if current_scheduled_time.tzinfo is None:
        logger.error("calculate_next_occurrence: current_scheduled_time não possui informações de fuso horário. Localizando como UTC.")
        current_scheduled_time = pytz.utc.localize(current_scheduled_time) # Assumindo UTC se for naive

    next_time = current_scheduled_time

    if recurrence == 'daily':
        next_time = current_scheduled_time + timedelta(days=1)
    elif recurrence == 'weekly':
        next_time = current_scheduled_time + timedelta(weeks=1)
    elif recurrence == 'monthly':
        # Tenta adicionar um mês, ajustando para o último dia do mês se necessário (ex: 31 de jan para 29 de fev)
        try:
            next_time = current_scheduled_time.replace(month=current_scheduled_time.month % 12 + 1)
        except ValueError:
            # Se o dia não existe no próximo mês (ex: 31 de abril), vai para o último dia
            next_month = current_scheduled_time.month % 12 + 1
            next_year = current_scheduled_time.year + (1 if next_month == 1 else 0)
            next_time = current_scheduled_time.replace(year=next_year, month=next_month, day=1) + timedelta(days=-1)
    elif recurrence == 'yearly':
        next_time = current_scheduled_time.replace(year=current_scheduled_time.year + 1)
    elif recurrence == 'none':
        return None # Não há recorrência, não recalcula
    else:
        logger.warning(f"Recorrência desconhecida: {recurrence}")
        return None

    # Se a próxima ocorrência calculada for no passado (ex: por causa de ajustes de fuso ou reinício do bot),
    # avança até que esteja no futuro.
    now = datetime.datetime.now(current_scheduled_time.tzinfo) # Usa o mesmo tzinfo
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
                next_time = next_time.replace(year=next_year, month=next_month, day=1) + timedelta(days=-1)
        elif recurrence == 'yearly':
            next_time = next_time.replace(year=next_time.year + 1)
        else: # 'none' ou desconhecido já devem ter retornado None
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
    
    bot: Bot = context.bot # Garante que context.bot é do tipo Bot

    try:
        # Envia a mensagem de lembrete
        await bot.send_message(user_id, escape_markdown(f"🔔 Lembrete: *{description}*", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembrete '{description}' (ID: {reminder_id}) enviado para user {user_id}.")

        if recurrence != 'none':
            # Recalcula a próxima ocorrência para lembretes recorrentes
            next_scheduled_time = calculate_next_occurrence(job.next_run_time, recurrence)
            if next_scheduled_time:
                # Remove o job antigo e adiciona um novo com o mesmo ID para substituí-lo
                # Isso impede jobs duplicados para o mesmo lembrete recorrente.
                job.schedule_removal() # Remove o job atual
                new_job = context.job_queue.run_once(
                    send_reminder,
                    next_scheduled_time,
                    data=reminder_data,
                    name=str(reminder_id) # Usa o ID do lembrete como nome do job
                )
                # Atualiza o DB com a nova data e o novo job_id
                db.update_reminder_scheduled_time(reminder_id, next_scheduled_time, new_job.id)
                logger.info(f"Lembrete '{description}' (ID: {reminder_id}) reagendado para {next_scheduled_time}.")
            else:
                # Se não há próxima ocorrência (ex: 'none' ou erro), desativa o lembrete no DB
                db.deactivate_reminder(reminder_id)
                logger.info(f"Lembrete '{description}' (ID: {reminder_id}) desativado após última ocorrência.")
        else:
            # Se não é recorrente, desativa após enviar
            db.deactivate_reminder(reminder_id)
            logger.info(f"Lembrete '{description}' (ID: {reminder_id}) desativado.")
            
    except Exception as e:
        logger.error(f"Erro ao enviar/reagendar lembrete ID {reminder_id} para user {user_id}: {e}")


def schedule_existing_reminders(job_queue: JobQueue, bot: Bot):
    """Agenda lembretes que estão no banco de dados ao iniciar o bot."""
    logger.info("Agendando lembretes existentes...")
    active_reminders = db.get_active_reminders()
    for reminder in active_reminders:
        reminder_id = reminder['id']
        user_id = reminder['user_id']
        description = reminder['description']
        scheduled_time = reminder['scheduled_time']
        recurrence = reminder['recurrence']
        job_id_from_db = reminder['job_id'] # Pega o job_id salvo no DB

        # Converte para o fuso horário padrão do bot, se a hora for "naive" (sem tzinfo)
        if scheduled_time.tzinfo is None:
            scheduled_time = DEFAULT_TIMEZONE.localize(scheduled_time)
        else:
            scheduled_time = scheduled_time.astimezone(DEFAULT_TIMEZONE)


        # Garante que o lembrete seja agendado para o futuro
        now = datetime.datetime.now(DEFAULT_TIMEZONE)
        if scheduled_time <= now:
            scheduled_time = calculate_next_occurrence(scheduled_time, recurrence)
            if not scheduled_time: # Se não houver próxima ocorrência (ex: 'none' e no passado), pula
                db.deactivate_reminder(reminder_id)
                logger.info(f"Lembrete ID {reminder_id} no passado e não recorrente. Desativado.")
                continue

        # Verifica se já existe um job com esse nome (ID do lembrete)
        existing_job = job_queue.get_jobs_by_name(str(reminder_id))
        if existing_job:
            # Se o job já existe (ex: bot foi reiniciado mas o JobQueue persistiu alguma informação),
            # remove o antigo para evitar duplicatas e adiciona o novo.
            logger.info(f"Job existente para lembrete ID {reminder_id} encontrado. Removendo para reagendar.")
            for job in existing_job:
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
            name=str(reminder_id) # Usa o ID do lembrete como nome do job
        )
        # Atualiza o job_id no banco de dados caso tenha mudado
        db.update_reminder_scheduled_time(reminder_id, scheduled_time, new_job.id)
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
        await update.message.reply_text(escape_markdown("A descrição do lembrete não pode ser vazia. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_DESC
    
    await update.message.reply_text(escape_markdown("Para quando é o lembrete? (Ex: 'amanhã 10:00', '25/12/2025 14:30', 'em 3 horas')", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    return GETTING_REMINDER_DATETIME

async def get_reminder_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data/hora do lembrete."""
    date_str = update.message.text.strip()
    try:
        # Tenta parsear a string de data/hora
        # 'fuzzy=True' permite parsing de strings incompletas ou com texto adicional
        scheduled_time = parser.parse(date_str, fuzzy=True)

        # Se o fuso horário for "naive" (não informado), localiza para o fuso horário padrão do bot
        if scheduled_time.tzinfo is None:
            scheduled_time = DEFAULT_TIMEZONE.localize(scheduled_time)
        else:
            # Se já tem fuso horário, converte para o fuso horário padrão do bot
            scheduled_time = scheduled_time.astimezone(DEFAULT_TIMEZONE)

        # Garante que o lembrete não seja agendado para o passado
        now = datetime.datetime.now(DEFAULT_TIMEZONE)
        if scheduled_time <= now:
            await update.message.reply_text(escape_markdown("A data/hora do lembrete deve ser no futuro. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
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

    except ValueError:
        await update.message.reply_text(escape_markdown("Não consegui entender a data/hora. Por favor, use um formato claro (ex: 'amanhã 10:00', '25/12/2025 14:30').", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_DATETIME

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

    # Adiciona o lembrete ao DB e obtém o ID
    reminder_id = db.add_reminder(user_id, description, scheduled_time, recurrence)

    if reminder_id:
        # Agenda o job no JobQueue
        job_data = {
            'id': reminder_id,
            'user_id': user_id,
            'description': description,
            'recurrence': recurrence,
        }
        # O nome do job é o ID do lembrete no DB para fácil rastreamento
        job = context.job_queue.run_once(
            send_reminder,
            scheduled_time,
            data=job_data,
            name=str(reminder_id) 
        )
        # Atualiza o job_id no banco de dados após o agendamento
        db.update_reminder_scheduled_time(reminder_id, scheduled_time, job.id)

        await query.edit_message_text(
            escape_markdown(f"🎉 Lembrete adicionado!\n'*{description}*' em {scheduled_time.strftime('%d/%m/%Y %H:%M')}\nRecorrência: {recurrence.capitalize()}", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Lembrete '{description}' adicionado e agendado por {user_id} para {scheduled_time} com recorrência {recurrence}.")
    else:
        await query.edit_message_text(escape_markdown("❌ Ops! Não foi possível adicionar o lembrete. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
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
            # Converte a data para o fuso horário do usuário para exibição
            display_time = r['scheduled_time'].astimezone(DEFAULT_TIMEZONE).strftime('%d/%m/%Y %H:%M')
            recurrence_display = r['recurrence'].capitalize()
            message_text += f"**ID: {r['id']}** - *{escape_markdown(r['description'], version=2)}*\n" \
                            f"  `Quando`: {display_time}\n" \
                            f"  `Repete`: {recurrence_display}\n" \
                            f"  `Status`: {status}\n\n"
        await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembretes exibidos para {user_id}.")
    else:
        await update.message.reply_text(escape_markdown("Você ainda não tem lembretes programados. Use /add_lembrete para adicionar um!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Nenhum lembrete encontrado para {user_id}.")

async def delete_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar um lembrete."""
    user_id = update.effective_user.id
    logger.info(f"Comando /apagar_lembrete recebido de {user_id}.")
    reminders = db.get_user_reminders(user_id) # Pega todos os lembretes para listar
    if not reminders:
        await update.message.reply_text(escape_markdown("Você não tem nenhum lembrete para apagar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    reminders_list = "⏰ *Seus Lembretes:*\n\n"
    for r in reminders:
        status = "✅ Ativo" if r['active'] else "❌ Inativo"
        display_time = r['scheduled_time'].astimezone(DEFAULT_TIMEZONE).strftime('%d/%m/%Y %H:%M')
        recurrence_display = r['recurrence'].capitalize()
        reminders_list += f"**ID: {r['id']}** - *{escape_markdown(r['description'], version=2)}*\n" \
                          f"  `Quando`: {display_time}\n" \
                          f"  `Repete`: {recurrence_display}\n" \
                          f"  `Status`: {status}\n\n"
    
    reminders_list += "Por favor, digite o *ID* do lembrete que deseja apagar."
    await update.message.reply_text(reminders_list, parse_mode=ParseMode.MARKDOWN_V2)
    return GETTING_REMINDER_ID_FOR_DELETE

async def delete_reminder_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga o lembrete."""
    user_id = update.effective_user.id
    try:
        reminder_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, insira um ID de lembrete válido (um número).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_ID_FOR_DELETE

    # Busca o lembrete para obter o job_id antes de deletar do DB
    # Poderíamos otimizar esta busca se db.delete_reminder retornasse o job_id
    # Por enquanto, pegamos todos os ativos para ver se está lá.
    reminder_to_delete = next((r for r in db.get_active_reminders(user_id=user_id) if r['id'] == reminder_id), None)
    
    if db.delete_reminder(reminder_id, user_id):
        # Se o lembrete foi deletado do DB, tenta remover do JobQueue
        if reminder_to_delete and reminder_to_delete.get('job_id'):
            job_name = reminder_to_delete['job_id']
            current_jobs = context.job_queue.get_jobs_by_name(job_name)
            for job in current_jobs:
                job.schedule_removal()
                logger.info(f"JobQueue: Lembrete '{job_name}' (ID: {reminder_id}) removido do JobQueue.")

        await update.message.reply_text(escape_markdown(f"🗑️ Lembrete ID **{reminder_id}** apagado com sucesso!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembrete ID {reminder_id} apagado por {user_id}.")
    else:
        await update.message.reply_text(escape_markdown(f"❌ Não foi possível apagar o lembrete ID **{reminder_id}**. Verifique se o ID está correto.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Falha ao apagar lembrete ID {reminder_id} por {user_id}.")

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo de lembrete em andamento."""
    if update.callback_query:
        await update.callback_query.answer()
        # Verifica se é um cancelamento específico de lembrete ou um cancelamento geral
        if update.callback_query.data == "cancel_reminder_add":
            await update.callback_query.edit_message_text(escape_markdown("Operação de adicionar lembrete cancelada. 😉", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        elif update.callback_query.data == "cancel_reminder_delete":
            await update.callback_query.edit_message_text(escape_markdown("Operação de apagar lembrete cancelada. 😉", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        else: # Outros cancelamentos de callbacks, se houver
            await update.callback_query.edit_message_text(escape_markdown("Operação de lembrete cancelada.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(escape_markdown("Operação de lembrete cancelada. Estou à disposição para o que precisar!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
    logger.info(f"Diálogo de lembrete cancelado por {update.effective_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END