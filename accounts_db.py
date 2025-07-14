import sqlite3
import datetime
import logging
import calendar

logger = logging.getLogger(__name__)

DATABASE_NAME = 'lilith_bot.db'

def init_accounts_db():
    """Inicializa as tabelas para gerenciamento de contas financeiras."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        # Tabela para modelos de contas (para recorrência e parcelas)
        logger.debug("Tentando criar tabela 'account_templates'...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                due_date_base TEXT NOT NULL, -- YYYY-MM-DD
                recurrence TEXT DEFAULT 'none', -- 'none', 'indefinite', 'fixed_parcel'
                parcel_count INTEGER DEFAULT NULL, -- Total de parcelas para recurrence='fixed_parcel'
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name, recurrence, due_date_base)
            )
        ''')
        logger.debug("Tabela 'account_templates' criada ou já existente.")

        # Tabela para as INSTÂNCIAS mensais das contas (despesas)
        logger.debug("Tentando criar tabela 'monthly_account_instances'...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monthly_account_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                template_id INTEGER, -- FK para account_templates, NULL para contas não recorrentes
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                due_date TEXT NOT NULL, -- YYYY-MM-DD (Data de vencimento desta instância)
                month INTEGER NOT NULL, -- Mês da instância
                year INTEGER NOT NULL, -- Ano da instância
                is_paid INTEGER DEFAULT 0, -- 0 for false, 1 for true (para esta instância mensal)
                recurrence_type TEXT DEFAULT 'none', -- 'none', 'indefinite', 'fixed_parcel' (tipo para esta instância)
                current_parcel INTEGER DEFAULT NULL, -- Parcela atual para esta instância (se for fixed_parcel)
                total_parcels INTEGER DEFAULT NULL, -- Total de parcelas (para exibir)
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name, month, year, template_id), 
                FOREIGN KEY (template_id) REFERENCES account_templates(id)
            )
        ''')
        logger.debug("Tabela 'monthly_account_instances' criada ou já existente.")

        # Tabela para registrar instâncias de contas recorrentes que foram removidas para um mês específico
        logger.debug("Tentando criar tabela 'ignored_monthly_instances'...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ignored_monthly_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                template_id INTEGER NOT NULL, -- FK para account_templates
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, template_id, month, year),
                FOREIGN KEY (template_id) REFERENCES account_templates(id)
            )
        ''')
        logger.debug("Tabela 'ignored_monthly_instances' criada ou já existente.")

        # Tabela para rendimentos financeiros
        logger.debug("Tentando criar tabela 'financial_incomes'...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_incomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                income_date TEXT NOT NULL, -- YYYY-MM-DD
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, description, income_date) 
            )
        ''')
        logger.debug("Tabela 'financial_incomes' criada ou já existente.")

        conn.commit()
        logger.info("Tabelas de contas financeiras e templates criadas ou já existentes com sucesso.")
    except sqlite3.Error as e:
        logger.error(f"Erro CRÍTICO ao criar tabelas de contas: {e}")
    finally:
        if conn:
            conn.close()
            logger.debug("Conexão com o banco de dados fechada após init.")

# NOVO: Função para adicionar uma entrada na tabela de instâncias ignoradas
def _add_ignored_monthly_instance(user_id: int, template_id: int, month: int, year: int):
    """Registra uma instância de conta recorrente como ignorada para um mês específico."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Adicionando instância ignorada: user_id={user_id}, template_id={template_id}, month={month}, year={year}")
        cursor.execute(
            """
            INSERT INTO ignored_monthly_instances (user_id, template_id, month, year)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, template_id, month, year)
        )
        conn.commit()
        logger.info(f"Instância para template {template_id} em {month}/{year} marcada como ignorada para user {user_id}.")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Instância para template {template_id} em {month}/{year} já estava marcada como ignorada para user {user_id}.")
        return False
    except Exception as e:
        logger.error(f"Erro ao adicionar instância ignorada para template {template_id} em {month}/{year} (user {user_id}): {e}")
        return False
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após _add_ignored_monthly_instance.")

# NOVO: Função para remover uma entrada da tabela de instâncias ignoradas (se for o caso de reativar no futuro)
def _remove_ignored_monthly_instance(user_id: int, template_id: int, month: int, year: int):
    """Remove o registro de uma instância ignorada para um mês específico."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Removendo instância ignorada: user_id={user_id}, template_id={template_id}, month={month}, year={year}")
        cursor.execute(
            """
            DELETE FROM ignored_monthly_instances
            WHERE user_id = ? AND template_id = ? AND month = ? AND year = ?
            """,
            (user_id, template_id, month, year)
        )
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Instância para template {template_id} em {month}/{year} removida da lista de ignoradas para user {user_id}.")
            return True
        else:
            logger.warning(f"Instância para template {template_id} em {month}/{year} não encontrada na lista de ignoradas para user {user_id}.")
            return False
    except Exception as e:
        logger.error(f"Erro ao remover instância ignorada para template {template_id} em {month}/{year} (user {user_id}): {e}")
        return False
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após _remove_ignored_monthly_instance.")

