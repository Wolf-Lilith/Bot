# db.py

import sqlite3
import logging
import datetime
import pytz
from datetime import timedelta
from dateutil import parser # Importado para parsing flexível de datas

# Use um logger específico para o módulo db para melhor rastreamento
logger = logging.getLogger(__name__)

# Nome do banco de dados unificado
DATABASE_NAME = 'lilith_bot.db' 

def create_tables():
    """Cria as tabelas necessárias no banco de dados se elas não existirem."""
    conn = None # Inicializa conn para None
    try:
        conn = sqlite3.connect(DATABASE_NAME) # Esta linha deve criar o arquivo se ele não existir
        cursor = conn.cursor()

        # Tabela para registrar comandos do bot
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS commands (
                command_name TEXT UNIQUE NOT NULL,
                function_name TEXT NOT NULL,
                description TEXT
            )
        ''')

        # Tabela para frases personalizadas do usuário
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS personal_phrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                trigger_phrase TEXT NOT NULL,
                response_phrase TEXT NOT NULL,
                UNIQUE(user_id, trigger_phrase) ON CONFLICT REPLACE
            )
        ''')

        # Tabela para listas de usuário
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                list_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, list_name) ON CONFLICT REPLACE
            )
        ''')

        # Tabela para itens dentro das listas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS list_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id INTEGER NOT NULL,
                item_text TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0, -- 0 for false, 1 for true
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (list_id) REFERENCES lists(id) ON DELETE CASCADE
            )
        ''')

        # Tabela para lembretes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                scheduled_time TEXT NOT NULL, -- ISO format string (YYYY-MM-DD HH:MM:SS+00:00)
                recurrence TEXT DEFAULT 'none', -- 'none', 'daily', 'weekly', 'monthly', 'yearly'
                active INTEGER DEFAULT 1, -- 1 for active, 0 for inactive
                job_id TEXT UNIQUE, -- ID do job no JobQueue para fácil cancelamento/rastreamento
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        logger.info("Tabelas do banco de dados criadas ou já existentes.")
    except sqlite3.Error as e:
        logger.error(f"Erro ao criar tabelas: {e}")
    finally:
        if conn:
            conn.close()

# --- Funções para Comandos ---
def insert_command(command_name, function_name, description=None):
    """Insere um novo comando no banco de dados se ele não existir."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO commands (command_name, function_name, description) VALUES (?, ?, ?)",
                       (command_name, function_name, description))
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Comando '{command_name}' inserido no DB.")
        else:
            logger.debug(f"Comando '{command_name}' já existe no DB.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Erro ao inserir comando '{command_name}': {e}")
        return False
    finally:
        conn.close()

def get_all_commands():
    """Retorna todos os comandos registrados no banco de dados."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT command_name, description FROM commands ORDER BY command_name")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar todos os comandos: {e}")
        return []
    finally:
        conn.close()

