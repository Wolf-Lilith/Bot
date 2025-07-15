from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
import handlers
import list_handlers
import reminders_handlers
import account_handlers 
from secrets import TELEGRAM_BOT_TOKEN
import db
import accounts_db
import logging

# Configuração de logging: CENTRALIZADA AQUI para todo o bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
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
    db.insert_command("listas", "list_handlers.list_my_lists_menu", "Gerencia suas listas existentes.") 
    db.insert_command("verlista", "list_handlers.view_list_start", "Vê os itens de uma lista específica.")
    db.insert_command("additem", "list_handlers.add_item_start", "Adiciona um item a uma lista existente.")
    db.insert_command("marcaritem", "list_handlers.toggle_item_start", "Marca/desmarca um item de uma lista como completo.")
    db.insert_command("removeritem", "list_handlers.remove_item_start", "Remover um item específico de uma lista.")
    db.insert_command("apagarlista", "list_handlers.delete_list_start", "Apaga uma lista e todos os seus itens.")
    db.insert_command("add_lembrete", "reminders_handlers.add_reminder_start", "Adiciona um novo lembrete com data e hora.")
    db.insert_command("ver_lembretes", "reminders_handlers.view_reminders", "Vê todos os seus lembretes programados.")
    db.insert_command("apagar_lembrete", "reminders_handlers.delete_reminder_start", "Apaga um lembrete existente.")
    db.insert_command("contas", "account_handlers.accounts_menu", "Gerencia suas contas financeiras.")
    db.insert_command("cancelar", "handlers.cancel_dialog", "Cancela qualquer operação ou diálogo em andamento.")
    db.insert_command("lembretes", "handlers.reminders_menu", "Abre o menu de gerenciamento de lembretes.") 

    # --- Registra os CommandHandlers ---
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("ajuda", handlers.help_command))
    application.add_handler(CommandHandler("lembretes", handlers.reminders_menu))
    application.add_handler(CommandHandler("contas", account_handlers.accounts_menu)) 

    application.add_handler(CallbackQueryHandler(handlers.send_help_category_menu, pattern=r"^help_category:(phrases|lists|reminders|general|accounts|main_menu)$"))
    
    # Handlers de visualização simples que não iniciam conversas
    application.add_handler(CommandHandler("minhasfrases", handlers.view_my_phrases))
    application.add_handler(CallbackQueryHandler(handlers.view_my_phrases, pattern=r"^command:/minhasfrases$"))
    
    # Handler para o botão "Sair" unificado (agora também no menu principal)
    application.add_handler(CallbackQueryHandler(handlers.cancel_dialog, pattern=r"^cancel_dialog_action$"))

    # --- NOVO HANDLER PARA BOTÕES 'SHOW COMMAND' ---
    application.add_handler(CallbackQueryHandler(handlers.show_command_and_return_to_main_menu, pattern=r"^show_command:/(start|ajuda)$"))


    # --- Registra os ConversationHandlers ---

    # Frases Personalizadas
    add_phrase_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("addfrase", handlers.new_phrase_start),
            CallbackQueryHandler(handlers.new_phrase_start, pattern=r"^command:/addfrase$")
        ],
        states={
            handlers.GETTING_TRIGGER_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_trigger_phrase)],
            handlers.GETTING_RESPONSE_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_response_phrase)],
            handlers.AWAIT_NEXT_PHRASE_ACTION: [CallbackQueryHandler(handlers.handle_next_phrase_action, pattern="^(add_another_phrase|help_category:main_menu|cancel_dialog_action)$")],
        },
        fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)],
        allow_reentry=True
    )
    # ConversationHandler para Apagar Frase com seleção por botão
    delete_phrase_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("apagarfrase", handlers.delete_phrase_start),
            CallbackQueryHandler(handlers.delete_phrase_start, pattern=r"^command:/apagarfrase$")
        ],
        states={
            handlers.AWAIT_NEXT_DELETE_ACTION: [
                CallbackQueryHandler(handlers.delete_phrase_select_and_confirm, pattern=r"^delete_phrase_id:\d+$"),
                CallbackQueryHandler(handlers.handle_next_delete_action, pattern="^(delete_another_phrase|help_category:main_menu|cancel_dialog_action)$"),
            ],
        },
        fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)],
        allow_reentry=True
    )

    # Listas
    application.add_handler(CommandHandler("listas", list_handlers.list_my_lists_menu))
    application.add_handler(CallbackQueryHandler(list_handlers.list_my_lists_menu, pattern=r"^command:/listas$"))
    
    application.add_handler(CallbackQueryHandler(list_handlers.handle_list_item_action_callbacks, 
                                                 pattern=r"^list_action:main_menu$|" + 
                                                         r"^help_category:main_menu$|" + 
                                                         r"^cancel_list_action$")) 

    # --- ConversationHandlers de Listas ---
    new_list_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("novalista", list_handlers.new_list_start),
            CallbackQueryHandler(list_handlers.new_list_start, pattern=r"^list_action:new_list$") 
        ],
        states={
            list_handlers.SELECTING_LIST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_list_name)],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    
    view_list_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("verlista", list_handlers.view_list_start),
            CallbackQueryHandler(list_handlers.view_list_start, pattern=r"^list_action:select_existing_list$"), 
            CallbackQueryHandler(lambda update, context: list_handlers.view_list_start(update, context, pre_selected_list_id=int(update.callback_query.data.split(':')[2])), pattern=r"^list_action:view_items:(\d+)$") 
        ],
        states={
            list_handlers.VIEWING_LIST_COMMAND_START: [
                CallbackQueryHandler(list_handlers.get_list_to_view, pattern=r'^select_list_id_for_action:\d+$'), 
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$'), 
                CallbackQueryHandler(list_handlers.list_my_lists_menu, pattern="^list_action:main_menu$"), 
                CallbackQueryHandler(handlers.send_main_help_menu, pattern="^help_category:main_menu$"), 
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    
    add_item_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("additem", list_handlers.add_item_start),
            CallbackQueryHandler(list_handlers.add_item_start, pattern=r"^list_action:add_item$"), 
            CallbackQueryHandler(lambda update, context: list_handlers.add_item_start(update, context, pre_selected_list_id=int(update.callback_query.data.split(':')[2])), pattern=r"^list_action:add_item_to_list:(\d+)$")
        ],
        states={
            list_handlers.SELECTING_LIST_TO_ADD_ITEM: [
                CallbackQueryHandler(list_handlers.get_list_to_add_item, pattern=r'^select_list_id_for_action:\d+$'),
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
        entry_points=[
            CommandHandler("marcaritem", list_handlers.toggle_item_start),
            CallbackQueryHandler(list_handlers.toggle_item_start, pattern=r"^list_action:toggle_item$"), 
            CallbackQueryHandler(lambda update, context: list_handlers.toggle_item_start(update, context, pre_selected_list_id=int(update.callback_query.data.split(':')[2])), pattern=r"^list_action:toggle_item_in_list:(\d+)$")
        ],
        states={
            list_handlers.SELECTING_LIST_TO_TOGGLE: [
                CallbackQueryHandler(list_handlers.get_list_to_toggle_item, pattern=r'^select_list_id_for_action:\d+$'), 
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$') 
            ],
            list_handlers.GETTING_ITEM_ID_TO_TOGGLE: [
                CallbackQueryHandler(list_handlers.process_toggle_item_callback, pattern=r'^toggle_item_id:\d+$'), 
                CommandHandler("cancelar", list_handlers.cancel_list_dialog)
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    remove_item_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("removeritem", list_handlers.remove_item_start),
            CallbackQueryHandler(list_handlers.remove_item_start, pattern=r"^list_action:remove_item$"), 
            CallbackQueryHandler(lambda update, context: list_handlers.remove_item_start(update, context, pre_selected_list_id=int(update.callback_query.data.split(':')[2])), pattern=r"^list_action:remove_item_from_list:(\d+)$")
        ],
        states={
            list_handlers.SELECTING_LIST_TO_REMOVE: [
                CallbackQueryHandler(list_handlers.get_list_to_remove_item, pattern=r'^select_list_id_for_action:\d+$'), 
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$') 
            ],
            list_handlers.GETTING_ITEM_ID_TO_REMOVE: [
                CallbackQueryHandler(list_handlers.process_remove_item_callback, pattern=r'^remove_item_id:\d+$'), 
                CommandHandler("cancelar", list_handlers.cancel_list_dialog)
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )
    delete_list_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("apagarlista", list_handlers.delete_list_start),
            CallbackQueryHandler(list_handlers.delete_list_start, pattern=r"^list_action:delete_list$"), 
            CallbackQueryHandler(lambda update, context: list_handlers.delete_list_start(update, context, pre_selected_list_id=int(update.callback_query.data.split(':')[2])), pattern=r"^list_action:delete_specific_list:(\d+)$")
        ],
        states={
            list_handlers.SELECTING_LIST_TO_DELETE: [ 
                CallbackQueryHandler(list_handlers.get_list_to_delete, pattern=r'^select_list_id_for_action:\d+$'), 
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$') 
            ],
            list_handlers.CONFIRM_DELETE_LIST: [
                CallbackQueryHandler(list_handlers.delete_list_confirm_action, pattern=r'^confirm_delete_list_action:\d+$'), 
                CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern='^cancel_list_action$') 
            ],
        },
        fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
        allow_reentry=True
    )

    # Lembretes - ConversationHandler único para todos os fluxos de lembretes
    reminders_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add_lembrete", reminders_handlers.add_reminder_start),
            CallbackQueryHandler(reminders_handlers.add_reminder_start, pattern=r"^command:/add_lembrete$"),
            CommandHandler("ver_lembretes", reminders_handlers.view_reminders), 
            CallbackQueryHandler(reminders_handlers.view_reminders, pattern=r"^command:/ver_lembretes$"), 
            CommandHandler("apagar_lembrete", reminders_handlers.delete_reminder_start),
            CallbackQueryHandler(reminders_handlers.delete_reminder_start, pattern=r"^command:/apagar_lembrete$"),
        ],
        states={
            reminders_handlers.GETTING_REMINDER_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_desc)],
            
            # NOVOS ESTADOS E HANDLERS PARA SELEÇÃO DE DATA/HORA
            reminders_handlers.GETTING_REMINDER_DATE_FROM_CALENDAR: [
                CallbackQueryHandler(reminders_handlers.handle_calendar_callback_reminders, pattern=r"^rem_cal:"),
            ],
            reminders_handlers.GETTING_REMINDER_HOUR: [
                CallbackQueryHandler(reminders_handlers.get_reminder_hour, pattern=r"^rem_hour:|^cancel_reminder_add$"),
            ],
            reminders_handlers.GETTING_REMINDER_MINUTE: [
                CallbackQueryHandler(reminders_handlers.get_reminder_minute, pattern=r"^rem_minute:|^cancel_reminder_add$"),
            ],

            # ESTADO EXISTENTE AGORA RECEBERÁ O scheduled_time PRONTO
            reminders_handlers.GETTING_REMINDER_RECURRENCE: [
                CallbackQueryHandler(reminders_handlers.get_reminder_recurrence, pattern="^(daily|weekly|monthly|yearly|none|cancel_reminder_add)$"), 
            ],
            # MODIFICADO: GETTING_REMINDER_ID_FOR_DELETE agora aceita CallbackQuery
            reminders_handlers.GETTING_REMINDER_ID_FOR_DELETE: [
                CallbackQueryHandler(reminders_handlers.delete_reminder_confirm, pattern=r"^delete_reminder_id:\d+$|^cancel_reminder_delete_op$"), 
            ],
            
            # NOVOS ESTADOS PARA FOLLOW-UP MENUS
            reminders_handlers.AWAIT_REMINDER_ADD_ACTION: [
                CallbackQueryHandler(reminders_handlers.handle_add_reminder_action, pattern=r"^reminder_add_action:|^help_category:main_menu$|^cancel_dialog_action$"),
            ],
            reminders_handlers.AWAIT_REMINDER_VIEW_ACTION: [
                CallbackQueryHandler(reminders_handlers.handle_view_reminder_action, pattern=r"^reminder_view_action:|^help_category:main_menu$|^cancel_dialog_action$"),
            ],
            reminders_handlers.AWAIT_REMINDER_DELETE_ACTION: [
                CallbackQueryHandler(reminders_handlers.handle_delete_reminder_action, pattern=r"^reminder_delete_action:|^help_category:main_menu$|^cancel_dialog_action$"),
            ],
        },
        fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)],
        allow_reentry=True
    )

    # --- Contas Financeiras: UNIFICADO EM UM ÚNICO ConversationHandler ---
    accounts_conv_handler = account_handlers.setup_accounts_handlers()

    application.add_handler(add_phrase_conv_handler)
    application.add_handler(delete_phrase_conv_handler)
    application.add_handler(new_list_conv_handler)
    application.add_handler(add_item_conv_handler)
    application.add_handler(toggle_item_conv_handler)
    application.add_handler(remove_item_conv_handler)
    application.add_handler(delete_list_conv_handler)
    
    application.add_handler(reminders_conv_handler) 
    
    application.add_handler(accounts_conv_handler)
    
    application.add_handler(view_list_conv_handler)


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