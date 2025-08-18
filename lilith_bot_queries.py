import sqlite3
import datetime
import calendar
import matplotlib.pyplot as plt
import os
import matplotlib.gridspec as gridspec
import matplotlib.font_manager as fm

# --- Configurações da Tabela ---
TABLE_PROPS = {
    'cellLoc': 'center',
    'cellText': None,
    'colLabels': None,
    'bbox': [0, 0, 1, 1],
}
CELL_PROPS = {
    'alpha': 0.8,
    'edgecolor': 'black',
    'facecolor': 'lightgray'
}
HEADER_PROPS = {
    'alpha': 1.0,
    'edgecolor': 'black',
    'facecolor': 'steelblue'
}

DATABASE_NAME = 'lilith_bot.db'
# USER ID PADRÃO
DEFAULT_USER_ID = 6883614660


def _get_quinzena_dates(month, year, quinzena):
    """
    Determina as datas de início e fim para a quinzena especificada.
    """
    if quinzena == 1:
        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, 15)
    elif quinzena == 2:
        start_date = datetime.date(year, month, 16)
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime.date(year, month, last_day)
    else:
        raise ValueError("Quinzena inválida. Use 1 ou 2.")

    return start_date, end_date


def generate_monthly_report_image(user_id=DEFAULT_USER_ID, month=None, year=None):
    """
    Gera um relatório mensal completo em uma única imagem, com tabelas para as duas quinzenas,
    usando consultas SQL diretas.
    """
    if month is None:
        month = datetime.date.today().month
    if year is None:
        year = datetime.date.today().year

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        # Consulta SQL para obter todas as contas do mês atual
        accounts_query = """
            SELECT name, amount, due_date, is_paid, recurrence_type, current_parcel, total_parcels
            FROM monthly_account_instances
            WHERE user_id = ? AND month = ? AND year = ?
        """
        cursor.execute(accounts_query, (user_id, month, year))
        all_accounts = cursor.fetchall()

        # Consulta SQL para obter todas as contas de meses anteriores que estão em aberto
        overdue_query = """
            SELECT name, amount, due_date, is_paid, recurrence_type, current_parcel, total_parcels
            FROM monthly_account_instances
            WHERE user_id = ? AND is_paid = 0 AND STRFTIME('%Y-%m', due_date) < ?
            ORDER BY due_date ASC
        """
        current_month_str = f'{year:04d}-{month:02d}'
        cursor.execute(overdue_query, (user_id, current_month_str))
        overdue_accounts = cursor.fetchall()


        # CORREÇÃO: Busca de rendimentos por quinzena separadamente para maior precisão
        incomes_q1_query = """
            SELECT description, amount, income_date
            FROM financial_incomes
            WHERE user_id = ? AND STRFTIME('%Y-%m-%d', income_date) BETWEEN ? AND ?
        """
        quinzena1_start, quinzena1_end = _get_quinzena_dates(month, year, 1)
        cursor.execute(incomes_q1_query, (user_id, quinzena1_start.strftime('%Y-%m-%d'), quinzena1_end.strftime('%Y-%m-%d')))
        quinzena1_incomes_raw = cursor.fetchall()

        incomes_q2_query = """
            SELECT description, amount, income_date
            FROM financial_incomes
            WHERE user_id = ? AND STRFTIME('%Y-%m-%d', income_date) BETWEEN ? AND ?
        """
        quinzena2_start, quinzena2_end = _get_quinzena_dates(month, year, 2)
        cursor.execute(incomes_q2_query, (user_id, quinzena2_start.strftime('%Y-%m-%d'), quinzena2_end.strftime('%Y-%m-%d')))
        quinzena2_incomes_raw = cursor.fetchall()
        
        # Filtra os dados por quinzena
        quinzena1_accounts = [
            acc for acc in all_accounts
            if quinzena1_start <= datetime.datetime.strptime(acc[2], '%Y-%m-%d').date() <= quinzena1_end
        ]
        quinzena2_accounts = [
            acc for acc in all_accounts
            if quinzena2_start <= datetime.datetime.strptime(acc[2], '%Y-%m-%d').date() <= quinzena2_end
        ]

        # ORDENAÇÃO POR DATA
        quinzena1_accounts.sort(key=lambda x: datetime.datetime.strptime(x[2], '%Y-%m-%d').date())
        quinzena2_accounts.sort(key=lambda x: datetime.datetime.strptime(x[2], '%Y-%m-%d').date())
        
        # Adiciona as contas atrasadas na frente da lista da 1ª quinzena
        # A lista overdue_accounts já está ordenada por data na query SQL
        quinzena1_accounts = list(overdue_accounts) + quinzena1_accounts

        # Prepara os dados da tabela, com mensagens para listas vazias
        headers = ["Nome", "Valor", "Vencimento", "Pago", "Parcela"]
        
        table1_data = []
        if not quinzena1_accounts:
            table1_data = [["Nenhuma conta encontrada", "", "", "", ""]]
        else:
            for row in quinzena1_accounts:
                try:
                    name = row[0]
                    amount = row[1] if row[1] is not None else 0.0
                    due_date = row[2]
                    is_paid = row[3]
                    recurrence_type = row[4]
                    current_parcel = row[5]
                    total_parcels = row[6]
                    
                    due_date_obj = datetime.datetime.strptime(due_date, '%Y-%m-%d').date()
                    due_date_formatted = due_date_obj.strftime('%d/%m/%Y')
                    
                    # Lógica para o novo status "Atrasado"
                    if is_paid == 1:
                        paid_status = "Pago"
                    elif due_date_obj < quinzena1_start:
                        paid_status = "Atrasado"
                    else:
                        paid_status = "Aberto"

                    parcel_info = f"{current_parcel}/{total_parcels}" if current_parcel and total_parcels else ""
                    if recurrence_type == 'indefinite': parcel_info = "Recorrente"
                        
                    table1_data.append([name, f"R$ {amount:.2f}", due_date_formatted, paid_status, parcel_info])
                except (ValueError, IndexError):
                    continue

        table2_data = []
        if not quinzena2_accounts:
            table2_data = [["Nenhuma conta encontrada", "", "", "", ""]]
        else:
            for row in quinzena2_accounts:
                try:
                    name = row[0]
                    amount = row[1] if row[1] is not None else 0.0
                    due_date = row[2]
                    is_paid = row[3]
                    recurrence_type = row[4]
                    current_parcel = row[5]
                    total_parcels = row[6]

                    due_date_formatted = datetime.datetime.strptime(due_date, '%Y-%m-%d').strftime('%d/%m/%Y')
                    
                    # Lógica simplificada para a segunda quinzena (não tem atraso)
                    paid_status = "Pago" if is_paid == 1 else "Aberto"

                    parcel_info = f"{current_parcel}/{total_parcels}" if current_parcel and total_parcels else ""
                    if recurrence_type == 'indefinite': parcel_info = "Recorrente"
                    table2_data.append([name, f"R$ {amount:.2f}", due_date_formatted, paid_status, parcel_info])
                except (ValueError, IndexError):
                    continue
        
        # 3. Gera a imagem com as duas tabelas
        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(12, 16))
        
        gs = gridspec.GridSpec(7, 1, height_ratios=[0.1, 1, 0.1, 1, 0.1, 0.5, 0.5])
        
        # TÍTULO 1
        ax1_title = fig.add_subplot(gs[0, 0])
        ax1_title.axis('off')
        ax1_title.text(0.5, 0.5, "1ª Quinzena", ha='center', va='center', fontsize=16, fontweight='bold', color='darkblue')

        # TABELA 1
        ax1_table = fig.add_subplot(gs[1, 0])
        ax1_table.axis('tight')
        ax1_table.axis('off')
        
        table1 = ax1_table.table(
            cellText=table1_data, 
            colLabels=headers, 
            loc='center', 
            cellLoc='center'
        )
        table1.auto_set_font_size(False)
        table1.set_fontsize(12)
        table1.scale(0.9, 1.2)
        
        # NOVO: Formata o fundo da célula e o texto para garantir as cores
        for i in range(len(table1_data)):
            status = table1_data[i][3]
            cell = table1.get_celld()[(i + 1, 3)] # A linha 0 é o cabeçalho
            cell._text.set_fontweight('bold')
            if status == "Pago":
                cell.set_facecolor('lightskyblue')
                cell._text.set_color('black')
            else: # Aberto ou Atrasado
                cell.set_facecolor('lightcoral')
                cell._text.set_color('black')

        # TÍTULO 2
        ax2_title = fig.add_subplot(gs[2, 0])
        ax2_title.axis('off')
        ax2_title.text(0.5, 0.5, "2ª Quinzena", ha='center', va='center', fontsize=16, fontweight='bold', color='darkblue')

        # TABELA 2
        ax2_table = fig.add_subplot(gs[3, 0])
        ax2_table.axis('tight')
        ax2_table.axis('off')
        
        table2 = ax2_table.table(
            cellText=table2_data, 
            colLabels=headers, 
            loc='center', 
            cellLoc='center'
        )
        table2.auto_set_font_size(False)
        table2.set_fontsize(12)
        table2.scale(0.9, 1.2)

        # NOVO: Formata o fundo da célula e o texto para garantir as cores
        for i in range(len(table2_data)):
            status = table2_data[i][3]
            cell = table2.get_celld()[(i + 1, 3)]
            cell._text.set_fontweight('bold')
            if status == "Pago":
                cell.set_facecolor('lightskyblue')
                cell._text.set_color('black')
            else: # Aberto
                cell.set_facecolor('lightcoral')
                cell._text.set_color('black')

        # TÍTULO 3 (Resumo)
        ax3_title = fig.add_subplot(gs[4, 0])
        ax3_title.axis('off')
        ax3_title.text(0.5, 0.5, "Resumo Financeiro", ha='center', va='center', fontsize=16, fontweight='bold', color='darkblue')


        # Resumo financeiro mensal e quinzenal
        # Cálculos de despesas
        total_paid_q1 = sum(acc[1] for acc in quinzena1_accounts if acc[3] == 1)
        total_due_q1 = sum(acc[1] for acc in quinzena1_accounts if acc[3] == 0)
        total_despesas_q1 = total_paid_q1 + total_due_q1

        total_paid_q2 = sum(acc[1] for acc in quinzena2_accounts if acc[3] == 1)
        total_due_q2 = sum(acc[1] for acc in quinzena2_accounts if acc[3] == 0)
        total_despesas_q2 = total_paid_q2 + total_due_q2

        total_despesas_mes = total_despesas_q1 + total_despesas_q2

        # Cálculos de renda
        total_income_q1 = sum(inc[1] for inc in quinzena1_incomes_raw)
        total_income_q2 = sum(inc[1] for inc in quinzena2_incomes_raw)
        total_income_mes = total_income_q1 + total_income_q2
        
        # Cálculos de saldo
        saldo_q1 = total_income_q1 - total_despesas_q1
        saldo_q2 = total_income_q2 - total_despesas_q2
        saldo_mes = total_income_mes - total_despesas_mes
        

        summary_data = [
            ["Renda Total", f"R$ {total_income_q1:.2f}", f"R$ {total_income_q2:.2f}", f"R$ {total_income_mes:.2f}"],
            ["Despesas Totais", f"R$ {total_despesas_q1:.2f}", f"R$ {total_despesas_q2:.2f}", f"R$ {total_despesas_mes:.2f}"],
            ["Saldo", f"R$ {saldo_q1:.2f}", f"R$ {saldo_q2:.2f}", f"R$ {saldo_mes:.2f}"],
            ["Total Pago", f"R$ {total_paid_q1:.2f}", f"R$ {total_paid_q2:.2f}", f"R$ {total_paid_q1 + total_paid_q2:.2f}"],
            ["Total a Pagar", f"R$ {total_due_q1:.2f}", f"R$ {total_due_q2:.2f}", f"R$ {total_due_q1 + total_due_q2:.2f}"]
        ]
        summary_headers = ["Categoria", "1ª Quinzena", "2ª Quinzena", "Total Mensal"]

        ax4 = fig.add_subplot(gs[5, 0])
        ax4.axis('tight')
        ax4.axis('off')
        
        table3 = ax4.table(
            cellText=summary_data, 
            colLabels=summary_headers, 
            loc='center', 
            cellLoc='center',
            cellColours=[['white'] * len(summary_headers) for _ in summary_data],
            colColours=['lightgray'] * len(summary_headers)
        )
        table3.auto_set_font_size(False)
        table3.set_fontsize(12)
        table3.scale(1, 1.5)

        # Final adjustments
        fig.tight_layout()
        image_file_name = f'relatorio_mensal.png'
        fig.savefig(image_file_name, bbox_inches='tight', dpi=150)
        plt.close(fig)

        return image_file_name, None
    except Exception as e:
        return None, f"Erro ao gerar relatório: {e}"
    finally:
        if conn:
            conn.close()


