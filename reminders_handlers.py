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

# Habilitar logging para este módulo
logger = logging.getLogger(__name__)

# Estados para ConversationHandler (certifique-se de que estes valores são únicos no seu main.py)
GETTING_REMINDER_DESC = 200
GETTING_REMINDER_DATETIME = 201
GETTING_REMINDER_RECURRENCE = 202
CONFIRM_DELETE_REMINDER = 203
GETTING_REMINDER_ID_FOR_DELETE = 204 # NOVO ESTADO: Para obter o ID do lembrete a ser apagado

# Fuso horário padrão do bot (pode ser ajustado se o usuário tiver uma configuração diferente)
DEFAULT_TIMEZONE = pytz.timezone('America/Sao_Paulo') # Exemplo. Mantenha o que você usa.

# --- Funções Auxiliares para Lembretes ---

def calculate_next_occurrence(current_scheduled_time: datetime.datetime, recurrence: str) -> datetime.datetime | None:
    """Calcula a próxima data/hora para um lembrete recorrente, garantindo que seja no futuro."""
    if current_scheduled_time.tzinfo is None:
        logger.error("calculate_next_occurrence: current_scheduled_time não possui informações de fuso horário.")
        # Por segurança, assume-se DEFAULT_TIMEZONE se for naive
        current_scheduled_time = DEFAULT_TIMEZONE.localize(current_scheduled_time)

    now_aware = datetime.datetime.now(DEFAULT_TIMEZONE)
    next_time = current_scheduled_time

    # Se o lembrete já passou, calcula o próximo
    while next_time <= now_aware:
        if recurrence == 'daily':
            next_time += timedelta(days=1)
        elif recurrence == 'weekly':
            next_time += timedelta(weeks=1)
        elif recurrence == 'monthly':
            # Adiciona um mês, ajustando para o último dia do mês se necessário
            try:
                next_time = next_time.replace(month=next_time.month + 1)
            except ValueError: # Se for dezembro, vai para janeiro do próximo ano
                next_time = next_time.replace(year=next_time.year + 1, month=1)
        elif recurrence == 'yearly':
            next_time = next_time.replace(year=next_time.year + 1)
        else:
            return None # Não recorrente ou tipo desconhecido, não recalcula

    return next_time

