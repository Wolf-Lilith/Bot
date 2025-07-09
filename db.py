import sqlite3
import logging
import datetime
import pytz
from datetime import timedelta
from dateutil import parser # Importado para parsing flexível de datas

# Use um logger específico para o módulo db para melhor rastreamento
logger = logging.getLogger(__name__)

DATABASE_NAME = 'lilith_bot.db' # Certifique-se de que o nome do seu banco é o mesmo

def create_tables():
    conn = None # Inicializa conn para None
    try:
        conn = sqlite3.connect(DATABASE_NAME) # Esta linha deve criar o arquivo se ele não existir
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS commands (
                command_name TEXT UNIQUE NOT NULL,
                function_name TEXT NOT NULL,
                description TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS personal_phrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                trigger_phrase TEXT NOT NULL,
                response_phrase TEXT NOT NULL,
                UNIQUE(user_id, trigger_phrase)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                list_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, list_name)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS list_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id INTEGER NOT NULL,
                item_text TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (list_id) REFERENCES lists(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                scheduled_time TEXT NOT NULL, -- Armazenar como ISO 8601 string (com UTC)
                recurrence TEXT, -- 'daily', 'weekly', 'monthly', 'yearly', ou NULL para não recorrente
                active INTEGER DEFAULT 1, -- 1 para ativo, 0 para inativo
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        logger.info("Tabelas verificadas/criadas no banco de dados.")
    except sqlite3.Error as e:
        logger.error(f"Erro de SQLite ao criar tabelas: {e}")
    except Exception as e:
        logger.error(f"Erro inesperado ao criar tabelas: {e}")
    finally:
        if conn:
            conn.close()

def insert_command(command_name, function_name, description):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO commands (command_name, function_name, description) VALUES (?, ?, ?)",
                       (command_name, function_name, description))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Comando '{command_name}' inserido no DB.")
        else:
            logger.info(f"Comando '{command_name}' verificado no DB.")
    except Exception as e:
        logger.error(f"Erro ao inserir/verificar comando '{command_name}': {e}")
    finally:
        conn.close()

# --- Funções para Frases Personalizadas ---
def add_personal_phrase(user_id, trigger, response):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO personal_phrases (user_id, trigger_phrase, response_phrase) VALUES (?, ?, ?)",
                       (user_id, trigger, response))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        logger.warning(f"Tentativa de adicionar frase duplicada para user {user_id} com trigger '{trigger}'.")
        return None # Indica que a frase já existe
    except Exception as e:
        logger.error(f"Erro ao adicionar frase personalizada para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def get_user_personal_phrases(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, trigger_phrase, response_phrase FROM personal_phrases WHERE user_id = ?", (user_id,))
        phrases = []
        for row in cursor.fetchall():
            phrases.append({'id': row[0], 'trigger_phrase': row[1], 'response_phrase': row[2]})
        return phrases
    except Exception as e:
        logger.error(f"Erro ao buscar frases personalizadas para user {user_id}: {e}")
        return []
    finally:
        conn.close()

def delete_personal_phrase(phrase_id, user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM personal_phrases WHERE id = ? AND user_id = ?", (phrase_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao deletar frase personalizada ID {phrase_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_response_for_trigger(user_id, trigger_phrase):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT response_phrase FROM personal_phrases WHERE user_id = ? AND trigger_phrase = ?",
                       (user_id, trigger_phrase))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Erro ao buscar resposta para trigger '{trigger_phrase}' de user {user_id}: {e}")
        return None
    finally:
        conn.close()

# --- Funções para Listas ---
def create_list(user_id, list_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO lists (user_id, list_name) VALUES (?, ?)", (user_id, list_name))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        logger.warning(f"Lista '{list_name}' já existe para o usuário {user_id}.")
        return None
    except Exception as e:
        logger.error(f"Erro ao criar lista para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def get_user_lists(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, list_name FROM lists WHERE user_id = ?", (user_id,))
        lists = []
        for row in cursor.fetchall():
            lists.append({'id': row[0], 'name': row[1]})
        return lists
    except Exception as e:
        logger.error(f"Erro ao buscar listas para user {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_list_name(list_id, user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT list_name FROM lists WHERE id = ? AND user_id = ?", (list_id, user_id))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Erro ao buscar nome da lista ID {list_id} para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def add_list_item(list_id, item_text):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO list_items (list_id, item_text) VALUES (?, ?)", (list_id, item_text))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Erro ao adicionar item à lista ID {list_id}: {e}")
        return None
    finally:
        conn.close()