def generate_trimestral_report_image(user_id=DEFAULT_USER_ID, quarter=None, year=None):
    """
    Gera um relatório trimestral em uma única imagem usando apenas matplotlib.
    """
    if quarter is None:
        quarter = (datetime.date.today().month - 1) // 3 + 1
    if year is None:
        year = datetime.date.today().year

    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        monthly_data = []
        total_income_trimestre = 0
        total_expense_trimestre = 0

        for month in range(start_month, end_month + 1):
            month_name = datetime.date(year, month, 1).strftime('%B').capitalize()
            
            # Subquery para somar as despesas do mês
            expenses_query = """
                SELECT IFNULL(SUM(amount), 0)
                FROM monthly_account_instances
                WHERE user_id = ? AND year = ? AND month = ?
            """
            cursor.execute(expenses_query, (user_id, year, month))
            total_expense = cursor.fetchone()[0]

            # Subquery para somar as rendas do mês
            incomes_query = """
                SELECT IFNULL(SUM(amount), 0)
                FROM financial_incomes
                WHERE user_id = ? AND STRFTIME('%Y', income_date) = ? AND STRFTIME('%m', income_date) = ?
            """
            cursor.execute(incomes_query, (user_id, str(year), f'{month:02d}'))
            total_income = cursor.fetchone()[0]

            saldo = total_income - total_expense
            
            monthly_data.append([month_name, f"R$ {total_income:.2f}", f"R$ {total_expense:.2f}", f"R$ {saldo:.2f}"])

            total_income_trimestre += total_income
            total_expense_trimestre += total_expense
        
        final_saldo_trimestre = total_income_trimestre - total_expense_trimestre

        monthly_headers = ["Mês", "Renda", "Despesa", "Saldo"]
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(10, 8))
        gs = gridspec.GridSpec(3, 1, height_ratios=[0.1, 1, 0.5])
        
        # TÍTULO PRINCIPAL
        ax1_title = fig.add_subplot(gs[0, 0])
        ax1_title.axis('off')
        ax1_title.text(0.5, 0.5, f"Relatório Trimestral: Trimestre {quarter} de {year}", 
                       ha='center', va='center', fontsize=18, fontweight='bold', color='darkblue')

        # TABELA DE RESUMO MENSAL
        ax2_table = fig.add_subplot(gs[1, 0])
        ax2_table.axis('tight')
        ax2_table.axis('off')
        table_summary = ax2_table.table(
            cellText=monthly_data,
            colLabels=monthly_headers,
            loc='center',
            cellLoc='center'
        )
        table_summary.auto_set_font_size(False)
        table_summary.set_fontsize(12)
        table_summary.scale(1.2, 1.5)

        # TABELA FINAL DO TRIMESTRE
        summary_data = [
            ["Renda Total do Trimestre", f"R$ {total_income_trimestre:.2f}"],
            ["Despesa Total do Trimestre", f"R$ {total_expense_trimestre:.2f}"],
            ["Saldo Final do Trimestre", f"R$ {final_saldo_trimestre:.2f}"]
        ]
        
        ax3_table = fig.add_subplot(gs[2, 0])
        ax3_table.axis('tight')
        ax3_table.axis('off')
        final_summary_table = ax3_table.table(
            cellText=summary_data,
            loc='center',
            cellLoc='center'
        )
        final_summary_table.auto_set_font_size(False)
        final_summary_table.set_fontsize(12)
        final_summary_table.scale(1.2, 1.5)
        
        fig.tight_layout(pad=3.0)
        
        image_file_name = f'relatorio_trimestral.png'
        fig.savefig(image_file_name, bbox_inches='tight', dpi=150)
        plt.close(fig)

        return image_file_name, None

    except Exception as e:
        return None, f"Erro ao gerar relatório trimestral: {e}"
    finally:
        if conn:
            conn.close()