# NOVO: Função para verificar se uma instância de template deve ser ignorada para um mês
def _is_monthly_instance_ignored(user_id: int, template_id: int, month: int, year: int) -> bool:
    """Verifica se uma instância de conta recorrente foi marcada para ser ignorada para um mês específico."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 1 FROM ignored_monthly_instances
            WHERE user_id = ? AND template_id = ? AND month = ? AND year = ?
            """,
            (user_id, template_id, month, year)
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Erro ao verificar se instância é ignorada para template {template_id} em {month}/{year} (user {user_id}): {e}")
        return False
    finally:
        conn.close()


def _add_account_template(user_id, name, amount, due_date_base, recurrence='none', parcel_count=None):
    """Adiciona um NOVO MODELO de conta (template)."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Adicionando template: user_id={user_id}, name='{name}', amount={amount}, due_date_base='{due_date_base}', recurrence='{recurrence}', parcel_count={parcel_count}")
        cursor.execute(
            "INSERT INTO account_templates (user_id, name, amount, due_date_base, recurrence, parcel_count) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, amount, due_date_base, recurrence, parcel_count)
        )
        conn.commit()
        template_id = cursor.lastrowid
        logger.info(f"Template de conta '{name}' (ID: {template_id}) adicionado para user {user_id}.")
        return template_id
    except sqlite3.IntegrityError:
        logger.warning(f"Template de conta '{name}' para user {user_id} já existe. Tentando retornar ID existente.")
        cursor.execute(
            "SELECT id FROM account_templates WHERE user_id = ? AND name = ? AND recurrence = ? AND due_date_base = ?",
            (user_id, name, recurrence, due_date_base)
        )
        existing_id = cursor.fetchone()
        if existing_id:
            logger.debug(f"ID existente para template '{name}': {existing_id[0]}.")
            return existing_id[0]
        else:
            logger.error(f"Erro de integridade, mas não encontrou template existente para '{name}'.")
            return None
    except Exception as e:
        logger.error(f"Erro ao adicionar template de conta para '{name}' (user {user_id}): {e}")
        return None
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após _add_account_template.")

def _add_monthly_account_instance(user_id, name, amount, due_date, month, year, is_paid=0, recurrence_type='none', template_id=None, current_parcel=None, total_parcels=None):
    """Adiciona uma INSTÂNCIA mensal de conta na tabela monthly_account_instances."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Adicionando instância: user_id={user_id}, name='{name}', amount={amount}, due_date='{due_date}', month={month}, year={year}, is_paid={is_paid}, recurrence_type='{recurrence_type}', template_id={template_id}, current_parcel={current_parcel}, total_parcels={total_parcels}")
        cursor.execute(
            """
            INSERT INTO monthly_account_instances (user_id, template_id, name, amount, due_date, month, year, is_paid, recurrence_type, current_parcel, total_parcels)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, template_id, name, amount, due_date, month, year, is_paid, recurrence_type, current_parcel, total_parcels)
        )
        conn.commit()
        logger.info(f"Instância de conta '{name}' para {month}/{year} adicionada com sucesso para user {user_id}.")
        return True
    except sqlite3.IntegrityError: # Tratamento específico para IntegrityError
        logger.warning(f"Instância de conta '{name}' para {month}/{year} já existe para user {user_id}. Não inserindo novamente.")
        return False
    except Exception as e:
        logger.error(f"Erro ao adicionar instância mensal de conta para '{name}' em {month}/{year} (user {user_id}): {e}")
        return False
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após _add_monthly_account_instance.")

# CORREÇÃO NA DEFINIÇÃO DA FUNÇÃO: O 'current_parcel_template=1' é um detalhe interno para o _add_monthly_account_instance,
# não para a função pública add_monthly_account.
def add_monthly_account(user_id, name, amount, due_date, recurrence='none', parcel_count=None):
    """
    Adiciona uma nova conta.
    Se for recorrente ou parcelada, adiciona um template e gera a primeira instância.
    Se não for recorrente, adiciona diretamente como uma instância única.
    """
    logger.debug(f"Iniciando add_monthly_account para user {user_id}, nome='{name}', valor={amount}, data='{due_date}', recorrência='{recurrence}', parcelas={parcel_count}")
    due_date_dt = datetime.datetime.strptime(due_date, '%Y-%m-%d').date()
    month = due_date_dt.month
    year = due_date_dt.year
    
    if recurrence == 'none':
        # Para contas não recorrentes, adiciona diretamente uma instância
        logger.debug("Conta não recorrente. Adicionando instância única.")
        return _add_monthly_account_instance(user_id, name, amount, due_date, month, year, is_paid=0, recurrence_type='none')
    else:
        # Para contas recorrentes ou parceladas, adiciona/recupera o template
        logger.debug(f"Conta recorrente/parcelada. Adicionando/recuperando template.")
        template_id = _add_account_template(user_id, name, amount, due_date, recurrence, parcel_count)
        if template_id is None:
            logger.error(f"Falha ao obter template_id para '{name}'.")
            return False
        
        # Gera a instância para o mês/ano da due_date_base
        # Se for parcelada, current_parcel é 1 para a primeira instância criada aqui.
        current_parcel_val = 1 if recurrence == 'fixed_parcel' else None
        total_parcels_val = parcel_count if recurrence == 'fixed_parcel' else None

        logger.debug(f"Template ID {template_id} obtido. Gerando primeira instância.")
        return _add_monthly_account_instance(user_id, name, amount, due_date, month, year, 
                                             is_paid=0, recurrence_type=recurrence, template_id=template_id, 
                                             current_parcel=current_parcel_val, total_parcels=total_parcels_val)

def _generate_monthly_account_instances(user_id: int, month: int, year: int):
    """
    Gera instâncias de contas recorrentes (indefinite e fixed_parcel)
    para o mês e ano especificados, se ainda não existirem.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Gerando instâncias para user {user_id}, mês {month}/{year}.")
        # Busca templates de contas que são recorrentes ou parceladas
        cursor.execute(
            """
            SELECT id, name, amount, due_date_base, recurrence, parcel_count
            FROM account_templates
            WHERE user_id = ? AND (recurrence = 'indefinite' OR recurrence = 'fixed_parcel')
            """,
            (user_id,)
        )
        templates = cursor.fetchall()
        logger.debug(f"Encontrados {len(templates)} templates recorrentes para user {user_id}.")

        current_month_date = datetime.date(year, month, 1)

        for t_id, t_name, t_amount, t_due_date_base, t_recurrence, t_parcel_count in templates:
            logger.debug(f"Processando template ID: {t_id}, Nome: '{t_name}'.")
            
            try:
                template_start_date_dt = datetime.datetime.strptime(t_due_date_base, '%Y-%m-%d').date()
            except ValueError:
                logger.warning(f"Erro ao parsear due_date_base '{t_due_date_base}' para template {t_id}. Pulando geração para este template.")
                continue

            # Se o mês/ano solicitado for anterior ao mês/ano de início do template, NÃO GERE
            if current_month_date < template_start_date_dt.replace(day=1):
                logger.debug(f"Mês/ano solicitado ({month}/{year}) é anterior ao início do template '{t_name}' ({template_start_date_dt.month}/{template_start_date_dt.year}). Pulando.")
                continue

            # Calcula a data de vencimento para a instância deste mês/ano
            base_day = template_start_date_dt.day
            # Garante que o dia não excede o último dia do mês
            day_for_this_month = min(base_day, calendar.monthrange(year, month)[1])
            instance_due_date_dt = datetime.date(year, month, day_for_this_month)
            instance_due_date_str = instance_due_date_dt.strftime('%Y-%m-%d')
            logger.debug(f"Data da instância calculada para {month}/{year}: {instance_due_date_str}.")

            # NOVO: Verifica se esta instância deve ser ignorada para este mês
            if _is_monthly_instance_ignored(user_id, t_id, month, year):
                logger.debug(f"Instância para template '{t_name}' ({t_id}) em {month}/{year} está marcada como IGNORADA. Pulando criação.")
                continue

            # Verifica se a instância já existe para este mês/ano
            cursor.execute(
                """
                SELECT id FROM monthly_account_instances
                WHERE user_id = ? AND template_id = ? AND month = ? AND year = ?
                """,
                (user_id, t_id, month, year)
            )
            existing_instance = cursor.fetchone()

            if not existing_instance:
                logger.debug(f"Instância para template '{t_name}' ({t_id}) em {month}/{year} NÃO EXISTE. Tentando criar.")
                # Lógica para fixed_parcel: só gera se a parcela atual estiver dentro do range
                if t_recurrence == 'fixed_parcel':
                    delta_months = (year - template_start_date_dt.year) * 12 + (month - template_start_date_dt.month) + 1 # +1 para ser 1-indexed

                    if delta_months <= t_parcel_count:
                        logger.debug(f"Gerando parcela {delta_months}/{t_parcel_count} para '{t_name}'.")
                        _add_monthly_account_instance(user_id, t_name, t_amount, instance_due_date_str, month, year,
                                                    is_paid=0, recurrence_type=t_recurrence, template_id=t_id,
                                                    current_parcel=delta_months, total_parcels=t_parcel_count)
                    else:
                        logger.debug(f"Não gerando instância para '{t_name}': parcela {delta_months} excede total de {t_parcel_count}.")
                else: # indefinite
                    logger.debug(f"Gerando instância indefinida para '{t_name}'.")
                    _add_monthly_account_instance(user_id, t_name, t_amount, instance_due_date_str, month, year,
                                                is_paid=0, recurrence_type=t_recurrence, template_id=t_id)
            else:
                logger.debug(f"Instância para template '{t_name}' ({t_id}) em {month}/{year} JÁ EXISTE. Pulando.")

        conn.commit()
        logger.info(f"Instâncias de contas mensais para user {user_id}, mês {month}/{year} geradas/verificadas com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao gerar instâncias de contas mensais para {month}/{year} (user {user_id}): {e}")
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após _generate_monthly_account_instances.")


def get_monthly_accounts(user_id, month=None, year=None):
    """
    Retorna as contas mensais de um usuário, opcionalmente filtradas por mês e ano.
    Esta função AGORA consulta `monthly_account_instances` após garantir que as instâncias
    recorrentes para o mês/ano foram geradas.
    """
    logger.debug(f"Buscando contas mensais para user {user_id}, mês {month}/{year}.")
    if month and year:
        _generate_monthly_account_instances(user_id, month, year)

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        query = """
            SELECT id, name, amount, due_date, is_paid, recurrence_type, current_parcel, total_parcels, template_id
            FROM monthly_account_instances
            WHERE user_id = ?
        """
        params = [user_id]
        
        if month and year:
            query += " AND month = ? AND year = ?"
            params.extend([month, year])

        query += " ORDER BY due_date, name"
        
        logger.debug(f"Executando query para get_monthly_accounts: '{query}' com params: {params}")
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        logger.info(f"Encontradas {len(results)} contas mensais para user {user_id}, mês {month}/{year}.")
        return results
    except Exception as e:
        logger.error(f"Erro ao buscar contas mensais para user {user_id}: {e}")
        return []
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após get_monthly_accounts.")

def get_account_by_id(account_id, user_id):
    """Retorna uma conta específica pelo ID e user_id da tabela de INSTÂNCIAS."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Buscando conta por ID: {account_id} para user {user_id}.")
        cursor.execute(
            """
            SELECT id, name, amount, due_date, is_paid, recurrence_type, current_parcel, total_parcels, template_id
            FROM monthly_account_instances WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id)
        )
        result = cursor.fetchone()
        if result:
            logger.info(f"Conta ID {account_id} encontrada para user {user_id}.")
        else:
            logger.warning(f"Conta ID {account_id} NÃO encontrada para user {user_id}.")
        return result
    except Exception as e:
        logger.error(f"Erro ao buscar instância de conta ID {account_id} para user {user_id}: {e}")
        return None
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após get_account_by_id.")

