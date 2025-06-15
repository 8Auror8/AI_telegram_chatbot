# Importar librerías necesarias (ej. google-generativeai)
import google.generativeai as genai
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes



# -------------------------  CARGA KEYS DE .ENV --------------------------------
load_dotenv()

# Carga de APIS desde .env
API_KEY = os.getenv("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
genai.configure(api_key=API_KEY)

# Conexión API con LLM
llm_model = genai.GenerativeModel('gemini-1.5-flash')

# -------------------------- VARIABLES  -------------------------------------------
# Diccionario para almacenar el estado de la conversación (historial) por cada chat_id de Telegram
# Esto es crucial para que el LLM "recuerde" conversaciones con diferentes usuarios.
user_chats = {}


# -------------------------- FUNCTIONS -------------------------------------------

# Función Telegram => Crear Handler para el comando /start. Async para que varios usuarios puedan chatear a la vez con el bot.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # obtiene el userID
    user_id = update.effective_user.id
    # si el user_id no está en los user_chats, significa que es un nuevo user, por lo que le da la bienvenida.
    if user_id not in user_chats:
        user_chats[user_id] = llm_model.start_chat(history=[])
    await update.message.reply_text('¡Hola! Soy tu asistente de IA. Envíame un mensaje para empezar a conversar.')

# Función telegram para recordar los chats anteriores de un usuario específico => Handler para los mensajes de texto
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # selecciona el mensaje del usuario
    user_message = update.message.text
    # selecciona el user id
    user_id = update.effective_user.id

    # Asegúrate de que el chat_id tenga un historial de conversación. Si el usuario es nuevo y no tiene chat de conversación
    # se le añade uno vacío.
    if user_id not in user_chats:
        user_chats[user_id] = llm_model.start_chat(history=[])

    chat = user_chats[user_id]

    print(f"[{user_id}] Tú: {user_message}") # Para ver en la consola lo que el usuario envía

    try:
        # Enviar el mensaje al LLM
        response = chat.send_message(user_message)
        ai_response = response.text
        
        print(f"[{user_id}] IA: {ai_response}") # Para ver en la consola lo que el LLM responde
        
        # Enviar la respuesta del LLM de vuelta al usuario en Telegram
        await update.message.reply_text(ai_response)
    except Exception as e:
        error_message = f"Ocurrió un error al procesar tu mensaje: {e}"
        print(f"[{user_id}] Error: {error_message}")
        await update.message.reply_text("Lo siento, hubo un problema al procesar tu solicitud. Inténtalo de nuevo más tarde.")

# Función telegram para manejar los errores => Handler para manejar errores
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Update {update} causó error {context.error}")


# Función principal para iniciar el bot de Telegram

def main() -> None:
    # Crear la aplicación y pasar el token de tu bot.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Añadir los handlers al despachador.
    # El CommandHandler para /start
    application.add_handler(CommandHandler("start", start))
    # El MessageHandler para cualquier mensaje de texto (que no sea un comando)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Handler para errores
    application.add_error_handler(error_handler)

    print("Bot de Telegram iniciado. Envíale un mensaje a tu bot en Telegram.")
    # Iniciar el bot (usa Long Polling para recibir actualizaciones).
    application.run_polling(allowed_updates=Update.ALL_TYPES)


# Dejamos de usar las funciones def iniciar_conversacion(): y def conversar(chat): ya que pasamos de un flujo secuencial
'''
Script de Consola: Control lineal, input() bloqueante, una única sesión de conversación global.
iniciar_conversacion y conversar estructuran este flujo secuencial.
'''

# A un flujo event-driven y asíncrono
'''
Bot de Telegram: Control basado en eventos y asíncrono. El bot está "siempre encendido" escuchando.
Cada mensaje de un usuario es un evento que dispara una función (handle_message). Necesitamos gestionar
múltiples sesiones de conversación (user_chats) porque hay múltiples usuarios interactuando de forma concurrente e impredecible.
'''

# # Función para iniciar una conversación
# def iniciar_conversacion():
#     chat = llm_model.start_chat(history=[])
#     print("\n¡Hola! Soy tu asistente de IA. Escribe 'salir' para terminar.")
#     return chat

# # Bucle principal de la conversación
# def conversar(chat):
#     while True:
#         user_message = input("\nTú: ")
#         if user_message.lower() == 'salir':
#             print("¡Hasta luego!")
#             break

#         try:
#             response = chat.send_message(user_message)
#             print(f"\nIA: {response.text}")
#         except Exception as e:
#             print(f"Ocurrió un error: {e}")

# -------------------------------------- EXECUTE ------------------------------------------------
# if __name__ == "__main__":
#     current_chat = iniciar_conversacion()
#     conversar(current_chat)


# It is needed to create a chatbot from Telegram to be able to connect it within this Script.
if __name__ == "__main__":
    main()