def generate_semestral_report_image(user_id=DEFAULT_USER_ID, semester=None, year=None):
    """
    Gera um relatório semestral em uma única imagem usando apenas matplotlib.
    """
    if semester is None:
        semester = 1 if datetime.date.today().month <= 6 else 2
    if year is None:
        year = datetime.date.today().year

    start_month = 1 if semester == 1 else 7
    end_month = 6 if semester == 1 else 12

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        monthly_data = []
        total_income_semestre = 0
        total_expense_semestre = 0
        
        for month in range(start_month, end_month + 1):
            month_name = datetime.date(year, month, 1).strftime('%B').capitalize()
            
            # Subquery para somar as despesas do mês
            expenses_query = """
                SELECT IFNULL(SUM(amount), 0)
                FROM monthly_account_instances
                WHERE user_id = ? AND year = ? AND month = ?
            """
            cursor.execute(expenses_query, (user_id, year, month))
            total_expense = cursor.fetchone()[0]

            # Subquery para somar as rendas do mês
            incomes_query = """
                SELECT IFNULL(SUM(amount), 0)
                FROM financial_incomes
                WHERE user_id = ? AND STRFTIME('%Y', income_date) = ? AND STRFTIME('%m', income_date) = ?
            """
            cursor.execute(incomes_query, (user_id, str(year), f'{month:02d}'))
            total_income = cursor.fetchone()[0]

            balance = total_income - total_expense
            
            monthly_data.append([month_name, f"R$ {total_income:.2f}", f"R$ {total_expense:.2f}", f"R$ {balance:.2f}"])

            total_income_semestre += total_income
            total_expense_semestre += total_expense
        
        final_saldo_semestre = total_income_semestre - total_expense_semestre
        
        monthly_headers = ["Mês", "Renda", "Despesa", "Saldo"]

        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(10, 10))
        gs = gridspec.GridSpec(3, 1, height_ratios=[0.1, 1, 0.5])

        # TÍTULO PRINCIPAL
        ax1_title = fig.add_subplot(gs[0, 0])
        ax1_title.axis('off')
        ax1_title.text(0.5, 0.5, f"Relatório Semestral: {semester}º Semestre de {year}", 
                       ha='center', va='center', fontsize=18, fontweight='bold', color='darkblue')

        # TABELA DE RESUMO MENSAL
        ax2_table = fig.add_subplot(gs[1, 0])
        ax2_table.axis('tight')
        ax2_table.axis('off')
        table_summary = ax2_table.table(
            cellText=monthly_data,
            colLabels=monthly_headers,
            loc='center',
            cellLoc='center'
        )
        table_summary.auto_set_font_size(False)
        table_summary.set_fontsize(12)
        table_summary.scale(1.2, 1.5)

        # TABELA FINAL DO SEMESTRE
        summary_data = [
            ["Renda Total do Semestre", f"R$ {total_income_semestre:.2f}"],
            ["Despesa Total do Semestre", f"R$ {total_expense_semestre:.2f}"],
            ["Saldo Final do Semestre", f"R$ {final_saldo_semestre:.2f}"]
        ]
        
        ax3_table = fig.add_subplot(gs[2, 0])
        ax3_table.axis('tight')
        ax3_table.axis('off')
        final_summary_table = ax3_table.table(
            cellText=summary_data,
            loc='center',
            cellLoc='center'
        )
        final_summary_table.auto_set_font_size(False)
        final_summary_table.set_fontsize(12)
        final_summary_table.scale(1.2, 1.5)
        
        fig.tight_layout(pad=3.0)
        
        image_file_name = f'relatorio_semestral.png'
        fig.savefig(image_file_name, bbox_inches='tight', dpi=150)
        plt.close(fig)

        return image_file_name, None

    except Exception as e:
        return None, f"Erro ao gerar relatório semestral: {e}"
    finally:
        if conn:
            conn.close()


