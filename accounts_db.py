import sqlite3
import datetime
import logging

logger = logging.getLogger(__name__)

DATABASE_NAME = 'bot_database.db'

def init_accounts_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Tabela para contas mensais (despesas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monthly_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT NOT NULL, -- YYYY-MM-DD
            is_paid INTEGER DEFAULT 0, -- 0 for false, 1 for true
            recurrence TEXT DEFAULT 'none', -- 'none', 'indefinite', 'fixed_parcel'
            parcel_count INTEGER DEFAULT NULL, -- Total de parcelas para recurrence='fixed_parcel'
            current_parcel INTEGER DEFAULT 1, -- Parcela atual para recurrence='fixed_parcel'
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name, due_date, recurrence) ON CONFLICT REPLACE
        )
    ''')

    # Tabela para rendimentos financeiros
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS financial_incomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            income_date TEXT NOT NULL, -- YYYY-MM-DD
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, description, income_date) ON CONFLICT REPLACE
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("Tabelas de contas e rendimentos verificadas/criadas no banco de dados.")

def add_monthly_account(user_id, name, amount, due_date, recurrence='none', parcel_count=None, current_parcel=1):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            INSERT INTO monthly_accounts (user_id, name, amount, due_date, recurrence, parcel_count, current_parcel)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (user_id, name, amount, due_date, recurrence, parcel_count, current_parcel)
        )
        conn.commit()
        logger.info(f"Conta '{name}' adicionada para user_id {user_id}.")
        return True
    except sqlite3.IntegrityError as e:
        logger.error(f"Erro de integridade ao adicionar conta para user_id {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_user_monthly_accounts(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel FROM monthly_accounts WHERE user_id = ? ORDER BY due_date ASC',
        (user_id,)
    )
    accounts = cursor.fetchall()
    conn.close()
    return accounts

def get_monthly_account_by_id(account_id, user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel FROM monthly_accounts WHERE id = ? AND user_id = ?',
        (account_id, user_id)
    )
    account = cursor.fetchone()
    conn.close()
    return account

def update_monthly_account(account_id, user_id, **kwargs):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        set_clauses = []
        values = []
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)
        
        if not set_clauses:
            return False # Nenhuma coluna para atualizar

        query = f"UPDATE monthly_accounts SET {', '.join(set_clauses)} WHERE id = ? AND user_id = ?"
        values.append(account_id)
        values.append(user_id)
        
        cursor.execute(query, tuple(values))
        conn.commit()
        logger.info(f"Conta ID {account_id} atualizada para user_id {user_id}.")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar conta ID {account_id} para user_id {user_id}: {e}")
        return False
    finally:
        conn.close()

def update_monthly_account_status(account_id, user_id, is_paid):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'UPDATE monthly_accounts SET is_paid = ? WHERE id = ? AND user_id = ?',
            (1 if is_paid else 0, account_id, user_id)
        )
        conn.commit()
        logger.info(f"Status da conta ID {account_id} alterado para {is_paid} por user_id {user_id}.")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status da conta ID {account_id} para user_id {user_id}: {e}")
        return False
    finally:
        conn.close()

def delete_monthly_account(account_id, user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM monthly_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
        conn.commit()
        deleted_rows = cursor.rowcount
        if deleted_rows > 0:
            logger.info(f"Conta ID {account_id} deletada por user_id {user_id}.")
            return True
        else:
            logger.warning(f"Tentativa de deletar conta ID {account_id} falhou. Não encontrada ou não pertence a user_id {user_id}.")
            return False
    except Exception as e:
        logger.error(f"Erro ao deletar conta ID {account_id} para user_id {user_id}: {e}")
        return False
    finally:
        conn.close()

def add_financial_income(user_id, description, amount, income_date):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            INSERT INTO financial_incomes (user_id, description, amount, income_date)
            VALUES (?, ?, ?, ?)
            ''',
            (user_id, description, amount, income_date)
        )
        conn.commit()
        logger.info(f"Entrada '{description}' (R${amount}) adicionada para user_id {user_id}.")
        return True
    except sqlite3.IntegrityError as e:
        logger.error(f"Erro de integridade ao adicionar entrada para user_id {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_user_financial_incomes(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, description, amount, income_date FROM financial_incomes WHERE user_id = ? ORDER BY income_date DESC',
        (user_id,)
    )
    incomes = cursor.fetchall()
    conn.close()
    return incomes

