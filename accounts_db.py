# accounts_db.py

import sqlite3
import datetime
import logging

logger = logging.getLogger(__name__)

# Nome do banco de dados unificado
DATABASE_NAME = 'lilith_bot.db' # UNIFICADO: Agora usa o mesmo DB que 'db.py'

def init_accounts_db():
    """Inicializa as tabelas para gerenciamento de contas financeiras."""
    conn = None
    try:
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
        logger.info("Tabelas de contas financeiras criadas ou já existentes.")
    except sqlite3.Error as e:
        logger.error(f"Erro ao criar tabelas de contas: {e}")
    finally:
        if conn:
            conn.close()

def add_monthly_account(user_id, name, amount, due_date, recurrence='none', parcel_count=None, current_parcel=1):
    """Adiciona uma nova conta mensal (despesa)."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO monthly_accounts (user_id, name, amount, due_date, recurrence, parcel_count, current_parcel) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, amount, due_date, recurrence, parcel_count, current_parcel)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Conta '{name}' para user {user_id} e data {due_date} já existe. Não adicionada.")
        return False
    except Exception as e:
        logger.error(f"Erro ao adicionar conta mensal: {e}")
        return False
    finally:
        conn.close()

def get_monthly_accounts(user_id, month=None, year=None):
    """Retorna as contas mensais de um usuário, opcionalmente filtradas por mês e ano."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        query = "SELECT id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel FROM monthly_accounts WHERE user_id = ?"
        params = [user_id]
        
        # Filtra por mês e ano para contas não recorrentes ou contas recorrentes em parcelas (considera a parcela atual)
        # Contas recorrentes "indefinite" são sempre incluídas, independentemente da data de vencimento.
        if month and year:
            query += """
                AND (
                    (STRFTIME('%Y', due_date) = ? AND STRFTIME('%m', due_date) = ?)
                    OR recurrence = 'indefinite'
                    OR (recurrence = 'fixed_parcel' AND current_parcel <= parcel_count)
                )
            """
            params.extend([str(year), f'{month:02d}'])

        query += " ORDER BY due_date, name"
        
        cursor.execute(query, tuple(params))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro ao buscar contas mensais para user {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_account_by_id(account_id, user_id):
    """Retorna uma conta específica pelo ID e user_id."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, name, amount, due_date, is_paid, recurrence, parcel_count, current_parcel FROM monthly_accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id)
        )
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Erro ao buscar conta ID {account_id} para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def mark_account_paid(account_id, user_id):
    """Marca uma conta como paga."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE monthly_accounts SET is_paid = 1 WHERE id = ? AND user_id = ?",
            (account_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao marcar conta ID {account_id} como paga para user {user_id}: {e}")
        return False
    finally:
        conn.close()

def delete_monthly_account(account_id, user_id):
    """Deleta uma conta mensal."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM monthly_accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao deletar conta ID {account_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()

def add_financial_income(user_id, description, amount, income_date):
    """Adiciona um novo rendimento financeiro."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO financial_incomes (user_id, description, amount, income_date) VALUES (?, ?, ?, ?)",
            (user_id, description, amount, income_date)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Entrada de renda '{description}' para user {user_id} e data {income_date} já existe. Não adicionada.")
        return False
    except Exception as e:
        logger.error(f"Erro ao adicionar rendimento financeiro: {e}")
        return False
    finally:
        conn.close()

def get_financial_incomes(user_id, month=None, year=None):
    """Retorna os rendimentos financeiros de um usuário, opcionalmente filtrados por mês e ano."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        query = "SELECT id, description, amount, income_date FROM financial_incomes WHERE user_id = ?"
        params = [user_id]
        if month and year:
            query += " AND STRFTIME('%Y', income_date) = ? AND STRFTIME('%m', income_date) = ?"
            params.extend([str(year), f'{month:02d}'])
        query += " ORDER BY income_date DESC"
        cursor.execute(query, tuple(params))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro ao buscar rendimentos para user {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_income_by_id(income_id, user_id):
    """Retorna uma entrada de renda específica pelo ID e user_id."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, description, amount, income_date FROM financial_incomes WHERE id = ? AND user_id = ?",
            (income_id, user_id)
        )
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Erro ao buscar entrada ID {income_id} para user {user_id}: {e}")
        return None
    finally:
        conn.close()

def delete_financial_income(income_id, user_id):
    """Deleta um rendimento financeiro."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM financial_incomes WHERE id = ? AND user_id = ?",
            (income_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Erro ao deletar rendimento ID {income_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_financial_summary(user_id, month, year):
    """Calcula o resumo financeiro para um mês e ano específicos, incluindo recorrência."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Total de rendimentos no mês
    cursor.execute(
        '''
        SELECT SUM(amount) FROM financial_incomes
        WHERE user_id = ? AND STRFTIME('%Y', income_date) = ? AND STRFTIME('%m', income_date) = ?
        ''',
        (user_id, str(year), f'{month:02d}')
    )
    total_incomes = cursor.fetchone()[0] or 0.0

    # Total de contas a pagar (considerando vencimento ou recorrência para o mês)
    # Inclui contas com due_date no mês/ano OU recorrentes indefinidas OU parceladas que ainda não acabaram
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