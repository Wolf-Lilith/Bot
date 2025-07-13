# main.py

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import Update
import handlers
import list_handlers
import reminders_handlers
import account_handlers # Importando o módulo de handlers de contas
from secrets import TELEGRAM_BOT_TOKEN
import db
import accounts_db # Importa o módulo de banco de dados para contas
import logging

# Configuração de logging: CENTRALIZADA AQUI para todo o bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Iniciando Lilith Bot...")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    db.create_tables()
    accounts_db.init_accounts_db()

    # Inserir comandos no DB (se não existirem)
    db.insert_command("start", "handlers.start_command", "Inicia o bot e te cumprimenta.")
    db.insert_command("ajuda", "handlers.help_command", "Mostra o menu de ajuda interativo.")
    db.insert_command("addfrase", "handlers.new_phrase_start", "Adiciona uma frase personalizada para eu responder.")
    db.insert_command("minhasfrases", "handlers.view_my_phrases", "Vê suas frases personalizadas.")
    db.insert_command("apagarfrase", "handlers.delete_phrase_start", "Apaga uma frase personalizada existente.")
    db.insert_command("novalista", "list_handlers.new_list_start", "Cria uma nova lista (ex: de compras, tarefas).")
    db.insert_command("listas", "list_handlers.list_my_lists", "Vê todas as suas listas existentes.")
    db.insert_command("verlista", "list_handlers.view_list_start", "Vê os itens de uma lista específica.")
    db.insert_command("additem", "list_handlers.add_item_start", "Adiciona um item a uma lista existente.")
    db.insert_command("marcaritem", "list_handlers.toggle_item_start", "Marca/desmarca um item de uma lista como completo.")
    db.insert_command("removeritem", "list_handlers.remove_item_start", "Remove um item específico de uma lista.")
    db.insert_command("apagarlista", "list_handlers.delete_list_start", "Apaga uma lista e todos os seus itens.")
    db.insert_command("add_lembrete", "reminders_handlers.add_reminder_start", "Adiciona um novo lembrete com data e hora.")
    db.insert_command("ver_lembretes", "reminders_handlers.view_reminders", "Vê todos os seus lembretes programados.")
    db.insert_command("apagar_lembrete", "reminders_handlers.delete_reminder_start", "Apaga um lembrete existente.")
    db.insert_command("contas", "account_handlers.accounts_menu", "Gerencia suas contas financeiras.")
    db.insert_command("cancelar", "handlers.cancel_dialog", "Cancela qualquer operação ou diálogo em andamento.")

    # --- Registra os CommandHandlers ---
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("ajuda", handlers.help_command))

    application.add_handler(CallbackQueryHandler(handlers.send_help_category_menu, pattern=r"^help_category:(phrases|lists|reminders|general|accounts)$"))
    application.add_handler(CallbackQueryHandler(handlers.send_main_help_menu, pattern=r"^help_category:main_menu$"))

    # Handlers de visualização simples que não iniciam conversas
    application.add_handler(CommandHandler("minhasfrases", handlers.view_my_phrases))
    application.add_handler(CommandHandler("listas", list_handlers.list_my_lists))
    application.add_handler(CommandHandler("ver_lembretes", reminders_handlers.view_reminders))

    # --- Registra os ConversationHandlers ---

    # Frases Personalizadas
    add_phrase_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addfrase", handlers.new_phrase_start)],
        states={
            handlers.GETTING_TRIGGER_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_trigger_phrase)],
            handlers.GETTING_RESPONSE_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_response_phrase)],
        },
        fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)],
        allow_reentry=True
    )
    delete_phrase_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("apagarfrase", handlers.delete_phrase_start)],
        states={
            handlers.GETTING_PHRASE_ID_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.delete_phrase_confirm)],
        },
        fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)],
        allow_reentry=True
    )

    # Listas
    new_list_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("novalista", list_handlers.new_list_start)],
        states={
            list_handlers.SELECTING_LIST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_list_name)],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    view_list_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("verlista", list_handlers.view_list_start)],
        states={
            list_handlers.VIEWING_LIST_COMMAND_START: [
                # Este CallbackQueryHandler é para a seleção da lista para visualização
                CallbackQueryHandler(list_handlers.get_list_to_view, pattern=r'^select_list_id:\d+$'),
                # Este CallbackQueryHandler é para o botão "Voltar às Listas" dentro da visualização
                CallbackQueryHandler(list_handlers.get_list_to_view, pattern=r'^view_lists_back$'),
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$')
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    add_item_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("additem", list_handlers.add_item_start)],
        states={
            list_handlers.SELECTING_LIST_TO_ADD_ITEM: [
                CallbackQueryHandler(list_handlers.handle_list_item_action_callbacks, pattern=r'^select_list_id:\d+$'),
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$')
            ],
            list_handlers.GETTING_ITEM_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_text),
                CommandHandler("cancelar", list_handlers.cancel_list_dialog)
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    toggle_item_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("marcaritem", list_handlers.toggle_item_start)],
        states={
            list_handlers.SELECTING_LIST_TO_TOGGLE: [
                CallbackQueryHandler(list_handlers.handle_list_item_action_callbacks, pattern=r'^select_list_id:\d+$'),
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$')
            ],
            list_handlers.GETTING_ITEM_ID_TO_TOGGLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_id_to_toggle),
                CommandHandler("cancelar", list_handlers.cancel_list_dialog)
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    remove_item_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("removeritem", list_handlers.remove_item_start)],
        states={
            list_handlers.SELECTING_LIST_TO_REMOVE: [
                CallbackQueryHandler(list_handlers.handle_list_item_action_callbacks, pattern=r'^select_list_id:\d+$'),
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$')
            ],
            list_handlers.GETTING_ITEM_ID_TO_REMOVE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_id_to_remove),
                CommandHandler("cancelar", list_handlers.cancel_list_dialog)
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    delete_list_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("apagarlista", list_handlers.delete_list_start)],
        states={
            list_handlers.CONFIRM_DELETE_LIST: [
                CallbackQueryHandler(list_handlers.handle_list_item_action_callbacks, pattern=r'^select_list_id:\d+$'), # Para selecionar a lista
                CallbackQueryHandler(list_handlers.handle_list_item_action_callbacks, pattern=r'^confirm_delete_list_action:\d+$'), # Para confirmar
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$') # Para cancelar
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)], # <--- CORREÇÃO APLICADA AQUI!
        allow_reentry=True
    )

    # Lembretes
    add_reminder_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add_lembrete", reminders_handlers.add_reminder_start)],
        states={
            reminders_handlers.GETTING_REMINDER_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_desc)],
            reminders_handlers.GETTING_REMINDER_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_datetime)],
            reminders_handlers.GETTING_REMINDER_RECURRENCE: [
                CallbackQueryHandler(reminders_handlers.get_reminder_recurrence, pattern="^(daily|weekly|monthly|yearly|none)$"),
                CallbackQueryHandler(reminders_handlers.cancel_dialog, pattern="^cancel_reminder_add$")
            ],
        },
        fallbacks=[CommandHandler("cancelar", reminders_handlers.cancel_dialog)],
        allow_reentry=True
    )
    delete_reminder_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("apagar_lembrete", reminders_handlers.delete_reminder_start)],
        states={
            reminders_handlers.GETTING_REMINDER_ID_FOR_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.delete_reminder_confirm)],
        },
        fallbacks=[CommandHandler("cancelar", reminders_handlers.cancel_dialog)],
        allow_reentry=True
    )

    # --- Contas Financeiras: UNIFICADO EM UM ÚNICO ConversationHandler ---
    accounts_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("contas", account_handlers.accounts_menu), # Comando para entrar no menu de contas
        ],
        states={
            account_handlers.VIEW_ACCOUNTS_MENU: [
                CallbackQueryHandler(account_handlers.handle_accounts_menu_selection, pattern=r"^accounts_action:"), # Padrão para os botões do menu principal de contas
                CallbackQueryHandler(account_handlers.handle_accounts_menu_selection, pattern=r"^accounts_nav:"), # Padrão para os botões de navegação de mês no menu de resumo
                # **LINHA ATUALIZADA PARA INCLUIR A NAVEGAÇÃO DE DELEÇÃO E VISUALIZAÇÃO**
                CallbackQueryHandler(account_handlers.handle_view_navigation, pattern=r"^(view_accounts_nav|view_incomes_nav|delete_accounts_nav|delete_incomes_nav):"), 
            ],
            
            # --- Fluxo de Adicionar Conta ---
            account_handlers.ADD_ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_name)],
            account_handlers.ADD_ACCOUNT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_amount)],
            account_handlers.GETTING_ACCOUNT_DATE_FROM_CALENDAR: [
                CallbackQueryHandler(account_handlers.handle_calendar_callback, pattern=r"^cal:"), # Qualquer clique no calendário
            ],
            account_handlers.ADD_ACCOUNT_RECURRENCE: [
                CallbackQueryHandler(account_handlers.get_account_recurrence, pattern="^(none|indefinite|fixed_parcel|cal:cancel)$") # Inclui o cancelar do calendário
            ],
            account_handlers.ADD_ACCOUNT_PARCEL_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_parcel_count)],

            # --- Fluxo de Marcar Conta como Paga ---
            account_handlers.GET_ACCOUNT_ID_TO_MARK: [
                CallbackQueryHandler(account_handlers.mark_account_paid_confirm, pattern=r"^mark_account:\d+$"),
                CallbackQueryHandler(account_handlers.mark_account_paid_confirm, pattern=r"^accounts_action:back_to_accounts_menu$"),
            ],

            # --- Fluxo de Deletar Conta (com navegação de mês) ---
            account_handlers.GET_ACCOUNT_ID_TO_DELETE: [
                CallbackQueryHandler(account_handlers.delete_account_confirm, pattern=r"^delete_account:\d+$"),
                CallbackQueryHandler(account_handlers.delete_account_confirm, pattern=r"^accounts_action:back_to_accounts_menu$"),
                # Adicionado para capturar a navegação de mês no fluxo de deleção de contas
                CallbackQueryHandler(account_handlers.handle_view_navigation, pattern=r"^delete_accounts_nav:"),
            ],

            # --- Fluxo de Adicionar Entrada ---
            account_handlers.ADD_INCOME_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_description)],
            account_handlers.ADD_INCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_amount)],
            account_handlers.GETTING_INCOME_DATE_FROM_CALENDAR: [
                CallbackQueryHandler(account_handlers.handle_calendar_callback, pattern=r"^cal:"), # Qualquer clique no calendário
            ],

            # --- Fluxo de Deletar Entrada (com navegação de mês) ---
            account_handlers.GET_INCOME_ID_TO_DELETE: [
                CallbackQueryHandler(account_handlers.delete_income_confirm, pattern=r"^delete_income:\d+$"),
                CallbackQueryHandler(account_handlers.delete_income_confirm, pattern=r"^accounts_action:back_to_accounts_menu$"),
                # Adicionado para capturar a navegação de mês no fluxo de deleção de entradas
                CallbackQueryHandler(account_handlers.handle_view_navigation, pattern=r"^delete_incomes_nav:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancelar", account_handlers.cancel_accounts_flow), # Cancelar em qualquer ponto da conversa de contas
            MessageHandler(filters.TEXT | filters.COMMAND, account_handlers.accounts_menu) # Volta para o menu de contas se receber texto/comando inesperado
        ],
        allow_reentry=True,
    )

    application.add_handler(add_phrase_conv_handler)
    application.add_handler(delete_phrase_conv_handler)
    application.add_handler(new_list_conv_handler)
    application.add_handler(view_list_conv_handler)
    application.add_handler(add_item_conv_handler)
    application.add_handler(toggle_item_conv_handler)
    application.add_handler(remove_item_conv_handler)
    application.add_handler(delete_list_conv_handler)
    application.add_handler(add_reminder_conv_handler)
    application.add_handler(delete_reminder_conv_handler)

    # REGISTRANDO O ÚNICO CONVERSATION HANDLER DE CONTAS
    application.add_handler(accounts_conv_handler)

    # Handler para frases personalizadas (deve ser o último MessageHandler para não interceptar comandos)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_personal_phrase))

    # Handler de cancelamento global (para casos que não estejam em ConversationHandlers específicos)
    application.add_handler(CommandHandler("cancelar", handlers.cancel_dialog))

    logger.info("Bot configurado. Agendando lembretes existentes...")
    reminders_handlers.schedule_existing_reminders(application) 

    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Lilith Bot parado.")

if __name__ == "__main__":
    main()