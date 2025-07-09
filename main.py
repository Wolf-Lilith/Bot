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
    level=logging.WARNING # Alterado para INFO para mais detalhes
)

# Cria o bot
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Inicializa os bancos de dados
db.create_tables()
accounts_db.init_accounts_db() # Chamada para inicializar o DB de contas

# Inserir comandos no DB (se não existirem)
# Nota: A função 'function_name' é uma string para referência, não a função em si.
db.insert_command("start", "handlers.start_command", "Inicia o bot e te cumprimenta.")
db.insert_command("ajuda", "handlers.help_command", "Mostra o menu de ajuda interativo.")
db.insert_command("addfrase", "handlers.add_phrase_start", "Adiciona uma frase personalizada para eu responder.") # CORRIGIDO: new_phrase_start para add_phrase_start
db.insert_command("minhasfrases", "handlers.view_my_phrases", "Vê suas frases personalizadas.")
db.insert_command("apagarfrase", "handlers.delete_phrase_start", "Apaga uma frase personalizada existente.")
db.insert_command("novalista", "list_handlers.new_list_start", "Cria uma nova lista (ex: de compras, tarefas).")
db.insert_command("listas", "list_handlers.list_my_lists", "Mostra todas as suas listas.")
db.insert_command("verlistas", "list_handlers.list_my_lists", "Mostra suas listas existentes.") # CORRIGIDO: list_my_lists_start para list_my_lists
db.insert_command("additem", "list_handlers.add_item_start", "Adiciona um item a uma lista existente.")
db.insert_command("marcaritem", "list_handlers.toggle_item_start", "Marca/desmarca um item de lista como concluído.")
db.insert_command("removeritem", "list_handlers.remove_item_start", "Remove um item de uma lista.")
db.insert_command("apagarlista", "list_handlers.delete_list_start", "Apaga uma lista e todos os seus itens.")
db.insert_command("add_lembrete", "reminders_handlers.add_reminder_start", "Adiciona um novo lembrete (data/hora específica ou recorrente).")
db.insert_command("ver_lembretes", "reminders_handlers.view_reminders", "Vê todos os seus lembretes programados.") # CORRIGIDO: view_reminders_start para view_reminders
db.insert_command("apagar_lembrete", "reminders_handlers.delete_reminder_start", "Apaga um lembrete existente.")
db.insert_command("contas", "account_handlers.accounts_menu_start", "Gerencia suas contas e finanças.") # Novo comando para o módulo de contas

# Handlers gerais de comando
application.add_handler(CommandHandler("start", handlers.start_command))
application.add_handler(CommandHandler("ajuda", handlers.help_command))
application.add_handler(CallbackQueryHandler(handlers.handle_help_category_selection, pattern=r"^help_category:.+$")) # NOVO HANDLER CRÍTICO AQUI

application.add_handler(CommandHandler("minhasfrases", handlers.view_my_phrases))
application.add_handler(CommandHandler("listas", list_handlers.list_my_lists)) # Este é o handler para o comando /listas
application.add_handler(CommandHandler("ver_lembretes", reminders_handlers.view_reminders)) # Este é o handler para o comando /ver_lembretes
application.add_handler(CommandHandler("contas", account_handlers.accounts_menu)) # Handler para o comando /contas

# --- DEFINIÇÃO DOS CONVERSATION HANDLERS ---
# handlers.py (Frases Personalizadas)
add_phrase_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("addfrase", handlers.add_phrase_start)],
    states={
        handlers.GETTING_TRIGGER_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_trigger_phrase)],
        handlers.GETTING_RESPONSE_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_response_phrase)]
    },
    fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)]
)

delete_phrase_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("apagarfrase", handlers.delete_phrase_start)],
    states={
        handlers.GETTING_PHRASE_ID_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.confirm_delete_phrase)],
    },
    fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)]
)

# list_handlers.py (Listas)
new_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("novalista", list_handlers.new_list_start)],
    states={
        list_handlers.SELECTING_LIST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_new_list_name)],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)]
)

view_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("verlista", list_handlers.view_list_start)],
    states={
        list_handlers.VIEWING_LIST_COMMAND_START: [CallbackQueryHandler(list_handlers.display_specific_list)],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    map_to_parent={} # Isso é importante se você aninhar handlers e quiser que o cancelamento retorne ao pai
)

add_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("additem", list_handlers.add_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_ADD_ITEM: [CallbackQueryHandler(list_handlers.select_list_to_add_item)],
        list_handlers.GETTING_ITEM_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_text)],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)]
)

toggle_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("marcaritem", list_handlers.toggle_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_TOGGLE: [CallbackQueryHandler(list_handlers.select_list_to_toggle_item)],
        list_handlers.GETTING_ITEM_ID_TO_TOGGLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_id_to_toggle)],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)]
)

remove_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("removeritem", list_handlers.remove_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_REMOVE: [CallbackQueryHandler(list_handlers.select_list_to_remove_item)],
        list_handlers.GETTING_ITEM_ID_TO_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_id_to_remove)],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)]
)

delete_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("apagarlista", list_handlers.delete_list_start)],
    states={
        list_handlers.CONFIRM_DELETE_LIST: [CallbackQueryHandler(list_handlers.confirm_delete_list)],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)]
)


# reminders_handlers.py (Lembretes)
add_reminder_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("add_lembrete", reminders_handlers.add_reminder_start)],
    states={
        reminders_handlers.GETTING_REMINDER_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_description)],
        reminders_handlers.GETTING_REMINDER_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_datetime)],
        reminders_handlers.GETTING_REMINDER_RECURRENCE: [CallbackQueryHandler(reminders_handlers.get_reminder_recurrence)],
    },
    fallbacks=[CommandHandler("cancelar", reminders_handlers.cancel_dialog)]
)