async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Função que envia o lembrete ao usuário."""
    job = context.job
    reminder_id = job.data['reminder_id']
    user_id = job.data['user_id']
    description = job.data['description']
    recurrence = job.data['recurrence']
    
    logger.info(f"Enviando lembrete ID {reminder_id} para o usuário {user_id}: '{description}'")

    try:
        # Envia a mensagem do lembrete
        await context.bot.send_message(chat_id=user_id, text=f"🔔 Lembrete: {escape_markdown(description, version=2)}", parse_mode=ParseMode.MARKDOWN_V2)
        
        # Se for recorrente, agende a próxima ocorrência e atualize no DB
        if recurrence:
            reminder_obj = db.get_reminder_by_id(reminder_id)
            if reminder_obj:
                current_scheduled_time = reminder_obj['scheduled_time']
                next_occurrence = calculate_next_occurrence(current_scheduled_time, recurrence)
                
                if next_occurrence:
                    # Verifica se o lembrete ainda está ativo antes de reagendar
                    if db.is_reminder_active(reminder_id):
                        job.run_at = next_occurrence # Atualiza o Job do PTB
                        db.update_reminder_scheduled_time(reminder_id, next_occurrence) # Atualiza no DB
                        logger.info(f"Lembrete ID {reminder_id} reagendado para {next_occurrence}.")
                    else:
                        logger.info(f"Lembrete ID {reminder_id} foi desativado, não será reagendado.")
                        job.schedule_removal() # Remove o job se o lembrete foi desativado no DB
                else:
                    logger.warning(f"Não foi possível calcular a próxima ocorrência para o lembrete ID {reminder_id}. Removendo job.")
                    job.schedule_removal() # Remove o job se não conseguiu calcular a próxima ocorrência
            else:
                logger.warning(f"Lembrete ID {reminder_id} não encontrado no DB para reagendamento. Removendo job.")
                job.schedule_removal() # Remove o job se não encontrou o lembrete no DB
        else:
            # Se não for recorrente, desativa o lembrete e remove o job
            db.deactivate_reminder(reminder_id)
            job.schedule_removal()
            logger.info(f"Lembrete ID {reminder_id} não recorrente enviado e desativado.")

    except Exception as e:
        logger.error(f"Erro ao enviar lembrete ID {reminder_id} para {user_id}: {e}")
        # Tenta desativar o lembrete no DB para evitar loop de erros
        db.deactivate_reminder(reminder_id)
        job.schedule_removal() # Remove o job em caso de erro

def schedule_reminder_job(job_queue: JobQueue, reminder_obj: dict, application_instance: object):
    """Agenda um lembrete no JobQueue do PTB."""
    reminder_id = reminder_obj['id']
    user_id = reminder_obj['user_id']
    description = reminder_obj['description']
    scheduled_time = reminder_obj['scheduled_time']
    recurrence = reminder_obj['recurrence']

    # Garante que scheduled_time é aware do fuso horário antes de agendar
    if scheduled_time.tzinfo is None:
        scheduled_time = DEFAULT_TIMEZONE.localize(scheduled_time)
        logger.warning(f"schedule_reminder_job: scheduled_time para lembrete ID {reminder_id} era naive, localizado para {DEFAULT_TIMEZONE}.")

    # Se a data já passou (para lembretes recorrentes ou se o bot ficou offline por muito tempo)
    now_aware = datetime.datetime.now(DEFAULT_TIMEZONE)
    if scheduled_time <= now_aware and recurrence:
        scheduled_time = calculate_next_occurrence(scheduled_time, recurrence)
        if not scheduled_time:
            logger.warning(f"Lembrete ID {reminder_id} é recorrente mas não pôde ter a próxima ocorrência calculada para agendamento. Desativando.")
            db.deactivate_reminder(reminder_id)
            return
        db.update_reminder_scheduled_time(reminder_id, scheduled_time) # Atualiza o DB com a próxima ocorrência

    elif scheduled_time <= now_aware and not recurrence:
        logger.info(f"Lembrete ID {reminder_id} não recorrente já passou. Desativando.")
        db.deactivate_reminder(reminder_id)
        return

    job_data = {
        'reminder_id': reminder_id,
        'user_id': user_id,
        'description': description,
        'recurrence': recurrence,
    }

    # Passa o 'application_instance' como 'application' para o job.context
    # Isso permite que 'context.bot' seja acessado dentro de send_reminder
    job_queue.run_once(
        send_reminder,
        when=scheduled_time,
        data=job_data,
        name=f'reminder_{reminder_id}',
        chat_id=user_id, # Adiciona chat_id para jobs do usuário
        user_id=user_id, # Adiciona user_id para jobs do usuário
        job_kwargs={'application': application_instance} # Passa a instância completa do application
    )
    logger.info(f"Lembrete ID {reminder_id} agendado para {scheduled_time}.")


def schedule_existing_reminders(job_queue: JobQueue, application_instance: object):
    """Agenda todos os lembretes ativos do banco de dados na inicialização do bot."""
    reminders = db.get_all_reminders_for_scheduling()
    logger.info(f"Tentando agendar {len(reminders)} lembretes existentes...")
    for reminder_obj in reminders:
        try:
            schedule_reminder_job(job_queue, reminder_obj, application_instance)
        except Exception as e:
            logger.error(f"Falha ao agendar lembrete ID {reminder_obj.get('id')} na inicialização: {e}")
            # Desativa o lembrete problemático para evitar que o erro se repita
            db.deactivate_reminder(reminder_obj.get('id'))


# --- Handlers para Adicionar Lembretes ---
async def add_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de adicionar um lembrete."""
    await update.message.reply_text(escape_markdown("Certo! Qual é a descrição do lembrete? (Ex: 'Comprar leite', 'Reunião com o João')", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Usuário {update.effective_user.id} iniciou adição de lembrete.")
    return GETTING_REMINDER_DESC

async def get_reminder_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a descrição do lembrete."""
    description = update.message.text.strip()
    if not description:
        await update.message.reply_text(escape_markdown("A descrição do lembrete não pode ser vazia. Por favor, digite uma descrição ou /cancelar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_DESC
    
    context.user_data['reminder_description'] = description
    await update.message.reply_text(escape_markdown("Qual a data e hora do lembrete? (Ex: 'amanhã 10:30', '01/01/2026 14:00')", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Descrição do lembrete '{description}' recebida de {update.effective_user.id}.")
    return GETTING_REMINDER_DATETIME

async def get_reminder_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data e hora do lembrete e pede a recorrência."""
    datetime_str = update.message.text.strip()
    user_id = update.effective_user.id

    try:
        # Tenta parsear a data/hora usando dateutil.parser
        # Assume que o input pode ser em português (hoje, amanhã, etc.)
        scheduled_time_naive = parser.parse(datetime_str, fuzzy=True)
        # Localiza a data/hora para o fuso horário padrão do bot
        scheduled_time_aware = DEFAULT_TIMEZONE.localize(scheduled_time_naive)

        # Se a data/hora parseada já passou, mas não é um lembrete para o mesmo dia do ano (ex: aniversário)
        # Tenta ajustar para o próximo ano se o mês/dia já passou neste ano.
        now_aware = datetime.datetime.now(DEFAULT_TIMEZONE)
        if scheduled_time_aware < now_aware:
            # Se for um lembrete de um dia específico do ano (ex: 25/12), e já passou, sugere o próximo ano.
            # Caso contrário, pode ser só um horário no mesmo dia que já passou, então ajusta para o dia seguinte.
            if scheduled_time_aware.date() < now_aware.date():
                # Se a data já passou, tenta o próximo dia (para recorrência diária implícita, ou se o usuário errou a data)
                # ou o próximo ano para datas específicas.
                if scheduled_time_aware.month < now_aware.month or \
                   (scheduled_time_aware.month == now_aware.month and scheduled_time_aware.day < now_aware.day):
                   # Se mês/dia já passou, tenta o próximo ano para manter a data
                   scheduled_time_aware = scheduled_time_aware.replace(year=now_aware.year + 1)
                   if scheduled_time_aware < now_aware: # Caso o ano +1 ainda seja passado (muito raro)
                       scheduled_time_aware += timedelta(days=365) # Última tentativa de jogar pro futuro
                else: # Data no futuro, mas hora já passou, para o mesmo dia
                    scheduled_time_aware += timedelta(days=1)
            elif scheduled_time_aware.time() < now_aware.time():
                scheduled_time_aware += timedelta(days=1)
            
            # Garante que, mesmo após ajustes, a data está no futuro.
            if scheduled_time_aware <= now_aware:
                 await update.message.reply_text(escape_markdown("Essa data/hora parece estar no passado ou é muito próxima. Por favor, tente novamente com uma data/hora no futuro, ou /cancelar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
                 return GETTING_REMINDER_DATETIME


        context.user_data['reminder_scheduled_time'] = scheduled_time_aware
        
        keyboard = [
            [InlineKeyboardButton("Não Recorrente", callback_data="recurrence:none")],
            [InlineKeyboardButton("Diariamente", callback_data="recurrence:daily")],
            [InlineKeyboardButton("Semanalmente", callback_data="recurrence:weekly")],
            [InlineKeyboardButton("Mensalmente", callback_data="recurrence:monthly")],
            [InlineKeyboardButton("Anualmente", callback_data="recurrence:yearly")],
            [InlineKeyboardButton("Cancelar", callback_data="cancel_reminder_action")] # Adicionado botão de cancelar
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(escape_markdown("Compreendido! O lembrete será enviado em " + scheduled_time_aware.strftime('%d/%m/%Y às %H:%M') + " (Horário de Brasília).\n\nEste lembrete deve se repetir?", version=2), reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Data/hora do lembrete '{datetime_str}' parseada para {scheduled_time_aware} para {user_id}.")
        return GETTING_REMINDER_RECURRENCE

    except (parser._parser.ParserError, ValueError) as e:
        await update.message.reply_text(escape_markdown("Não consegui entender a data/hora. Por favor, use um formato como 'amanhã 10:30' ou '01/01/2026 14:00', ou /cancelar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Erro ao parsear data/hora '{datetime_str}' de {user_id}: {e}")
        return GETTING_REMINDER_DATETIME
    except Exception as e:
        logger.error(f"Erro inesperado ao processar data/hora do lembrete de {user_id}: {e}")
        await update.message.reply_text(escape_markdown("Ocorreu um erro ao processar a data. Por favor, tente novamente ou /cancelar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_DATETIME


async def get_reminder_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a recorrência e salva o lembrete."""
    query = update.callback_query
    await query.answer()

    recurrence = query.data.split(":")[1] if query.data.startswith("recurrence:") else None
    
    # Se o usuário clicou em cancelar no teclado de recorrência
    if query.data == "cancel_reminder_action":
        await query.edit_message_text(escape_markdown("Operação de adicionar lembrete cancelada. 😉", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data.clear()
        return ConversationHandler.END

    description = context.user_data.get('reminder_description')
    scheduled_time = context.user_data.get('reminder_scheduled_time')
    user_id = query.effective_user.id

    if not description or not scheduled_time:
        logger.error(f"Erro: descrição ou scheduled_time não encontrados para user {user_id} no estado GETTING_REMINDER_RECURRENCE.")
        await query.edit_message_text(escape_markdown("Ocorreu um erro ao finalizar o lembrete. Por favor, tente novamente com /add_lembrete.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data.clear()
        return ConversationHandler.END

    recurrence_map = {
        'none': None,
        'daily': 'daily',
        'weekly': 'weekly',
        'monthly': 'monthly',
        'yearly': 'yearly'
    }
    final_recurrence = recurrence_map.get(recurrence, None)

    reminder_id = db.add_reminder(user_id, description, scheduled_time, final_recurrence)
    if reminder_id:
        # Agendar o job imediatamente após salvar
        schedule_reminder_job(context.application.job_queue, {
            'id': reminder_id,
            'user_id': user_id,
            'description': description,
            'scheduled_time': scheduled_time,
            'recurrence': final_recurrence
        }, context.application) # Passa a instância completa do application
        
        recurrence_text = f" Repetição: {final_recurrence.capitalize()}." if final_recurrence else ""
        await query.edit_message_text(escape_markdown(f"✅ Lembrete adicionado! ID: `{reminder_id}`\nDescrição: '{description}'\nAgendado para: {scheduled_time.strftime('%d/%m/%Y às %H:%M')}.{recurrence_text}", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembrete ID {reminder_id} adicionado e agendado para {user_id}.")
    else:
        await query.edit_message_text(escape_markdown("❌ Não foi possível adicionar o lembrete. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Falha ao adicionar lembrete para {user_id}.")

    context.user_data.clear()
    return ConversationHandler.END

# --- Handlers para Visualizar Lembretes ---
async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vê os lembretes ativos do usuário."""
    user_id = update.effective_user.id
    reminders = db.get_active_reminders(user_id) # Usar a nova função que busca apenas ativos

    if reminders:
        text = escape_markdown("*Seus Lembretes Ativos:*\n\n", version=2)
        for r in reminders:
            recurrence_str = f" (Repete: {r['recurrence'].capitalize()})" if r['recurrence'] else ""
            text += escape_markdown(f"ID: `{r['id']}`\n", version=2)
            text += escape_markdown(f"  Descrição: '{r['description']}'\n", version=2)
            text += escape_markdown(f"  Próximo: {r['scheduled_time'].strftime('%d/%m/%Y às %H:%M')}{recurrence_str}\n\n", version=2)
        
        # Opcional: Adicionar botões para apagar lembretes aqui também
        keyboard = []
        for r in reminders:
            keyboard.append([InlineKeyboardButton(f"Apagar ID {r['id']}: '{r['description']}'", callback_data=f"delete_reminder:{r['id']}")])
        if keyboard: # Só adiciona o botão de cancelar se houver lembretes para apagar
            keyboard.append([InlineKeyboardButton("Cancelar Deleção", callback_data="cancel_reminder_delete")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Usuário {user_id} visualizou seus lembretes.")
    else:
        await update.message.reply_text(escape_markdown("Você não tem nenhum lembrete ativo. Use /add_lembrete para adicionar um!", version=2), parse_mode=ParseMode.MARKDOWN_V2)

# --- Handlers para Apagar Lembretes ---
async def delete_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o processo de apagar um lembrete, mostrando as opções."""
    user_id = update.effective_user.id
    reminders = db.get_active_reminders(user_id)

    if not reminders:
        await update.message.reply_text(escape_markdown("Você não tem nenhum lembrete ativo para apagar.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    text = escape_markdown("*Selecione o lembrete que deseja apagar:*\n\n", version=2)
    keyboard = []
    for r in reminders:
        recurrence_str = f" (Repete: {r['recurrence'].capitalize()})" if r['recurrence'] else ""
        text += escape_markdown(f"ID: `{r['id']}` - '{r['description']}' ({r['scheduled_time'].strftime('%d/%m/%Y %H:%M')}{recurrence_str})\n", version=2)
        keyboard.append([InlineKeyboardButton(f"Apagar ID {r['id']}", callback_data=f"delete_reminder:{r['id']}")])
    
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel_reminder_delete")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logger.info(f"Usuário {user_id} iniciou o processo de apagar lembrete.")
    return GETTING_REMINDER_ID_FOR_DELETE

async def confirm_delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga o lembrete selecionado."""
    query = update.callback_query
    await query.answer()

    user_id = query.effective_user.id
    
    if query.data.startswith("delete_reminder:"):
        reminder_id_str = query.data.split(":")[1]
        try:
            reminder_id = int(reminder_id_str)
        except ValueError:
            await query.edit_message_text(escape_markdown("❌ ID de lembrete inválido. Por favor, tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            context.user_data.clear()
            return ConversationHandler.END

        # Tentar cancelar o job agendado se ele existir
        job_name = f'reminder_{reminder_id}'
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Job do lembrete ID {reminder_id} removido do JobQueue.")

        if db.delete_reminder(reminder_id, user_id):
            await query.edit_message_text(escape_markdown(f"✅ Lembrete (ID: `{reminder_id}`) apagado com sucesso!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Lembrete ID {reminder_id} apagado por {user_id}.")
        else:
            reply_text = escape_markdown(f"❌ Não foi possível apagar o lembrete com ID `{reminder_id}`. Verifique se ele existe e pertence a você.", version=2)
            if update.callback_query:
                await update.callback_query.edit_message_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)
            logger.warning(f"Falha ao deletar lembrete ID {reminder_id} para user {user_id}.")

    elif query.data == "cancel_reminder_delete":
        await query.edit_message_text(escape_markdown("Operação de apagar lembrete cancelada. 😉", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text(escape_markdown("Ação desconhecida para apagar lembrete.", version=2), parse_mode=ParseMode.MARKDOWN_V2)

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela qualquer diálogo de lembrete em andamento."""
    if update.callback_query:
        await update.callback_query.answer()
        # Verifica se é um cancelamento específico de lembrete ou um cancelamento geral
        if update.callback_query.data == "cancel_reminder_delete":
            await update.callback_query.edit_message_text(escape_markdown("Operação de apagar lembrete cancelada. 😉", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        else: # Outros cancelamentos de callbacks, se houver
            await update.callback_query.edit_message_text(escape_markdown("Operação de lembrete cancelada.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(escape_markdown("Operação de lembrete cancelada. Estou à disposição para o que precisar!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    
    context.user_data.clear() # Limpa os dados do usuário
    return ConversationHandler.END