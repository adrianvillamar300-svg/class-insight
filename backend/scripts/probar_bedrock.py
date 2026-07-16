import os
import json
import logging
import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Configuración básica
REGION = "us-east-1"
BEDROCK_MODEL_ID = "us.meta.llama3-1-8b-instruct-v1:0"

def analizar_texto_con_bedrock():
    # 1. Leer el archivo de texto simulado
    try:
        with open("simulacion.txt", "r", encoding="utf-8") as f:
            full_text = f.read()
    except FileNotFoundError:
        logger.error("No se encontró el archivo 'simulacion.txt'. Por favor créalo primero.")
        return

    # 2. Inicializar cliente de Bedrock
    session = boto3.Session(region_name=REGION)
    bedrock_client = session.client("bedrock-runtime")

    # 3. Preparar Prompts
    system_prompt = (
        "Eres un asistente educativo experto en análisis de clases. "
        "Basándote ÚNICAMENTE en el texto proporcionado, genera un entregable "
        "con la siguiente estructura estricta en formato Markdown:\n\n"
        "## 📝 Resumen General de la Clase\n"
        "(Un resumen ejecutivo, claro y estructurado por temas principales de lo que se habló en la clase).\n\n"
        "## 🚨 Puntos Críticos y Alertas de Exámenes\n"
        "(Lista detallada de CADA VEZ que el profesor mencione: exámenes, lecciones, pruebas, "
        "entrega de proyectos o tareas importantes. Para cada punto, debes incluir obligatoriamente "
        "el contexto de lo que se dijo y la fecha/marca de tiempo estimada)."
    )

    logger.info("Enviando texto simulado a Amazon Bedrock (%s)...", BEDROCK_MODEL_ID)

    try:
        # LLamada oficial con Converse API
        response = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": f"Aquí está el texto de la clase:\n\n{full_text}"}]
                }
            ],
            system=[{"text": system_prompt}],
            inferenceConfig={
                "maxTokens": 2048,
                "temperature": 0.3
            }
        )

        # Extraer respuesta
        resultado_ia = response["output"]["message"]["content"][0]["text"]
        
        # Guardar resultado localmente
        with open("resultado_classinsight.md", "w", encoding="utf-8") as out:
            out.write(resultado_ia)
            
        logger.info("¡Éxito! El reporte se guardó en 'resultado_classinsight.md'")
        print("\n=== RESPUESTA DE BEDROCK ===\n")
        print(resultado_ia)

    except Exception as e:
        logger.error("Error al conectar con Bedrock: %s", e)

if __name__ == "__main__":
    analizar_texto_con_bedrock()