delete_reminder_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("apagar_lembrete", reminders_handlers.delete_reminder_start)],
    states={
        reminders_handlers.GETTING_REMINDER_ID_FOR_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.confirm_delete_reminder_by_id)],
    },
    fallbacks=[CommandHandler("cancelar", reminders_handlers.cancel_dialog)]
)


# account_handlers.py (Contas Financeiras)
accounts_menu_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("contas", account_handlers.accounts_menu)],
    states={
        account_handlers.VIEW_ACCOUNTS_MENU: [CallbackQueryHandler(account_handlers.handle_accounts_menu_selection)],
        account_handlers.VIEW_DETAILED_ACCOUNTS: [CallbackQueryHandler(account_handlers.view_detailed_accounts)],
        account_handlers.VIEW_DETAILED_INCOMES: [CallbackQueryHandler(account_handlers.view_detailed_incomes)],
        # Adicione aqui os estados para outros menus de contas, se existirem
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow),
               CallbackQueryHandler(account_handlers.cancel_accounts_flow, pattern="^cancel_accounts_flow$")]
)

add_account_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.add_account_start, pattern="^accounts_action:add_account$")],
    states={
        account_handlers.ADD_ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_name)],
        account_handlers.ADD_ACCOUNT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_amount)],
        account_handlers.ADD_ACCOUNT_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_due_date)],
        account_handlers.ADD_ACCOUNT_RECURRENCE: [CallbackQueryHandler(account_handlers.get_account_recurrence)],
        account_handlers.ADD_ACCOUNT_PARCEL_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_account_parcel_count)],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow),
               CallbackQueryHandler(account_handlers.cancel_accounts_flow, pattern="^cancel_accounts_flow$")],
    per_user=True,
    per_chat=False,
    allow_reentry=True
)

add_income_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.add_income_start, pattern="^accounts_action:add_income$")],
    states={
        account_handlers.ADD_INCOME_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_description)],
        account_handlers.ADD_INCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_amount)],
        account_handlers.ADD_INCOME_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.get_income_date)],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow),
               CallbackQueryHandler(account_handlers.cancel_accounts_flow, pattern="^cancel_accounts_flow$")],
    per_user=True,
    per_chat=False,
    allow_reentry=True
)

delete_account_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.delete_account_start, pattern="^accounts_action:delete_account$")],
    states={
        account_handlers.GET_ACCOUNT_ID_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.confirm_delete_account)],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow),
               CallbackQueryHandler(account_handlers.cancel_accounts_flow, pattern="^cancel_accounts_flow$")],
    per_user=True,
    per_chat=False,
    allow_reentry=True
)

delete_income_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.delete_income_start, pattern="^accounts_action:delete_income$")],
    states={
        account_handlers.GET_INCOME_ID_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.confirm_delete_income)],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow),
               CallbackQueryHandler(account_handlers.cancel_accounts_flow, pattern="^cancel_accounts_flow$")],
    per_user=True,
    per_chat=False,
    allow_reentry=True
)

mark_account_paid_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(account_handlers.mark_account_paid_start, pattern="^accounts_action:mark_paid$")],
    states={
        account_handlers.GET_ACCOUNT_ID_TO_MARK: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_handlers.confirm_mark_account_paid)],
    },
    fallbacks=[CommandHandler("cancelar", account_handlers.cancel_accounts_flow),
               CallbackQueryHandler(account_handlers.cancel_accounts_flow, pattern="^cancel_accounts_flow$")],
    per_user=True,
    per_chat=False,
    allow_reentry=True
)


# Registra os ConversationHandlers
application.add_handler(add_phrase_conv_handler)
application.add_handler(delete_phrase_conv_handler)
application.add_handler(new_list_conv_handler)
application.add_handler(view_list_conv_handler)
application.add_handler(add_item_conv_handler)
application.add_handler(toggle_item_conv_handler)
application.add_handler(remove_item_conv_handler)
application.add_handler(delete_list_conv_handler)

# Registra os Callbacks para as ações gerais de lista (Adicionar, Marcar/Desmarcar, Remover, Voltar)
application.add_handler(CallbackQueryHandler(list_handlers.handle_list_item_action_callbacks, 
                                             pattern="^(add_item_to_list|toggle_items_in_list|remove_items_from_list|view_lists_back):.*$|^view_lists_back$"))


# Registra handlers de lembretes
application.add_handler(add_reminder_conv_handler)
application.add_handler(delete_reminder_conv_handler)


# REGISTRANDO NOVOS CONVERSATION HANDLERS DE CONTAS AQUI
application.add_handler(accounts_menu_conv_handler)
application.add_handler(add_account_conv_handler)
application.add_handler(add_income_conv_handler)
application.add_handler(delete_account_conv_handler)
application.add_handler(delete_income_conv_handler)
application.add_handler(mark_account_paid_conv_handler)


# Handler para frases personalizadas (deve ser o último MessageHandler para não interceptar comandos)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_personal_phrase))

# Handler de cancelamento global (para casos que não estejam em ConversationHandlers específicos)
application.add_handler(CommandHandler("cancelar", handlers.cancel_dialog))


# Inicia o bot
if __name__ == "__main__":
    # Agendar lembretes existentes ao iniciar o bot
    # Garanta que o JobQueue esteja pronto antes de agendar
    reminders_handlers.schedule_existing_reminders(application.job_queue, application.bot) # CORRIGIDO: passado application.bot

    application.run_polling(allowed_updates=Update.ALL_TYPES)