def mark_account_paid(account_id, user_id):
    """Marca uma INSTÂNCIA de conta como paga."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Tentando marcar conta ID {account_id} como paga para user {user_id}.")
        cursor.execute(
            "UPDATE monthly_account_instances SET is_paid = 1 WHERE id = ? AND user_id = ?",
            (account_id, user_id)
        )
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Conta ID {account_id} marcada como paga com sucesso para user {user_id}.")
            return True
        else:
            logger.warning(f"Falha ao marcar conta ID {account_id} como paga para user {user_id}. Nenhuma linha afetada.")
            return False
    except Exception as e:
        logger.error(f"Erro ao marcar instância de conta ID {account_id} como paga para user {user_id}: {e}")
        return False
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após mark_account_paid.")

def delete_monthly_account(account_id, user_id):
    """
    Deleta uma ÚNICA INSTÂNCIA de conta mensal.
    Se a instância deletada for de um template recorrente, ela também é marcada como ignorada para aquele mês.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Tentando deletar instância de conta ID {account_id} para user {user_id}.")
        
        # Passo 1: Obter detalhes da instância antes de deletar
        cursor.execute(
            "SELECT template_id, month, year FROM monthly_account_instances WHERE id = ? AND user_id = ?",
            (account_id, user_id)
        )
        instance_details = cursor.fetchone()
        
        # Passo 2: Deletar a instância
        cursor.execute(
            "DELETE FROM monthly_account_instances WHERE id = ? AND user_id = ?",
            (account_id, user_id)
        )
        conn.commit()

        if cursor.rowcount > 0:
            logger.info(f"Instância de conta ID {account_id} deletada com sucesso para user {user_id}.")
            
            # Passo 3: Se era de um template recorrente, adicionar à lista de ignorados
            if instance_details and instance_details[0] is not None: # instance_details[0] é o template_id
                template_id = instance_details[0]
                month = instance_details[1]
                year = instance_details[2]
                _add_ignored_monthly_instance(user_id, template_id, month, year) # Adiciona à tabela de ignorados
                logger.info(f"Instância de conta ID {account_id} (template {template_id}) para {month}/{year} marcada como ignorada.")
            
            return True
        else:
            logger.warning(f"Falha ao deletar instância de conta ID {account_id} para user {user_id}. Nenhuma linha afetada.")
            return False
    except Exception as e:
        logger.error(f"Erro ao deletar instância de conta ID {account_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após delete_monthly_account.")