# --- Funções para Frases Personalizadas ---
def add_personal_phrase(user_id, trigger_phrase, response_phrase):
    """Adiciona uma nova frase personalizada para um usuário."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO personal_phrases (user_id, trigger_phrase, response_phrase) VALUES (?, ?, ?)",
                       (user_id, trigger_phrase, response_phrase))
        conn.commit()
        return True
    except sqlite3.IntegrityError: # Captura erro de UNIQUE constraint
        logger.warning(f"Frase '{trigger_phrase}' já existe para user {user_id}. Não adicionado.")
        return False
    except Exception as e:
        logger.error(f"Erro ao adicionar frase personalizada: {e}")
        return False
    finally:
        conn.close()

def get_user_personal_phrases(user_id):
    """Retorna todas as frases personalizadas de um usuário."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, trigger_phrase, response_phrase FROM personal_phrases WHERE user_id = ? ORDER BY trigger_phrase", (user_id,))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro ao buscar frases personalizadas para user {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_response_for_trigger(user_id, trigger_phrase):
    """Retorna a frase de resposta para um gatilho específico de um usuário."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT response_phrase FROM personal_phrases WHERE user_id = ? AND trigger_phrase = ?",
                       (user_id, trigger_phrase))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Erro ao buscar resposta para gatilho '{trigger_phrase}' de user {user_id}: {e}")
        return None
    finally:
        conn.close()

def delete_personal_phrase(phrase_id, user_id):
    """Apaga uma frase personalizada pelo ID para um usuário específico."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM personal_phrases WHERE id = ? AND user_id = ?", (phrase_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao deletar frase ID {phrase_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()

# --- Funções para Listas ---
def add_list(user_id, list_name):
    """Adiciona uma nova lista para um usuário."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO lists (user_id, list_name) VALUES (?, ?)", (user_id, list_name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Lista '{list_name}' já existe para user {user_id}. Não adicionada.")
        return False
    except Exception as e:
        logger.error(f"Erro ao adicionar lista: {e}")
        return False
    finally:
        conn.close()

def get_user_lists(user_id):
    """Retorna todas as listas de um usuário."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, list_name FROM lists WHERE user_id = ? ORDER BY list_name", (user_id,))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro ao buscar listas para user {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_list_by_name(user_id, list_name):
    """Retorna o ID e nome de uma lista pelo nome para um usuário específico."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, list_name FROM lists WHERE user_id = ? AND list_name = ?", (user_id, list_name))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Erro ao buscar lista '{list_name}' para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def get_list_by_id(list_id, user_id):
    """Retorna o ID e nome de uma lista pelo ID para um usuário específico."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, list_name FROM lists WHERE id = ? AND user_id = ?", (list_id, user_id))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Erro ao buscar lista ID {list_id} para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def add_list_item(list_id, item_text):
    """Adiciona um item a uma lista."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO list_items (list_id, item_text) VALUES (?, ?)", (list_id, item_text))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar item '{item_text}' à lista {list_id}: {e}")
        return False
    finally:
        conn.close()

def get_list_items(list_id):
    """Retorna todos os itens de uma lista."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, item_text, is_completed FROM list_items WHERE list_id = ? ORDER BY created_at", (list_id,))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro ao buscar itens para lista {list_id}: {e}")
        return []
    finally:
        conn.close()

def toggle_list_item(item_id, list_id):
    """Alterna o status de conclusão de um item da lista."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE list_items SET is_completed = (CASE WHEN is_completed = 0 THEN 1 ELSE 0 END) WHERE id = ? AND list_id = ?", (item_id, list_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao alternar item ID {item_id} da lista {list_id}: {e}")
        return False
    finally:
        conn.close()

def remove_list_item(item_id, list_id):
    """Remove um item de uma lista."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM list_items WHERE id = ? AND list_id = ?", (item_id, list_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao remover item ID {item_id} da lista {list_id}: {e}")
        return False
    finally:
        conn.close()

def delete_list(list_id, user_id):
    """Apaga uma lista e todos os seus itens."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        # A FOREIGN KEY com ON DELETE CASCADE em list_items garante que os itens sejam apagados automaticamente
        cursor.execute("DELETE FROM lists WHERE id = ? AND user_id = ?", (list_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao deletar lista ID {list_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()


# --- Funções para Lembretes ---
def add_reminder(user_id, description, scheduled_time, recurrence, job_id=None):
    """Adiciona um novo lembrete."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO reminders (user_id, description, scheduled_time, recurrence, job_id) VALUES (?, ?, ?, ?, ?)",
                       (user_id, description, scheduled_time.isoformat(), recurrence, job_id))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        logger.warning(f"Job ID '{job_id}' para lembrete já existe. Não adicionado.")
        return None
    except Exception as e:
        logger.error(f"Erro ao adicionar lembrete para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def update_reminder_scheduled_time(reminder_id, new_scheduled_time, new_job_id=None):
    """Atualiza a próxima data/hora de agendamento de um lembrete e opcionalmente o job_id."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        if new_job_id:
            cursor.execute("UPDATE reminders SET scheduled_time = ?, job_id = ? WHERE id = ?",
                           (new_scheduled_time.isoformat(), new_job_id, reminder_id))
        else:
            cursor.execute("UPDATE reminders SET scheduled_time = ? WHERE id = ?",
                           (new_scheduled_time.isoformat(), reminder_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao atualizar scheduled_time para lembrete ID {reminder_id}: {e}")
        return False
    finally:
        conn.close()

def deactivate_reminder(reminder_id):
    """Desativa um lembrete (define active para 0)."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE reminders SET active = 0 WHERE id = ?", (reminder_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao desativar lembrete ID {reminder_id}: {e}")
        return False
    finally:
        conn.close()

def get_user_reminders(user_id):
    """Retorna todos os lembretes (ativos e inativos) para um usuário específico."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, description, scheduled_time, recurrence, active FROM reminders WHERE user_id = ? ORDER BY scheduled_time ASC", (user_id,))
        reminders = []
        for row in cursor.fetchall():
            # Converte a string ISO de volta para objeto datetime
            scheduled_time_dt = parser.parse(row[2])
            reminders.append({
                'id': row[0],
                'description': row[1],
                'scheduled_time': scheduled_time_dt,
                'recurrence': row[3],
                'active': bool(row[4])
            })
        return reminders
    except Exception as e:
        logger.error(f"Erro ao buscar lembretes para user {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_active_reminders(user_id=None):
    """Retorna todos os lembretes ativos (de todos os usuários ou de um específico)."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        query = "SELECT id, user_id, description, scheduled_time, recurrence, job_id FROM reminders WHERE active = 1"
        params = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY scheduled_time ASC"

        cursor.execute(query, tuple(params))
        reminders = []
        for row in cursor.fetchall():
            scheduled_time_dt = parser.parse(row[3])
            if scheduled_time_dt.tzinfo is None:
                # Se não tem fuso horário, assume que é UTC (o que o JobQueue espera por padrão)
                scheduled_time_dt = pytz.utc.localize(scheduled_time_dt)
            reminders.append({
                'id': row[0],
                'user_id': row[1],
                'description': row[2],
                'scheduled_time': scheduled_time_dt,
                'recurrence': row[4],
                'job_id': row[5]
            })
        return reminders
    except Exception as e:
        logger.error(f"Erro ao buscar lembretes ativos: {e}")
        return []
    finally:
        conn.close()

def delete_reminder(reminder_id, user_id):
    """Deleta um lembrete pelo ID para um usuário específico."""
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