def delete_financial_income(income_id, user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM financial_incomes WHERE id = ? AND user_id = ?', (income_id, user_id))
        conn.commit()
        deleted_rows = cursor.rowcount
        if deleted_rows > 0:
            logger.info(f"Entrada ID {income_id} deletada por user_id {user_id}.")
            return True
        else:
            logger.warning(f"Tentativa de deletar entrada ID {income_id} falhou. Não encontrada ou não pertence a user_id {user_id}.")
            return False
    except Exception as e:
        logger.error(f"Erro ao deletar entrada ID {income_id} para user_id {user_id}: {e}")
        return False
    finally:
        conn.close()


def get_monthly_summary(user_id, year, month):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Total de Entradas para o mês e ano especificados
    cursor.execute(
        '''
        SELECT SUM(amount) FROM financial_incomes
        WHERE user_id = ? AND STRFTIME('%Y', income_date) = ? AND STRFTIME('%m', income_date) = ?
        ''',
        (user_id, str(year), f'{month:02d}')
    )
    total_incomes = cursor.fetchone()[0] or 0.0

    # Total de todas as contas ATIVAS (não importa se pagas ou não) no mês
    # Uma conta é ativa se a due_date for no mês/ano, ou se for recorrente/parcelada e ainda não atingiu o parcel_count
    # Para simplificar, vamos considerar as contas com due_date no mês/ano ou contas recorrentes/parceladas que ainda não acabaram
    
    # Contas com vencimento no mês/ano OU
    # Contas recorrentes ('indefinite') OU
    # Contas parceladas ('fixed_parcel') onde current_parcel <= parcel_count
    cursor.execute(
        '''
        SELECT SUM(amount) FROM monthly_accounts
        WHERE user_id = ? AND (
            (STRFTIME('%Y', due_date) = ? AND STRFTIME('%m', due_date) = ?)
            OR recurrence = 'indefinite'
            OR (recurrence = 'fixed_parcel' AND current_parcel <= parcel_count)
        )
        ''',
        (user_id, str(year), f'{month:02d}')
    )
    total_accounts_due_this_month = cursor.fetchone()[0] or 0.0

    # Total de contas PAGAS no mês
    cursor.execute(
        '''
        SELECT SUM(amount) FROM monthly_accounts
        WHERE user_id = ? AND is_paid = 1 AND STRFTIME('%Y', due_date) = ? AND STRFTIME('%m', due_date) = ?
        ''',
        (user_id, str(year), f'{month:02d}')
    )
    paid_accounts_this_month = cursor.fetchone()[0] or 0.0

    # Total de contas A PAGAR no mês
    cursor.execute(
        '''
        SELECT SUM(amount) FROM monthly_accounts
        WHERE user_id = ? AND is_paid = 0 AND (
            (STRFTIME('%Y', due_date) = ? AND STRFTIME('%m', due_date) = ?)
            OR recurrence = 'indefinite'
            OR (recurrence = 'fixed_parcel' AND current_parcel <= parcel_count)
        )
        ''',
        (user_id, str(year), f'{month:02d}')
    )
    unpaid_accounts_this_month = cursor.fetchone()[0] or 0.0

    conn.close()

    # --- Lógica de Saldo ATUALIZADA ---
    # Saldo = Entradas - Total de Contas Ativas (Pagas ou Não)
    # Isso reflete que mesmo as contas pagas reduzem o saldo disponível.
    balance = total_incomes - total_accounts_due_this_month

    return {
        'total_incomes': total_incomes,
        'total_accounts_due_this_month': total_accounts_due_this_month,
        'paid_accounts_this_month': paid_accounts_this_month,
        'unpaid_accounts_this_month': unpaid_accounts_this_month,
        'balance': balance
    }

def get_pending_reminders():
    # Implementar lógica para buscar lembretes pendentes
    pass # Placeholder