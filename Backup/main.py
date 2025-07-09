from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import Update
from handlers import GETTING_TRIGGER_PHRASE, GETTING_RESPONSE_PHRASE, GETTING_PHRASE_ID_TO_DELETE
import handlers
import list_handlers
import reminders_handlers
from secrets import TELEGRAM_BOT_TOKEN
import db
import logging

# Configuração de logging: Agora em INFO para ver mais detalhes do bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

# Cria o bot
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
db.create_tables()

# Inserir comandos no DB (se não existirem)
db.insert_command("start", "handlers.start_command", "Inicia o bot e te cumprimenta.")
db.insert_command("ajuda", "handlers.help_command", "Mostra o menu de ajuda interativo.") # Descrição atualizada
db.insert_command("addfrase", "handlers.add_phrase_start", "Adiciona uma frase personalizada para eu responder.") # CORRIGIDO AQUI
db.insert_command("minhasfrases", "handlers.view_my_phrases", "Vê suas frases personalizadas.")
db.insert_command("apagarfrase", "handlers.delete_phrase_start", "Apaga uma frase personalizada existente.")
db.insert_command("novalista", "list_handlers.new_list_start", "Cria uma nova lista (ex: de compras, tarefas).")
db.insert_command("listas", "list_handlers.list_my_lists", "Lista todas as suas listas.")
db.insert_command("verlista", "list_handlers.view_list_start", "Visualiza os itens de uma lista específica.")
db.insert_command("additem", "list_handlers.add_item_start", "Adiciona um item a uma lista existente.")
db.insert_command("marcaritem", "list_handlers.toggle_item_start", "Marca/desmarca um item como concluído.")
db.insert_command("removeritem", "list_handlers.remove_item_start", "Remove um item de uma lista.")
db.insert_command("apagarlista", "list_handlers.delete_list_start", "Apaga uma lista inteira e seus itens.")
db.insert_command("add_lembrete", "reminders_handlers.add_reminder_start", "Define um novo lembrete.") # CORRIGIDO AQUI: Nome da função
db.insert_command("ver_lembretes", "reminders_handlers.view_reminders", "Vê seus lembretes agendados.")
db.insert_command("apagar_lembrete", "reminders_handlers.delete_reminder_start", "Apaga um lembrete existente.") # CORRIGIDO AQUI: Nome da função
db.insert_command("cancelar", "handlers.cancel_dialog", "Cancela a operação atual.")


# --- Handlers de Conversa para Frases Personalizadas ---
add_phrase_conv_handler = ConversationHandler( # Renomeado para consistência
    entry_points=[CommandHandler("addfrase", handlers.add_phrase_start)],
    states={
        handlers.GETTING_TRIGGER_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_trigger_phrase)],
        handlers.GETTING_RESPONSE_PHRASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_response_phrase)],
    },
    fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog)],
    per_user=True
)

delete_phrase_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("apagarfrase", handlers.delete_phrase_start)],
    states={
        GETTING_PHRASE_ID_TO_DELETE: [
            CallbackQueryHandler(handlers.delete_phrase_confirm, pattern=r"^delete_phrase_id:(\d+)$"),
            CallbackQueryHandler(handlers.cancel_dialog, pattern="^cancel_delete_phrase$")
        ],
    },
    fallbacks=[CommandHandler("cancelar", handlers.cancel_dialog),
               MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.cancel_dialog)],
    # Mantido per_message=False por ora, pois o CallbackQueryHandler está tratando a seleção
    # e não há um MessageHandler que esperaria algo do usuário neste estado.
    per_message=False
)


# --- Handlers de Conversa para Listas ---
new_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("novalista", list_handlers.new_list_start)],
    states={
        list_handlers.SELECTING_LIST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.create_new_list_name)],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    per_user=True
)

view_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("verlista", list_handlers.view_list_start)],
    states={
        list_handlers.VIEWING_LIST_COMMAND_START: [
            CallbackQueryHandler(list_handlers.view_specific_list, pattern=r"^select_list:\d+$"),
            CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern="^cancel_list_action$")
            # Removido MessageHandler para evitar conflito com CallbackQueryHandler no mesmo estado
            # MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.view_specific_list),
        ],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    # Aumentado a abrangência do CallbackQueryHandler, então per_message=True é mais adequado
    per_message=True, # Alterado para True para melhor rastreamento de callbacks
    allow_reentry=True
)

add_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("additem", list_handlers.add_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_ADD_ITEM: [
            CallbackQueryHandler(list_handlers.add_item_to_selected_list, pattern=r"^select_list:\d+$"),
            CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern="^cancel_list_action$")
            # Removido MessageHandler
            # MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.add_item_to_selected_list),
        ],
        list_handlers.GETTING_ITEM_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_text)],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    per_user=True # Mantido per_user=True aqui
)