def generate_anual_report_image(user_id=DEFAULT_USER_ID, year=None):
    """
    Gera um relatório anual em uma única imagem usando apenas matplotlib.
    """
    if year is None:
        year = datetime.date.today().year

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()

        monthly_data = []
        total_income_ano = 0
        total_expense_ano = 0
        
        for month in range(1, 13):
            month_name = datetime.date(year, month, 1).strftime('%B').capitalize()
            
            # Subquery para somar as despesas do mês
            expenses_query = """
                SELECT IFNULL(SUM(amount), 0)
                FROM monthly_account_instances
                WHERE user_id = ? AND year = ? AND month = ?
            """
            cursor.execute(expenses_query, (user_id, year, month))
            total_expense = cursor.fetchone()[0]

            # Subquery para somar as rendas do mês
            incomes_query = """
                SELECT IFNULL(SUM(amount), 0)
                FROM financial_incomes
                WHERE user_id = ? AND STRFTIME('%Y', income_date) = ? AND STRFTIME('%m', income_date) = ?
            """
            cursor.execute(incomes_query, (user_id, str(year), f'{month:02d}'))
            total_income = cursor.fetchone()[0]

            balance = total_income - total_expense
            
            monthly_data.append([month_name, f"R$ {total_income:.2f}", f"R$ {total_expense:.2f}", f"R$ {balance:.2f}"])

            total_income_ano += total_income
            total_expense_ano += total_expense
        
        final_saldo_ano = total_income_ano - total_expense_ano
        
        # Adiciona a linha de total
        monthly_data.append(["Total", f"R$ {total_income_ano:.2f}", f"R$ {total_expense_ano:.2f}", f"R$ {final_saldo_ano:.2f}"])
        
        monthly_headers = ["Mês", "Renda", "Despesa", "Saldo"]
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(12, 12))
        gs = gridspec.GridSpec(2, 1, height_ratios=[0.1, 1])

        # TÍTULO PRINCIPAL
        ax1_title = fig.add_subplot(gs[0, 0])
        ax1_title.axis('off')
        ax1_title.text(0.5, 0.5, f"Relatório Anual de {year}", 
                       ha='center', va='center', fontsize=18, fontweight='bold', color='darkblue')
        
        # TABELA
        ax2_table = fig.add_subplot(gs[1, 0])
        ax2_table.axis('tight')
        ax2_table.axis('off')
        
        table = ax2_table.table(
            cellText=monthly_data,
            colLabels=monthly_headers,
            loc='center',
            cellLoc='center',
            bbox=[0, 0, 1, 1],
        )

        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1.2, 1.2)
        
        # O código de formatação abaixo foi removido para evitar erros de compatibilidade.
        # for i in range(len(monthly_data) -1, len(monthly_data)):
        #     for j in range(len(monthly_headers)):
        #         cell = table.get_celld()[(i + 1, j)]
        #         cell.set_facecolor('lightgray')
        #         cell.set_edgecolor('black')
        #         cell.set_fontweight('bold')

        fig.tight_layout(pad=3.0)
        
        image_file_name = f'relatorio_anual.png'
        fig.savefig(image_file_name, bbox_inches='tight', dpi=150)
        plt.close(fig)

        return image_file_name, None

    except Exception as e:
        return None, f"Erro ao gerar relatório anual: {e}"
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    print("Gerando relatório mensal completo com user_id padrão...")
    current_month = datetime.date.today().month
    current_year = datetime.date.today().year
    
    # Chamando a função sem o user_id, ele usará o padrão
    image_file, error = generate_monthly_report_image(month=current_month, year=current_year)
    
    if error:
        print(f"Erro: {error}")
    else:
        print(f"Relatório mensal gerado e salvo em: {image_file}")
    
    print("\nGerando relatório trimestral...")
    quarter_to_test = (datetime.date.today().month - 1) // 3 + 1
    image_file_trimestral, error_trimestral = generate_trimestral_report_image(quarter=quarter_to_test, year=current_year)
    if error_trimestral:
        print(f"Erro: {error_trimestral}")
    else:
        print(f"Relatório trimestral gerado e salvo em: {image_file_trimestral}")

    print("\nGerando relatório semestral...")
    semester_to_test = 1 if datetime.date.today().month <= 6 else 2
    image_file_semestral, error_semestral = generate_semestral_report_image(semester=semester_to_test, year=current_year)
    if error_semestral:
        print(f"Erro: {error_semestral}")
    else:
        print(f"Relatório semestral gerado e salvo em: {image_file_semestral}")

    print("\nGerando relatório anual...")
    image_file_anual, error_anual = generate_anual_report_image(year=current_year)
    if error_anual:
        print(f"Erro: {error_anual}")
    else:
        print(f"Relatório anual gerado e salvo em: {image_file_anual}")