def get_list_items(list_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, item_text, is_completed FROM list_items WHERE list_id = ?", (list_id,))
        items = []
        for row in cursor.fetchall():
            items.append({'id': row[0], 'text': row[1], 'completed': bool(row[2])})
        return items
    except Exception as e:
        logger.error(f"Erro ao buscar itens para lista ID {list_id}: {e}")
        return []
    finally:
        conn.close()

def toggle_list_item_status(item_id, list_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE list_items SET is_completed = 1 - is_completed WHERE id = ? AND list_id = ?", (item_id, list_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao alternar status do item ID {item_id} da lista ID {list_id}: {e}")
        return False
    finally:
        conn.close()

def remove_list_item(item_id, list_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM list_items WHERE id = ? AND list_id = ?", (item_id, list_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao remover item ID {item_id} da lista ID {list_id}: {e}")
        return False
    finally:
        conn.close()

def delete_list(list_id, user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        # A cascade delete na criação da tabela garante que os itens são apagados
        cursor.execute("DELETE FROM lists WHERE id = ? AND user_id = ?", (list_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao deletar lista ID {list_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()

# --- Funções para Lembretes ---
def add_reminder(user_id, description, scheduled_time, recurrence=None):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        # Garante que scheduled_time é uma string ISO formatada (UTC)
        if isinstance(scheduled_time, datetime.datetime):
            if scheduled_time.tzinfo is None:
                # Assume UTC se for naive, ou use seu DEFAULT_TIMEZONE
                scheduled_time = pytz.utc.localize(scheduled_time)
            scheduled_time_iso = scheduled_time.astimezone(pytz.utc).isoformat()
        else:
            scheduled_time_iso = scheduled_time # Já deve vir como string ISO, mas bom garantir

        cursor.execute(
            "INSERT INTO reminders (user_id, description, scheduled_time, recurrence) VALUES (?, ?, ?, ?)",
            (user_id, description, scheduled_time_iso, recurrence)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Erro ao adicionar lembrete para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def get_all_reminders_for_scheduling():
    """Retorna todos os lembretes ativos para serem agendados na inicialização do bot."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, user_id, description, scheduled_time, recurrence FROM reminders WHERE active = 1")
        reminders = []
        for row in cursor.fetchall():
            # Converte a string ISO de volta para datetime aware
            scheduled_time_dt = parser.parse(row[3])
            # Se a string ISO não tem fuso, assume UTC (como salvamos)
            if scheduled_time_dt.tzinfo is None:
                scheduled_time_dt = pytz.utc.localize(scheduled_time_dt)
            reminders.append({
                'id': row[0],
                'user_id': row[1],
                'description': row[2],
                'scheduled_time': scheduled_time_dt,
                'recurrence': row[4]
            })
        return reminders
    except Exception as e:
        logger.error(f"Erro ao buscar todos os lembretes para agendamento: {e}")
        return []
    finally:
        conn.close()

def get_reminder_by_id(reminder_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, user_id, description, scheduled_time, recurrence, active FROM reminders WHERE id = ?", (reminder_id,))
        result = cursor.fetchone()
        if result:
            scheduled_time_dt = parser.parse(result[3])
            if scheduled_time_dt.tzinfo is None:
                scheduled_time_dt = pytz.utc.localize(scheduled_time_dt) # Assume UTC se for naive
            return {
                'id': result[0],
                'user_id': result[1],
                'description': result[2],
                'scheduled_time': scheduled_time_dt,
                'recurrence': result[4],
                'active': bool(result[5])
            }
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar lembrete ID {reminder_id}: {e}")
        return None
    finally:
        conn.close()

def deactivate_reminder(reminder_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE reminders SET active = 0 WHERE id = ?", (reminder_id,))
        conn.commit()
        logger.info(f"Lembrete ID {reminder_id} desativado.")
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao desativar lembrete ID {reminder_id}: {e}")
        return False
    finally:
        conn.close()

def update_reminder_scheduled_time(reminder_id, new_scheduled_time_dt: datetime.datetime):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        if new_scheduled_time_dt.tzinfo is None:
            # Se for 'naive', assume UTC para salvar, ou use seu DEFAULT_TIMEZONE se for o caso
            # Idealmente, a data já virá 'aware' do handler.
            new_scheduled_time_dt = pytz.utc.localize(new_scheduled_time_dt)
        
        # Converte para UTC e salva como ISO format string para consistência
        scheduled_time_iso = new_scheduled_time_dt.astimezone(pytz.utc).isoformat()

        cursor.execute(
            "UPDATE reminders SET scheduled_time = ? WHERE id = ?",
            (scheduled_time_iso, reminder_id)
        )
        conn.commit()
        logger.info(f"Scheduled time para lembrete ID {reminder_id} atualizado para {scheduled_time_iso}.")
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao atualizar scheduled_time para lembrete ID {reminder_id}: {e}")
        return False
    finally:
        conn.close()

# --- NOVA FUNÇÃO: is_reminder_active ---
def is_reminder_active(reminder_id):
    """Verifica se um lembrete está ativo no banco de dados."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT active FROM reminders WHERE id = ?", (reminder_id,))
        result = cursor.fetchone()
        return result[0] == 1 if result else False
    except Exception as e:
        logger.error(f"Erro ao verificar se lembrete ID {reminder_id} está ativo: {e}")
        return False
    finally:
        conn.close()

# --- NOVO: Função para obter lembretes ativos de um usuário específico ---
def get_active_reminders(user_id):
    """Retorna todos os lembretes ativos para um usuário específico."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, description, scheduled_time, recurrence FROM reminders WHERE user_id = ? AND active = 1 ORDER BY scheduled_time ASC", (user_id,))
        reminders = []
        for row in cursor.fetchall():
            scheduled_time_dt = parser.parse(row[2])
            if scheduled_time_dt.tzinfo is None:
                scheduled_time_dt = pytz.utc.localize(scheduled_time_dt) # Assume UTC se for naive
            reminders.append({
                'id': row[0],
                'description': row[1],
                'scheduled_time': scheduled_time_dt,
                'recurrence': row[3]
            })
        return reminders
    except Exception as e:
        logger.error(f"Erro ao buscar lembretes ativos para user {user_id}: {e}")
        return []
    finally:
        conn.close()

def delete_reminder(reminder_id, user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao deletar lembrete ID {reminder_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()