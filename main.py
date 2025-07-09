from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import Update
import handlers
import list_handlers
import reminders_handlers
import account_handlers # Importa o handler de contas
from secrets import TELEGRAM_BOT_TOKEN
import db
import accounts_db # Importa o módulo de banco de dados de contas
import logging

# Configuração de logging: Sugiro INFO para ver mais detalhes durante o desenvolvimento
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO # Alterado para INFO para ver mais logs durante o desenvolvimento
)

# Cria o bot
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Inicializa os bancos de dados
db.create_tables()
accounts_db.init_accounts_db() # Chamada para inicializar o DB de contas

# Inserir comandos no DB (se não existirem)
# Verificação dos nomes das funções nos módulos correspondentes:
# handlers.py
db.insert_command("start", "handlers.start_command", "Inicia o bot e te cumprimenta.")
db.insert_command("ajuda", "handlers.help_command", "Mostra o menu de ajuda interativo.")
db.insert_command("addfrase", "handlers.new_phrase_start", "Adiciona uma frase personalizada para eu responder.") # Verificado: new_phrase_start
db.insert_command("minhasfrases", "handlers.view_my_phrases", "Vê suas frases personalizadas.")
db.insert_command("apagarfrase", "handlers.delete_phrase_start", "Apaga uma frase personalizada existente.")

# list_handlers.py
db.insert_command("novalista", "list_handlers.new_list_start", "Cria uma nova lista (ex: de compras, tarefas).")
db.insert_command("listas", "list_handlers.list_my_lists", "Mostra todas as suas listas criadas.")
db.insert_command("verlista", "list_handlers.view_list_start", "Vê os itens de uma lista específica.")
db.insert_command("additem", "list_handlers.add_item_start", "Adiciona um item a uma lista existente.")
db.insert_command("marcaritem", "list_handlers.toggle_item_start", "Marca/desmarca um item como completo em uma lista.")
db.insert_command("removeritem", "list_handlers.remove_item_start", "Remove um item de uma lista.")
db.insert_command("apagarlista", "list_handlers.delete_list_start", "Apaga uma lista inteira e seus itens.")

# reminders_handlers.py
db.insert_command("addlembrete", "reminders_handlers.add_reminder_start", "Define um novo lembrete com descrição, data/hora e recorrência.")
db.insert_command("verlembretes", "reminders_handlers.view_reminders", "Vê todos os seus lembretes ativos.") # Verificado: view_reminders
db.insert_command("apagarlembrete", "reminders_handlers.delete_reminder_start", "Apaga um lembrete existente.")

# account_handlers.py
db.insert_command("contas", "account_handlers.accounts_menu", "Gerencia suas contas financeiras.")
db.insert_command("addconta", "account_handlers.add_account_start", "Adiciona uma nova conta a pagar.")
db.insert_command("addentrada", "account_handlers.add_income_start", "Adiciona um novo rendimento financeiro.")
db.insert_command("marcarpago", "account_handlers.mark_account_paid_start", "Marca uma conta como paga.")
db.insert_command("apagarconta", "account_handlers.delete_account_start", "Apaga uma conta registrada.")
db.insert_command("apagarentrada", "account_handlers.delete_income_start", "Apaga um rendimento financeiro.")


# Registra os CommandHandlers básicos
application.add_handler(CommandHandler("start", handlers.start_command))
application.add_handler(CommandHandler("ajuda", handlers.help_command)) # help_command chama o menu interativo

# --- ConversationHandlers ---
# handlers (frases personalizadas)
add_phrase_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("addfrase", handlers.new_phrase_start)], # Verificado: new_phrase_start
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
        handlers.GETTING_PHRASE_ID_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.confirm_delete_phrase)]
    },
    fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)],
    allow_reentry=True
)

# list_handlers (listas)
new_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("novalista", list_handlers.new_list_start)],
    states={
        # CORRIGIDO AQUI: A função correta é create_new_list_name, conforme o erro e o arquivo list_handlers.py
        list_handlers.SELECTING_LIST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.create_new_list_name)]
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    allow_reentry=True
)

