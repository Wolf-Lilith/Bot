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
CONFIRM_DELETE_REMINDER = 203 # Renumerado para evitar conflitos
GETTING_REMINDER_ID_FOR_DELETE = 204 # NOVO ESTADO: Para obter o ID do lembrete a ser apagado

# Fuso horário padrão do bot (pode ser ajustado se o usuário tiver uma configuração diferente)
DEFAULT_TIMEZONE = pytz.timezone('America/Sao_Paulo') # Exemplo. Mantenha o que você usa.

# --- Funções Auxiliares para Lembretes ---

def calculate_next_occurrence(current_scheduled_time: datetime.datetime, recurrence: str) -> datetime.datetime | None:
    """Calcula a próxima data/hora para um lembrete recorrente, garantindo que seja no futuro."""
    if current_scheduled_time.tzinfo is None:
        logger.error("calculate_next_occurrence: current_scheduled_time não possui informações de fuso horário.")
        # Por segurança, vamos assumir UTC se não houver fuso horário
        current_scheduled_time = pytz.utc.localize(current_scheduled_time)

    now = datetime.datetime.now(current_scheduled_time.tzinfo) # Usa o fuso horário do lembrete

    if recurrence == 'daily':
        next_occurrence = current_scheduled_time + timedelta(days=1)
        # Se a próxima ocorrência já passou hoje, avance para o próximo dia
        if next_occurrence < now:
            next_occurrence = next_occurrence.replace(day=now.day, month=now.month, year=now.year) # Reseta para hoje
            if next_occurrence < now: # Se ainda assim for passado, vai para amanhã
                next_occurrence += timedelta(days=1)

    elif recurrence == 'weekly':
        next_occurrence = current_scheduled_time + timedelta(weeks=1)
        if next_occurrence < now:
            # Tenta ajustar para a próxima semana se já passou
            next_occurrence = next_occurrence.replace(day=now.day, month=now.month, year=now.year)
            while next_occurrence < now:
                next_occurrence += timedelta(weeks=1)

    elif recurrence == 'monthly':
        # Para mensal, tenta manter o dia do mês, ajustando para o final do mês se necessário
        next_month = current_scheduled_time.month % 12 + 1
        next_year = current_scheduled_time.year + (1 if next_month == 1 else 0)
        try:
            next_occurrence = current_scheduled_time.replace(year=next_year, month=next_month)
        except ValueError:
            # Dia fora do alcance para o próximo mês (ex: 31 de fevereiro)
            next_occurrence = current_scheduled_time.replace(year=next_year, month=next_month, day=1) + timedelta(days=32)
            next_occurrence = next_occurrence.replace(day=1) - timedelta(days=1) # Último dia do mês

        if next_occurrence < now:
            # Se a próxima ocorrência calculada ainda está no passado, tenta para o mês seguinte novamente
            next_month = next_occurrence.month % 12 + 1
            next_year = next_occurrence.year + (1 if next_month == 1 else 0)
            try:
                next_occurrence = next_occurrence.replace(year=next_year, month=next_month)
            except ValueError:
                next_occurrence = next_occurrence.replace(year=next_year, month=next_month, day=1) + timedelta(days=32)
                next_occurrence = next_occurrence.replace(day=1) - timedelta(days=1) # Último dia do mês

    elif recurrence == 'yearly':
        next_occurrence = current_scheduled_time.replace(year=current_scheduled_time.year + 1)
        if next_occurrence < now:
            # Se a próxima ocorrência ainda está no passado, tenta para o próximo ano novamente
            next_occurrence = next_occurrence.replace(year=next_occurrence.year + 1)
    else:
        return None # Não recorrente

    # Garante que a data calculada seja sempre no futuro
    if next_occurrence < now:
        # Se por alguma lógica de fuso horário ou cálculo ela ainda está no passado, force para o futuro
        # Isso pode acontecer em viradas de fuso ou DST
        if recurrence == 'daily':
            next_occurrence += timedelta(days=1)
        elif recurrence == 'weekly':
            next_occurrence += timedelta(weeks=1)
        elif recurrence == 'monthly':
            # Para mensal, avançar um mês inteiro pode ser mais seguro
            next_month = next_occurrence.month % 12 + 1
            next_year = next_occurrence.year + (1 if next_month == 1 else 0)
            try:
                next_occurrence = next_occurrence.replace(year=next_year, month=next_month)
            except ValueError:
                next_occurrence = next_occurrence.replace(year=next_year, month=next_month, day=1) + timedelta(days=32)
                next_occurrence = next_occurrence.replace(day=1) - timedelta(days=1)
        elif recurrence == 'yearly':
            next_occurrence = next_occurrence.replace(year=next_occurrence.year + 1)

    return next_occurrence