toggle_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("marcaritem", list_handlers.toggle_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_TOGGLE: [
            CallbackQueryHandler(list_handlers.get_item_id_to_toggle, pattern=r"^select_list:\d+$"),
            CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern="^cancel_list_action$")
            # Removido MessageHandler
            # MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_id_to_toggle),
        ],
        list_handlers.GETTING_ITEM_ID_TO_TOGGLE: [CallbackQueryHandler(list_handlers.toggle_item_status, pattern=r"^toggle_item:\d+$")], # Adicionado pattern específico para toggle
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    per_user=True # Mantido per_user=True
)

remove_item_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("removeritem", list_handlers.remove_item_start)],
    states={
        list_handlers.SELECTING_LIST_TO_REMOVE: [
            CallbackQueryHandler(list_handlers.get_item_id_to_remove, pattern=r"^select_list:\d+$"),
            CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern="^cancel_list_action$")
            # Removido MessageHandler
            # MessageHandler(filters.TEXT & ~filters.COMMAND, list_handlers.get_item_id_to_remove),
        ],
        list_handlers.GETTING_ITEM_ID_TO_REMOVE: [CallbackQueryHandler(list_handlers.remove_item_from_list, pattern=r"^remove_item:\d+$")], # Adicionado pattern específico para remover
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    per_user=True # Mantido per_user=True
)

delete_list_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("apagarlista", list_handlers.delete_list_start)],
    states={
        list_handlers.CONFIRM_DELETE_LIST: [
            CallbackQueryHandler(list_handlers.confirm_delete_list, pattern=r"^confirm_delete_list:\d+:.+$"),
            CallbackQueryHandler(list_handlers.cancel_list_dialog, pattern="^cancel_list_action$")
        ],
    },
    fallbacks=[CommandHandler("cancelar", list_handlers.cancel_list_dialog)],
    # Aumentado a abrangência do CallbackQueryHandler, então per_message=True é mais adequado
    per_message=True # Alterado para True para melhor rastreamento de callbacks
)


# --- Handlers de Conversa para Lembretes ---
add_reminder_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("add_lembrete", reminders_handlers.add_reminder_start)], # CORRIGIDO AQUI
    states={
        reminders_handlers.GETTING_REMINDER_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_description)],
        reminders_handlers.GETTING_REMINDER_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminders_handlers.get_reminder_datetime)],
        reminders_handlers.GETTING_REMINDER_RECURRENCE: [CallbackQueryHandler(reminders_handlers.get_reminder_recurrence, pattern=r"^recurrence:.+$")], # CORRIGIDO AQUI: Usar CallbackQueryHandler
    },
    fallbacks=[CommandHandler("cancelar", reminders_handlers.cancel_dialog)],
    per_user=True
)

delete_reminder_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("apagar_lembrete", reminders_handlers.delete_reminder_start)], # CORRIGIDO AQUI
    states={
        reminders_handlers.GETTING_REMINDER_ID_FOR_DELETE: [ # CORRIGIDO AQUI: Usar o estado correto
            CallbackQueryHandler(reminders_handlers.confirm_delete_reminder, pattern=r"^delete_reminder:\d+$|^cancel_reminder_delete$") # CORRIGIDO AQUI: Pattern e função
        ],
    },
    fallbacks=[CommandHandler("cancelar", reminders_handlers.cancel_dialog)],
    per_user=True
)


# Registra os handlers de comandos simples
application.add_handler(CommandHandler("start", handlers.start_command))
application.add_handler(CommandHandler("ajuda", handlers.help_command)) # Mantém o handler principal

# Adiciona o CallbackQueryHandler para o novo menu de ajuda
application.add_handler(CallbackQueryHandler(handlers.handle_help_category_callbacks, pattern=r"^help_category:.+$")) # NOVO HANDLER CRÍTICO AQUI

application.add_handler(CommandHandler("minhasfrases", handlers.view_my_phrases))
application.add_handler(CommandHandler("listas", list_handlers.list_my_lists))
application.add_handler(CommandHandler("ver_lembretes", reminders_handlers.view_reminders))


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


# Handler para frases personalizadas (deve ser o último MessageHandler para não interceptar comandos)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_personal_phrase))

# Handler de cancelamento global (para casos que não estejam em ConversationHandlers específicos)
application.add_handler(CommandHandler("cancelar", handlers.cancel_dialog))


# Inicia o bot
if __name__ == "__main__":
    reminders_handlers.schedule_existing_reminders(application.job_queue, application) # Alterado aqui para passar 'application' ao invés de 'application.bot'
    application.run_polling(allowed_updates=Update.ALL_TYPES)