view_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("verlista", list_handlers.view_list_start)],
    states={
        list_handlers.VIEWING_LIST_COMMAND_START: [CallbackQueryHandler(list_handlers.handle_view_list_selection, pattern=r"^view_list:\d+$")],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    allow_reentry=True
)

add_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("additem", list_handlers.add_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_ADD_ITEM: [CallbackQueryHandler(list_handlers.handle_add_item_list_selection, pattern=r"^select_list_to_add_item:\d+$")],
        list_handlers.GETTING_ITEM_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_text)]
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    allow_reentry=True
)

toggle_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("marcaritem", list_handlers.toggle_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_TOGGLE: [CallbackQueryHandler(list_handlers.handle_toggle_item_list_selection, pattern=r"^select_list_to_toggle:\d+$")],
        list_handlers.GETTING_ITEM_ID_TO_TOGGLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_id_to_toggle)]
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    allow_reentry=True
)

remove_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("removeritem", list_handlers.remove_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_REMOVE: [CallbackQueryHandler(list_handlers.handle_remove_item_list_selection, pattern=r"^select_list_to_remove:\d+$")],
        list_handlers.GETTING_ITEM_ID_TO_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_id_to_remove)]
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    allow_reentry=True
)

delete_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("apagarlista", list_handlers.delete_list_start)],
    states={
        list_handlers.CONFIRM_DELETE_LIST: [CallbackQueryHandler(list_handlers.handle_delete_list_confirmation, pattern=r"^(confirm_delete_list:\d+|cancel_list_action)$")]
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    allow_reentry=True
)

# reminders_handlers (lembretes)
add_reminder_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("addlembrete", reminders_handlers.add_reminder_start)],
    states={
        reminders_handlers.GETTING_REMINDER_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_description)],
        reminders_handlers.GETTING_REMINDER_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_datetime)],
        reminders_handlers.GETTING_REMINDER_RECURRENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_recurrence)]
    },
    fallbacks=[CommandHandler("cancelar", reminders_handlers.cancel_dialog)],
    allow_reentry=True
)

delete_reminder_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("apagarlembrete", reminders_handlers.delete_reminder_start)],
    states={
        reminders_handlers.GETTING_REMINDER_ID_FOR_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_id_to_delete)],
        reminders_handlers.CONFIRM_DELETE_REMINDER: [CallbackQueryHandler(reminders_handlers.handle_delete_reminder_confirmation, pattern=r"^(confirm_delete_reminder:\d+|cancel_reminder_delete)$")]
    },
    fallbacks=[CommandHandler("cancelar", reminders_handlers.cancel_dialog)],
    allow_reentry=True
)

# account_handlers (contas financeiras)
accounts_menu_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("contas", account_handlers.accounts_menu)],
    states={
        account_handlers.VIEW_ACCOUNTS_MENU: [
            CallbackQueryHandler(account_handlers.add_account_start, pattern="^accounts_action:add_account$"),
            CallbackQueryHandler(account_handlers.add_income_start, pattern="^accounts_action:add_income$"),
            CallbackQueryHandler(account_handlers.mark_account_paid_start, pattern="^accounts_action:mark_paid$"),
            CallbackQueryHandler(account_handlers.delete_account_start, pattern="^accounts_action:delete_account$"),
            CallbackQueryHandler(account_handlers.delete_income_start, pattern="^accounts_action:delete_income$"),
            CallbackQueryHandler(account_handlers.view_detailed_accounts, pattern="^accounts_action:view_accounts$"), # Função confirmada
            CallbackQueryHandler(account_handlers.view_detailed_incomes, pattern="^accounts_action:view_incomes$"), # Função confirmada
            CallbackQueryHandler(handlers.send_main_help_menu, pattern="^accounts_action:main_menu$") # Volta para o menu principal de ajuda
        ],
        account_handlers.VIEW_DETAILED_ACCOUNTS: [
             CallbackQueryHandler(account_handlers.accounts_menu, pattern="^accounts_action:main_menu$"), # Voltar para o menu principal de contas
        ],
        account_handlers.VIEW_DETAILED_INCOMES: [
             CallbackQueryHandler(account_handlers.accounts_menu, pattern="^accounts_action:main_menu$"), # Voltar para o menu principal de contas
        ],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow)],
    allow_reentry=True
)