async def send_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Função que envia o lembrete para o usuário e lida com a recorrência."""
    job_data = context.job.data
    user_id = job_data['user_id']
    description = job_data['description']
    reminder_id = job_data['reminder_id']
    recurrence = job_data['recurrence']
    scheduled_time_str = job_data['scheduled_time'] # A string original para recalcular
    reminder_timezone_str = job_data['reminder_timezone'] # O timezone original

    chat_id = user_id # Por simplicidade, user_id é o chat_id para enviar mensagens privadas.

    try:
        # Busca a informação mais recente do lembrete do DB
        current_reminder_data = db.get_reminder_by_id(reminder_id, user_id)
        if not current_reminder_data or not current_reminder_data['ativo']:
            logger.info(f"Lembrete {reminder_id} não ativo ou não encontrado. Removendo job.")
            context.job.schedule_removal()
            return

        await context.bot.send_message(chat_id=chat_id, text=f"🔔 Lembrete: {escape_markdown(description, version=2)}", parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembrete ID {reminder_id} enviado para user {user_id}.")

        if recurrence and recurrence != 'none':
            # Certifique-se de que a scheduled_time tem fuso horário para o cálculo
            scheduled_time_dt = current_reminder_data['scheduled_time'] # Já vem com tz info do DB
            
            next_occurrence = calculate_next_occurrence(scheduled_time_dt, recurrence)

            if next_occurrence:
                # Atualiza o lembrete no DB com a nova scheduled_time
                db.update_reminder_scheduled_time(reminder_id, next_occurrence)
                
                # Reagenda o job para a próxima ocorrência
                context.job_queue.run_once(
                    send_reminder_job,
                    next_occurrence,
                    data={
                        'user_id': user_id,
                        'description': description,
                        'reminder_id': reminder_id,
                        'recurrence': recurrence,
                        'scheduled_time': next_occurrence.isoformat(), # Salva como ISO format
                        'reminder_timezone': reminder_timezone_str
                    },
                    name=f'reminder_{reminder_id}'
                )
                logger.info(f"Lembrete ID {reminder_id} reagendado para {next_occurrence} ({recurrence}).")
            else:
                # Se não há próxima ocorrência, desativa o lembrete e remove o job
                db.deactivate_reminder(reminder_id)
                context.job.schedule_removal()
                logger.info(f"Lembrete ID {reminder_id} desativado por não ter próxima ocorrência.")
        else:
            # Se não é recorrente, desativa e remove o job após enviar
            db.deactivate_reminder(reminder_id)
            context.job.schedule_removal()
            logger.info(f"Lembrete ID {reminder_id} não recorrente enviado. Job removido.")

    except Exception as e:
        logger.error(f"Erro ao enviar/reagendar lembrete ID {reminder_id} para user {user_id}: {e}")
        # Em caso de erro, remova o job para evitar loop infinito
        context.job.schedule_removal()


def schedule_existing_reminders(job_queue: JobQueue, bot: Bot) -> None:
    """Agenda todos os lembretes ativos existentes no banco de dados ao iniciar o bot."""
    # Como não temos um user_id aqui, precisamos buscar todos os lembretes ativos
    # para todos os usuários (ou de forma mais sofisticada, por usuário se o bot tiver muitos)
    
    # Esta função é chamada uma vez na inicialização do bot.
    # Ela precisa ser capaz de iterar sobre todos os lembretes ativos.
    
    # NOTA: O método get_active_reminders no seu db.py espera um user_id.
    # Precisaríamos de uma função em db.py como `get_all_active_reminders()`
    # se quisermos carregar todos os lembretes de todos os usuários.
    # Por enquanto, vou assumir que você tem um mecanismo para obter todos eles,
    # ou que para testes, você está focando em um único usuário.
    # Se precisar que eu adicione `get_all_active_reminders` em `db.py`, me avise!

    # Exemplo (adaptado se get_active_reminders for alterado ou se você iterar usuários)
    # Por enquanto, vou fazer um mock para demonstração, idealmente isto viria do DB
    # todos_os_lembretes_ativos = db.get_all_active_reminders() # <-- Esta função precisaria existir

    # Para fins de demonstração e para funcionar com o db.py atual, 
    # vou assumir que se o bot reiniciou, os lembretes serão reagendados quando o usuário interagir.
    # OU, se você tiver uma lista de todos os user_ids ativos, você poderia iterar:
    
    # Exemplo com um mock de lembretes, substitua pela chamada real ao DB
    # Lembretes reais devem ser carregados do banco de dados ao iniciar o bot
    all_reminders = db.get_all_reminders_for_scheduling()
    
    for reminder in all_reminders:
        user_id = reminder['user_id']
        description = reminder['description']
        scheduled_time = reminder['scheduled_time'] # datetime object com tzinfo
        recurrence = reminder['recurrence']
        reminder_id = reminder['id']
        reminder_timezone_str = reminder['reminder_timezone'] # String do fuso horário

        # Garante que a hora agendada é no futuro
        now_in_tz = datetime.datetime.now(scheduled_time.tzinfo)
        if scheduled_time < now_in_tz:
            # Se o lembrete já deveria ter disparado e é recorrente, calcula a próxima ocorrência
            if recurrence and recurrence != 'none':
                next_occurrence = calculate_next_occurrence(scheduled_time, recurrence)
                if next_occurrence:
                    scheduled_time = next_occurrence
                    db.update_reminder_scheduled_time(reminder_id, scheduled_time) # Atualiza no DB
                else:
                    db.deactivate_reminder(reminder_id) # Se não há próxima, desativa
                    logger.warning(f"Lembrete ID {reminder_id} no passado e sem próxima ocorrência válida. Desativado.")
                    continue # Pula para o próximo lembrete
            else:
                db.deactivate_reminder(reminder_id) # Se não recorrente e no passado, desativa
                logger.warning(f"Lembrete ID {reminder_id} no passado e não recorrente. Desativado.")
                continue # Pula para o próximo lembrete

        job_queue.run_once(
            send_reminder_job,
            scheduled_time,
            data={
                'user_id': user_id,
                'description': description,
                'reminder_id': reminder_id,
                'recurrence': recurrence,
                'scheduled_time': scheduled_time.isoformat(),
                'reminder_timezone': reminder_timezone_str
            },
            name=f'reminder_{reminder_id}' # Nome único para o job
        )
        logger.info(f"Lembrete ID {reminder_id} para user {user_id} reagendado para {scheduled_time}.")


# --- Handlers de Comando ---

async def add_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para adicionar um lembrete."""
    await update.message.reply_text(escape_markdown("Certo! O que você quer que eu te lembre?", version=2), parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Diálogo 'add_lembrete' iniciado por {update.effective_user.id}.")
    return GETTING_REMINDER_DESC

async def get_reminder_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a descrição do lembrete e pede a data/hora."""
    context.user_data['description'] = update.message.text
    await update.message.reply_text(
        escape_markdown("Quando você quer que eu te lembre? (Ex: 'amanhã 10h', '25/12/2025 14:30', 'em 5 minutos')", version=2),
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logger.info(f"Descrição do lembrete '{update.message.text}' recebida de {update.effective_user.id}.")
    return GETTING_REMINDER_DATETIME

async def get_reminder_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data/hora do lembrete e valida."""
    user_input = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Tenta fazer o parse da data/hora com fuso horário padrão (America/Sao_Paulo)
    try:
        # Usa o parser para flexibilidade. Assume o DEFAULT_TIMEZONE se não especificado.
        # now_with_tz = datetime.datetime.now(DEFAULT_TIMEZONE)
        # current_year = now_with_tz.year
        # current_month = now_with_tz.month
        # current_day = now_with_tz.day

        # Tentativa de parsear com parser.parse, que é mais robusto
        # Primeiro, tenta parsear com base no tempo atual no fuso horário do usuário (se definido) ou padrão
        now_in_default_tz = datetime.datetime.now(DEFAULT_TIMEZONE)
        parsed_dt = parser.parse(user_input, fuzzy=True, default=now_in_default_tz)

        # Se o parsed_dt ainda for naive (sem timezone), localiza com o default
        if parsed_dt.tzinfo is None:
            parsed_dt = DEFAULT_TIMEZONE.localize(parsed_dt)
        else:
            # Se já tem tzinfo, converte para o timezone padrão do bot (se necessário)
            parsed_dt = parsed_dt.astimezone(DEFAULT_TIMEZONE)

        # Se a data/hora parseada for no passado (e não for só o dia atual antes da hora atual)
        if parsed_dt < now_in_default_tz - timedelta(seconds=60): # Dando uma margem de 60s
            await update.message.reply_text(
                escape_markdown("Essa data/hora já passou. Por favor, forneça uma data/hora futura. 🕰️", version=2),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return GETTING_REMINDER_DATETIME

    except ValueError:
        await update.message.reply_text(
            escape_markdown("Não consegui entender a data/hora. Por favor, tente um formato como 'amanhã 10h', '25/12/2025 14:30' ou 'em 5 minutos'.", version=2),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Formato de data/hora inválido recebido de {user_id}: '{user_input}'.")
        return GETTING_REMINDER_DATETIME

    context.user_data['scheduled_time'] = parsed_dt
    context.user_data['reminder_timezone'] = str(DEFAULT_TIMEZONE) # Salva o fuso horário usado

    keyboard = [
        [InlineKeyboardButton("Sem Recorrência", callback_data="recurrence:none")],
        [InlineKeyboardButton("Diariamente", callback_data="recurrence:daily")],
        [InlineKeyboardButton("Semanalmente", callback_data="recurrence:weekly")],
        [InlineKeyboardButton("Mensalmente", callback_data="recurrence:monthly")],
        [InlineKeyboardButton("Anualmente", callback_data="recurrence:yearly")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        escape_markdown(f"Lembrete agendado para: `{parsed_dt.strftime('%d/%m/%Y %H:%M:%S %Z%z')}`.\\n"
                        "Com que frequência você quer que ele se repita?", version=2),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logger.info(f"Data/hora do lembrete '{parsed_dt}' recebida de {user_id}.")
    return GETTING_REMINDER_RECURRENCE

async def get_reminder_recurrence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a recorrência do lembrete e o salva."""
    query = update.callback_query
    await query.answer()

    recurrence = query.data.split(':')[1]
    user_id = update.effective_user.id
    description = context.user_data['description']
    scheduled_time = context.user_data['scheduled_time'] # datetime object com tzinfo
    reminder_timezone_str = context.user_data['reminder_timezone']

    reminder_id = db.insert_reminder(user_id, description, scheduled_time, recurrence, reminder_timezone_str)

    if reminder_id:
        # Agendar o job com python-telegram-bot's JobQueue
        context.job_queue.run_once(
            send_reminder_job,
            scheduled_time,
            data={
                'user_id': user_id,
                'description': description,
                'reminder_id': reminder_id,
                'recurrence': recurrence,
                'scheduled_time': scheduled_time.isoformat(), # Armazena como string ISO para JobData
                'reminder_timezone': reminder_timezone_str
            },
            name=f'reminder_{reminder_id}' # Nome único para o job
        )
        await query.edit_message_text(f"✅ Lembrete '{escape_markdown(description, version=2)}' agendado com sucesso! (ID: `{reminder_id}`)", parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembrete ID {reminder_id} adicionado e agendado por {user_id}.")
    else:
        await query.edit_message_text(escape_markdown("❌ Não foi possível agendar o lembrete. Tente novamente.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Falha ao adicionar lembrete para {user_id}. Desc: '{description}'.")

    context.user_data.clear()
    return ConversationHandler.END


async def view_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe todos os lembretes ativos do usuário."""
    user_id = update.effective_user.id
    reminders = db.get_active_reminders(user_id)

    if not reminders:
        await update.message.reply_text(escape_markdown("Você não tem nenhum lembrete ativo. Use /add_lembrete para adicionar um!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Nenhum lembrete ativo para {user_id}.")
        return

    message_text = "Seus lembretes ativos:\\n\\n"
    for r in reminders:
        # Formata a hora agendada para exibição no fuso horário do usuário/bot
        scheduled_time_display = r['scheduled_time'].astimezone(DEFAULT_TIMEZONE).strftime('%d/%m/%Y %H:%M:%S %Z%z')
        recurrence_text = f" (Recorrência: {r['recurrence']})" if r['recurrence'] and r['recurrence'] != 'none' else ""
        
        message_text += f"**ID:** `{r['id']}`\\n" \
                        f"**O que:** {escape_markdown(r['description'], version=2)}\\n" \
                        f"**Quando:** {escape_markdown(scheduled_time_display, version=2)}{escape_markdown(recurrence_text, version=2)}\\n\\n"
    
    message_text += escape_markdown("Use /apagar_lembrete <ID> para remover um.", version=2)

    await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Lembretes ativos exibidos para {user_id}.")


async def delete_reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o diálogo para apagar um lembrete."""
    args = context.args
    if not args:
        await update.message.reply_text(escape_markdown("Qual o ID do lembrete que você quer apagar? (Use /ver_lembretes para ver os IDs)", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_ID_FOR_DELETE
    
    try:
        reminder_id = int(args[0])
        user_id = update.effective_user.id
        
        # Opcional: Buscar detalhes do lembrete para confirmação mais robusta
        reminder_data = db.get_reminder_by_id(reminder_id, user_id)
        if not reminder_data:
            await update.message.reply_text(escape_markdown(f"❌ Lembrete ID `{reminder_id}` não encontrado ou não pertence a você.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            return ConversationHandler.END

        # Envia um teclado de confirmação
        keyboard = [
            [InlineKeyboardButton("✅ Sim, Apagar", callback_data=f"confirm_delete_reminder:{reminder_id}")],
            [InlineKeyboardButton("❌ Não, Cancelar", callback_data="cancel_reminder_delete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            escape_markdown(f"Tem certeza que deseja apagar o lembrete '`{reminder_data['description']}`' (ID: `{reminder_id}`)?", version=2),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return CONFIRM_DELETE_REMINDER # Vai para o estado de confirmação
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, digite um ID de lembrete válido (um número).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_ID_FOR_DELETE


async def confirm_delete_reminder_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma e apaga o lembrete com base no ID fornecido (se vier do input de texto)."""
    try:
        reminder_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text(escape_markdown("Por favor, digite um ID de lembrete válido (um número).", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        return GETTING_REMINDER_ID_FOR_DELETE

    user_id = update.effective_user.id
    
    # Remove o job do JobQueue (se existir)
    job_name = f'reminder_{reminder_id}'
    current_jobs = context.application.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
        logger.info(f"Job agendado '{job_name}' removido do JobQueue.")

    if db.delete_reminder(reminder_id, user_id):
        await update.message.reply_text(escape_markdown(f"🗑️ Lembrete ID `{reminder_id}` deletado com sucesso!", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Lembrete ID {reminder_id} deletado por {user_id}.")
    else:
        await update.message.reply_text(escape_markdown(f"❌ Não foi possível encontrar ou deletar o lembrete ID `{reminder_id}`. Verifique se o ID está correto ou use /ver_lembretes para ver seus IDs.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
        logger.warning(f"Falha ao deletar lembrete ID {reminder_id} para user {user_id}.")

    context.user_data.clear()
    return ConversationHandler.END


async def handle_reminder_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lida com as callbacks de confirmação ou cancelamento da exclusão de lembretes."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("confirm_delete_reminder:"):
        reminder_id = int(data.split(":")[1])
        user_id = query.from_user.id

        # Remove o job do JobQueue (se existir)
        job_name = f'reminder_{reminder_id}'
        current_jobs = context.application.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Job agendado '{job_name}' removido do JobQueue (via callback).")

        if db.delete_reminder(reminder_id, user_id):
            await query.edit_message_text(escape_markdown(f"🗑️ Lembrete ID `{reminder_id}` deletado com sucesso! 👍", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Lembrete ID {reminder_id} deletado por {user_id} (via callback).")
        else:
            await query.edit_message_text(escape_markdown(f"❌ Não foi possível encontrar ou deletar o lembrete ID `{reminder_id}`. Verifique se ele pertence a você.", version=2), parse_mode=ParseMode.MARKDOWN_V2)
            logger.warning(f"Falha ao deletar lembrete ID {reminder_id} por {user_id} (via callback).")

    elif data == "cancel_reminder_delete":
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
    
    logger.info(f"Diálogo de lembrete cancelado por {update.effective_user.id}.")
    context.user_data.clear()
    return ConversationHandler.END