def delete_account_template_and_future_instances(template_id, user_id):
    """
    Deleta o template de conta recorrente e TODAS as instâncias associadas
    (incluindo a instância do mês atual e futuras).
    Também limpa entradas correspondentes na tabela de ignorados.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Tentando deletar template ID {template_id} e suas instâncias futuras para user {user_id}.")
        
        # Deleta as instâncias associadas ao template
        cursor.execute(
            "DELETE FROM monthly_account_instances WHERE template_id = ? AND user_id = ?",
            (template_id, user_id)
        )
        rows_deleted_instances = cursor.rowcount
        logger.info(f"{rows_deleted_instances} instâncias deletadas para o template ID {template_id}.")

        # NOVO: Limpa as entradas correspondentes na tabela de instâncias ignoradas
        cursor.execute(
            "DELETE FROM ignored_monthly_instances WHERE template_id = ? AND user_id = ?",
            (template_id, user_id)
        )
        rows_deleted_ignored = cursor.rowcount
        logger.info(f"{rows_deleted_ignored} entradas de ignorados deletadas para o template ID {template_id}.")

        # Deleta o template em si
        cursor.execute(
            "DELETE FROM account_templates WHERE id = ? AND user_id = ?",
            (template_id, user_id)
        )
        rows_deleted_template = cursor.rowcount
        logger.info(f"{rows_deleted_template} template(s) deletado(s) para o template ID {template_id}.")

        conn.commit()
        return rows_deleted_template > 0 or rows_deleted_instances > 0
    except Exception as e:
        logger.error(f"Erro ao deletar template e instâncias futuras para template ID {template_id} (user {user_id}): {e}")
        return False
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após delete_account_template_and_future_instances.")

def add_financial_income(user_id, description, amount, income_date):
    """Adiciona um novo rendimento financeiro."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Adicionando entrada: user_id={user_id}, description='{description}', amount={amount}, income_date='{income_date}'")
        cursor.execute(
            "INSERT INTO financial_incomes (user_id, description, amount, income_date) VALUES (?, ?, ?, ?)",
            (user_id, description, amount, income_date)
        )
        conn.commit()
        logger.info(f"Entrada '{description}' adicionada com sucesso para user {user_id}.")
        return True
    except sqlite3.IntegrityError: # Tratamento específico para IntegrityError
        logger.warning(f"Entrada '{description}' para a data {income_date} já existe para user {user_id}. Não inserindo novamente.")
        return False
    except Exception as e:
        logger.error(f"Erro ao adicionar rendimento financeiro para '{description}' (user {user_id}): {e}")
        return False
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após add_financial_income.")

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
        logger.debug(f"Executando query para get_financial_incomes: '{query}' com params: {params}")
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        logger.info(f"Encontrados {len(results)} rendimentos para user {user_id}, mês {month}/{year}.")
        return results
    except Exception as e:
        logger.error(f"Erro ao buscar rendimentos para user {user_id}: {e}")
        return []
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após get_financial_incomes.")