add_account_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.add_account_start, pattern="^accounts_action:add_account$")],
    states={
        account_handlers.ADD_ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_name)],
        account_handlers.ADD_ACCOUNT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_amount)],
        account_handlers.ADD_ACCOUNT_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_due_date)],
        account_handlers.ADD_ACCOUNT_RECURRENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_recurrence)],
        account_handlers.ADD_ACCOUNT_PARCEL_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_parcel_count)]
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow)],
    allow_reentry=True
)

add_income_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.add_income_start, pattern="^accounts_action:add_income$")],
    states={
        account_handlers.ADD_INCOME_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_description)],
        account_handlers.ADD_INCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_amount)],
        account_handlers.ADD_INCOME_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_date)]
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow)],
    allow_reentry=True
)

mark_account_paid_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.mark_account_paid_start, pattern="^accounts_action:mark_paid$")],
    states={
        account_handlers.GET_ACCOUNT_ID_TO_MARK: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_id_to_mark)],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow)],
    allow_reentry=True
)

delete_account_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.delete_account_start, pattern="^accounts_action:delete_account$")],
    states={
        account_handlers.GET_ACCOUNT_ID_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_id_to_delete)],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow)],
    allow_reentry=True
)

delete_income_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.delete_income_start, pattern="^accounts_action:delete_income$")],
    states={
        account_handlers.GET_INCOME_ID_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_id_to_delete)],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow)],
    allow_reentry=True
)


# Outros CommandHandlers
application.add_handler(CommandHandler("minhasfrases", handlers.view_my_phrases))
application.add_handler(CommandHandler("listas", list_handlers.list_my_lists))
application.add_handler(CommandHandler("ver_lembretes", reminders_handlers.view_reminders)) # Verificado: view_reminders

# Handler para o menu de ajuda interativo (CallbackQueryHandler que lida com os botões)
application.add_handler(CallbackQueryHandler(handlers.handle_help_menu_callback, pattern=r"^help_category:.+$")) # NOVO HANDLER CRÍTICO AQUI

# Registra os ConversationHandlers
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

# REGISTRANDO NOVOS CONVERSATION HANDLERS DE CONTAS AQUI
application.add_handler(accounts_menu_conv_handler)
application.add_handler(add_account_conv_handler)
application.add_handler(add_income_conv_handler)
application.add_handler(delete_account_conv_handler)
application.add_handler(delete_income_conv_handler)
application.add_handler(mark_account_paid_conv_handler)


# Handlers para callbacks específicos de ações de lista (que não iniciam conversas, mas lidam com estados)
application.add_handler(CallbackQueryHandler(list_handlers.handle_list_item_action_callbacks,
                                             pattern="^(add_item_to_list|toggle_items_in_list|remove_items_from_list|view_lists_back):.*$|^view_lists_back$"))


# Handler para frases personalizadas (deve ser o último MessageHandler para não interceptar comandos)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_personal_phrase))

# Handler de cancelamento global (para casos que não estejam em ConversationHandlers específicos)
application.add_handler(CommandHandler("cancelar", handlers.cancel_dialog))


# Inicia o bot
if __name__ == "__main__":
    # Agendar lembretes existentes ao iniciar o bot
    # Garanta que o JobQueue esteja pronto antes de agendar
    reminders_handlers.schedule_existing_reminders(application.job_queue, application.bot)
    application.run_polling(allowed_updates=Update.ALL_TYPES)