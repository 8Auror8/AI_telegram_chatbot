# api/webhook.py
import os
import json
import logging
import asyncio # Necesario para ejecutar funciones async con asyncio.run()

# Configuración de log (para que puedas ver mensajes en los logs de Vercel)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importar librerías necesarias
import google.generativeai as genai
from dotenv import load_dotenv # Para desarrollo local. En Vercel, las variables son inyectadas.

# Importar las librerías de Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Cargar Variables de Entorno ---
# En Vercel, estas variables se inyectan directamente. Para probar en local, puedes usar .env.
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Verificar si las claves están presentes
if not GOOGLE_API_KEY:
    logger.error("GOOGLE_API_KEY no encontrada. Asegúrate de configurarla en Vercel o en tu .env local.")
    # En un entorno de producción real, podrías querer levantar una excepción aquí.
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN no encontrada. Asegúrate de configurarla en Vercel o en tu .env local.")
    # En un entorno de producción real, podrías querer levantar una excepción aquí.

# --- Configuración de la API de Gemini ---
genai.configure(api_key=GOOGLE_API_KEY)
llm_model = genai.GenerativeModel('gemini-1.5-flash')

# Diccionario para almacenar el historial de conversación por chat_id de Telegram
# ADVERTENCIA: En un entorno serverless como Vercel, este diccionario se reinicia
# con cada nueva solicitud (cada mensaje de Telegram). Esto significa que
# el bot no "recordará" el historial de conversación entre mensajes/turnos.
# Para mantener el historial, necesitarías una base de datos externa (ej. Redis, Supabase, Firestore).
# Para este Nivel 1 de despliegue, está bien, pero es una limitación a considerar.
user_chats = {}

# --- Funciones Manejadoras de Telegram (async) ---
# Estas son las mismas funciones 'start' y 'handle_message' que ya tienes.
# Asegúrate de copiarlas aquí con sus decoradores `async def`.

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in user_chats:
        user_chats[user_id] = llm_model.start_chat(history=[])

    await update.message.reply_text(f"¡Hola {update.effective_user.first_name}! Soy tu asistente de IA. Envíame un mensaje y conversaremos.")
    logger.info(f"Comando /start recibido de {user_id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    user_id = update.effective_user.id

    if user_id not in user_chats:
        user_chats[user_id] = llm_model.start_chat(history=[])

    chat_session = user_chats[user_id]

    try:
        response = await chat_session.send_message_async(user_message)

        if response.text:
            await update.message.reply_text(response.text)
            logger.info(f"Respuesta enviada a {user_id}: {response.text[:50]}...")
        else:
            finish_reason = None
            if response.candidates:
                first_candidate = response.candidates[0]
                if hasattr(first_candidate, 'finish_reason'):
                    finish_reason = first_candidate.finish_reason.name
                elif hasattr(first_candidate, 'safety_ratings') and first_candidate.safety_ratings:
                    for rating in first_candidate.safety_ratings:
                        if rating.blocked:
                            finish_reason = f"SEGURIDAD: {rating.category.name}"
                            break

            if finish_reason:
                if "RECITATION" in finish_reason:
                    await update.message.reply_text("Lo siento, no puedo proporcionar esa información directamente debido a restricciones de contenido (posible recitación de fuentes). Por favor, intenta reformular tu pregunta.")
                elif "SAFETY" in finish_reason:
                     await update.message.reply_text("Lo siento, no puedo responder a esa pregunta debido a nuestras políticas de seguridad de contenido. Por favor, intenta con otra pregunta.")
                else:
                    await update.message.reply_text(f"Lo siento, no pude generar una respuesta clara. Razón: {finish_reason}. ¿Puedes intentar reformular?")
            else:
                await update.message.reply_text("Lo siento, no pude generar una respuesta para esa pregunta. Por favor, intenta reformularla.")
            logger.warning(f"Respuesta vacía o filtrada para {user_id}. Razón: {finish_reason or 'Desconocida'}")

    except Exception as e:
        logger.error(f"Ocurrió un error al procesar el mensaje para el usuario {user_id}: {e}")
        await update.message.reply_text("Lo siento, hubo un error al procesar tu solicitud. Por favor, inténtalo de nuevo más tarde.")


# --- Función Principal que Vercel invocará ---
# Vercel espera una función 'handler' en tu archivo Python.
# Esta función recibirá un objeto 'request' y debe devolver una respuesta HTTP.
async def handler(request):
    """
    Función principal que Vercel invoca para manejar las solicitudes HTTP (webhooks).
    """
    logger.info(f"Petición recibida: {request.method} {request.url}")


    # Asegúrate de que el token esté disponible antes de construir la aplicación PTB
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no configurado en el handler de Vercel.")
        return {"body": "Internal Server Error: Bot Token not configured", "statusCode": 500}

    # Cada vez que llega un webhook, creamos una nueva instancia de Application.
    # Esto es normal en serverless.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Registra tus handlers dentro de la función de manejo de la petición.
    # Esto asegura que cada invocación de la función serverless tenga sus handlers listos.
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if request.method == 'POST':
        try:
            # Lee el cuerpo de la petición como JSON (esto viene de Telegram)
            update_data = await request.json()
            
            # Crea un objeto Update a partir del JSON recibido
            update = Update.de_json(update_data, application.bot)

            # Procesa la actualización. El dispatcher de PTB se encargará de llamar al handler correcto.
            # update.bot ya ha sido asignado al crear el objeto `update` arriba.
            await application.process_update(update)

            # Telegram espera un 200 OK para confirmar que se recibió el webhook.
            return {"body": "OK", "statusCode": 200}
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            # Devuelve un error para que Telegram sepa que algo falló, aunque a veces un 200 es mejor.
            # Para depurar, dejar el mensaje de error es útil.
            return {"body": f"Error: {e}", "statusCode": 500}
    else:
        # Para peticiones GET (ej. cuando abres la URL en el navegador)
        # Puedes poner un mensaje simple para verificar que la función está viva.
        return {"body": "Bot está corriendo (webhook endpoint). Envía una petición POST de Telegram.", "statusCode": 200}

    
    # **Notas Importantes sobre `api/webhook.py`:**
    # **Variables de Entorno:** `load_dotenv()` está ahí por si pruebas localmente. En Vercel, las variables (`GOOGLE_API_KEY`, `TELEGRAM_BOT_TOKEN`) se inyectarán directamente en el entorno de ejecución de la función.
    # **`user_chats`:** Reitero la advertencia. Para mantener el historial de conversación, necesitarás una base de datos externa. Por ahora, cada mensaje será como el inicio de una nueva conversación para el LLM.
    # **`async def handler(request)`:** Esta es la función principal que Vercel buscará y ejecutará cuando reciba una solicitud HTTP en la ruta configurada.