def get_income_by_id(income_id, user_id):
    """Retorna uma entrada de renda específica pelo ID e user_id."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Buscando entrada por ID: {income_id} para user {user_id}.")
        cursor.execute(
            "SELECT id, description, amount, income_date FROM financial_incomes WHERE id = ? AND user_id = ?",
            (income_id, user_id)
        )
        result = cursor.fetchone()
        if result:
            logger.info(f"Entrada ID {income_id} encontrada para user {user_id}.")
        else:
            logger.warning(f"Entrada ID {income_id} NÃO encontrada para user {user_id}.")
        return result
    except Exception as e:
        logger.error(f"Erro ao buscar entrada ID {income_id} para user {user_id}: {e}")
        return None
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após get_income_by_id.")

def delete_financial_income(income_id, user_id):
    """Deleta um rendimento financeiro."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        logger.debug(f"Tentando deletar entrada ID {income_id} para user {user_id}.")
        cursor.execute(
            "DELETE FROM financial_incomes WHERE id = ? AND user_id = ?",
            (income_id, user_id)
        )
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Entrada ID {income_id} deletada com sucesso para user {user_id}.")
            return True
        else:
            logger.warning(f"Falha ao deletar entrada ID {income_id} para user {user_id}. Nenhuma linha afetada.")
            return False
    except Exception as e:
        logger.error(f"Erro ao deletar rendimento ID {income_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()
        logger.debug("Conexão com o banco de dados fechada após delete_financial_income.")

def get_accumulated_balance_up_to_date(user_id: int, target_date: datetime.date) -> float:
    """
    Calcula o saldo acumulado (entradas totais - saídas totais) até uma data específica.
    Considera todas as entradas até a data e todas as CONTAS INSTÂNCIAS (mesmo as não pagas)
    cuja data de vencimento é até a data.
    """
    conn = None
    balance = 0.0 # Inicializa balance antes do try
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        target_date_str = target_date.strftime('%Y-%m-%d')
        logger.debug(f"Calculando saldo acumulado para user {user_id} até {target_date_str}.")

        # Total de entradas até a data alvo
        cursor.execute(
            "SELECT SUM(amount) FROM financial_incomes WHERE user_id = ? AND income_date <= ?",
            (user_id, target_date_str)
        )
        total_incomes = cursor.fetchone()[0] or 0.0 # Atribuição
        logger.debug(f"Buscando total de entradas até {target_date_str}: {total_incomes}.") # LOG AGORA VEM DEPOIS DA ATRIBUIÇÃO

        # Total de contas (despesas) INSTÂNCIAS até a data alvo
        cursor.execute(
            """
            SELECT SUM(amount) FROM monthly_account_instances
            WHERE user_id = ? AND due_date <= ?
            """,
            (user_id, target_date_str)
        )
        total_expenses = cursor.fetchone()[0] or 0.0 # Atribuição
        logger.debug(f"Buscando total de contas (instâncias) até {target_date_str}: {total_expenses}.") # LOG AGORA VEM DEPOIS DA ATRIBUIÇÃO
        
        balance = total_incomes - total_expenses
        logger.info(f"Saldo acumulado para user {user_id} até {target_date_str}: {balance:.2f}.")
        return balance
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar saldo acumulado até {target_date}: {e}")
        return 0.0
    finally:
        if conn:
            conn.close()
            logger.debug("Conexão com o banco de dados fechada após get_accumulated_balance_up_to_date.")

def get_financial_summary(user_id: int, month: int, year: int) -> dict:
    """
    Retorna um dicionário com o resumo financeiro para o mês e ano especificados,
    considerando o saldo acumulado do mês anterior.
    AGORA OPERA APENAS NAS INSTÂNCIAS GENERADAS.
    """
    logger.debug(f"Gerando resumo financeiro para user {user_id}, mês {month}/{year}.")
    # Garante que as instâncias para o mês solicitado foram geradas
    _generate_monthly_account_instances(user_id, month, year)

    first_day_current_month = datetime.date(year, month, 1)
    last_day_previous_month = first_day_current_month - datetime.timedelta(days=1)
    
    previous_month_balance = get_accumulated_balance_up_to_date(user_id, last_day_previous_month)
    logger.debug(f"Saldo do mês anterior ({last_day_previous_month.strftime('%Y-%m-%d')}) para user {user_id}: {previous_month_balance:.2f}.")

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Total de rendimentos no mês ATUAL
    logger.debug(f"Buscando total de entradas no mês atual ({month}/{year}) para user {user_id}.")
    cursor.execute(
        '''
        SELECT SUM(amount) FROM financial_incomes
        WHERE user_id = ? AND STRFTIME('%Y', income_date) = ? AND STRFTIME('%m', income_date) = ?
        ''',
        (user_id, str(year), f'{month:02d}')
    )
    total_incomes_this_month = cursor.fetchone()[0] or 0.0
    logger.debug(f"Total de entradas neste mês: {total_incomes_this_month:.2f}.")

    # Total de contas (despesas) ATIVAS para o mês atual (instâncias do mês)
    logger.debug(f"Buscando total de contas ativas no mês atual ({month}/{year}) para user {user_id}.")
    cursor.execute(
        '''
        SELECT SUM(amount) FROM monthly_account_instances
        WHERE user_id = ? AND month = ? AND year = ?
        ''',
        (user_id, month, year)
    )
    total_accounts_due_this_month = cursor.fetchone()[0] or 0.0
    logger.debug(f"Total de contas a pagar neste mês: {total_accounts_due_this_month:.2f}.")

    # Total de contas PAGAS no mês ATUAL (instâncias pagas do mês)
    logger.debug(f"Buscando total de contas pagas no mês atual ({month}/{year}) para user {user_id}.")
    cursor.execute(
        '''
        SELECT SUM(amount) FROM monthly_account_instances
        WHERE user_id = ? AND is_paid = 1 AND month = ? AND year = ?
        ''',
        (user_id, month, year)
    )
    paid_accounts_this_month = cursor.fetchone()[0] or 0.0
    logger.debug(f"Total de contas pagas neste mês: {paid_accounts_this_month:.2f}.")

    # Total de contas PENDENTES no mês ATUAL (instâncias pendentes do mês)
    logger.debug(f"Buscando total de contas pendentes no mês atual ({month}/{year}) para user {user_id}.")
    cursor.execute(
        '''
        SELECT SUM(amount) FROM monthly_account_instances
        WHERE user_id = ? AND is_paid = 0 AND month = ? AND year = ?
        ''',
        (user_id, month, year)
    )
    unpaid_accounts_this_month = cursor.fetchone()[0] or 0.0
    logger.debug(f"Total de contas pendentes neste mês: {unpaid_accounts_this_month:.2f}.")

    conn.close()
    logger.debug("Conexão com o banco de dados fechada após get_financial_summary.")

    current_month_net_change = total_incomes_this_month - total_accounts_due_this_month
    final_balance_this_month = previous_month_balance + current_month_net_change

    logger.info(f"Resumo financeiro final para user {user_id}, mês {month}/{year}: Saldo Final Acumulado = {final_balance_this_month:.2f}.")
    return {
        'total_incomes_this_month': total_incomes_this_month,
        'total_accounts_due_this_month': total_accounts_due_this_month,
        'paid_accounts_this_month': paid_accounts_this_month,
        'unpaid_accounts_this_month': unpaid_accounts_this_month,
        'previous_month_balance': previous_month_balance,
        'current_month_net_change': current_month_net_change,
        'final_balance_this_month': final_balance_this_month
    }

def get_detailed_monthly_accounts(user_id: int, month: int, year: int) -> list:
    """Retorna contas detalhadas do mês e ano especificados, garantindo a geração."""
    logger.debug(f"Chamando get_monthly_accounts para detalhes de contas para user {user_id}, mês {month}/{year}.")
    return get_monthly_accounts(user_id, month, year)

def get_detailed_financial_incomes(user_id: int, month: int, year: int) -> list:
    """Retorna entradas detalhadas do mês e ano especificados."""
    logger.debug(f"Chamando get_financial_incomes para detalhes de entradas para user {user_id}, mês {month}/{year}.")
    return get_financial_incomes(user_id, month, year)