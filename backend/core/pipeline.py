"""
ClassInsight - Módulo de transcripción y análisis inteligente de clases universitaria.
Utiliza Amazon Transcribe, S3 y Amazon Bedrock (Claude 3 Haiku).
"""

import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv("CLASSINSIGHT_S3_BUCKET", "classinsight-ciap")
REGION = os.getenv("AWS_REGION", "us-east-1")
TRANSCRIBE_LANGUAGE_CODE = "es-US"
BEDROCK_MODEL_ID = "us.meta.llama3-1-8b-instruct-v1:0"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "data"
OUTPUT_FILENAME = "resultado_classinsight.md"


def get_aws_clients():
    """Crea clientes AWS reutilizando las credenciales configuradas en el entorno o ~/.aws."""
    session = boto3.Session(region_name=REGION)
    return {
        "s3": session.client("s3"),
        "transcribe": session.client("transcribe"),
        "bedrock": session.client("bedrock-runtime"),
    }


def upload_to_s3(s3_client, file_path: str, key: str | None = None) -> str:
    """Sube un archivo local a S3 y devuelve la clave del objeto."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

    if key is None:
        key = f"transcriptions/{file_path.stem}_{datetime.now():%Y%m%d_%H%M%S}{file_path.suffix}"

    logger.info("Subiendo '%s' a s3://%s/%s ...", file_path.name, S3_BUCKET, key)
    s3_client.upload_file(str(file_path), S3_BUCKET, key)
    logger.info("Archivo subido correctamente.")
    return key


def start_transcription(transcribe_client, s3_key: str) -> str:
    """Inicia un trabajo de transcripción en Amazon Transcribe y espera su finalización."""
    job_name = f"classinsight_{Path(s3_key).stem}_{int(time.time())}"
    media_uri = f"s3://{S3_BUCKET}/{s3_key}"

    logger.info("Iniciando trabajo de transcripción: %s", job_name)
    
    # NOTA DE SEGURIDAD/SIMPLICIDAD: Quitamos OutputBucketName. 
    # De esta forma, Transcribe guarda el resultado de forma segura en su propio servicio
    # y nos da una URL directa y temporal para descargarlo sin configurar políticas de S3 complejas.
    transcribe_client.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode=TRANSCRIBE_LANGUAGE_CODE,
        Media={"MediaFileUri": media_uri}
    )

    logger.info("Esperando finalización del trabajo de transcripción...")
    while True:
        response = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        status = response["TranscriptionJob"]["TranscriptionJobStatus"]
        if status == "COMPLETED":
            logger.info("Transcripción completada.")
            break
        if status == "FAILED":
            reason = response["TranscriptionJob"].get("FailureReason", "Desconocido")
            raise RuntimeError(f"El trabajo de transcripción falló: {reason}")
        logger.info("Estado: %s - esperando 10 s...", status)
        time.sleep(10)

    result_uri = response["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
    return result_uri

def download_and_extract_transcript(s3_client, result_uri: str) -> tuple[str, list[dict]]:
    """Descarga el JSON de resultados y extrae el texto y las marcas de tiempo."""
    import urllib.request

    logger.info("Descargando resultado de transcripción...")
    with urllib.request.urlopen(result_uri) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    full_text = data.get("results", {}).get("transcripts", [{}])[0].get("transcript", "")

    words_with_timestamps = []
    for item in data.get("results", {}).get("items", []):
        if item["type"] == "pronunciation":
            start = float(item.get("start_time", 0))
            end = float(item.get("end_time", 0))
            word = item.get("alternatives", [{}])[0].get("content", "")
            words_with_timestamps.append({"word": word, "start": start, "end": end})

    logger.info("Transcripción extraída: %d caracteres, %d palabras con timestamps.",
                len(full_text), len(words_with_timestamps))
    return full_text, words_with_timestamps


def _format_timestamp(seconds: float) -> str:
    """Convierte segundos a formato MM:SS."""
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins:02d}:{secs:02d}"


def _estimate_timestamp_for_sentence(words: list[dict], text: str) -> str:
    """Busca en la lista de palabras la marca de tiempo aproximada para un fragmento."""
    clean = text.lower().strip()
    for w in words:
        if w["word"].lower() in clean:
            return _format_timestamp(w["start"])
    return "N/A"


def analyze_with_bedrock(bedrock_client, full_text: str, words: list[dict]) -> str:
    """Envía el texto transcrito a Bedrock usando la Converse API moderna."""
    system_prompt = (
        "Eres un asistente educativo experto en análisis de clases. "
        "Basándote ÚNICAMENTE en la transcripción proporcionada, genera un entregable "
        "con la siguiente estructura estricta en formato Markdown:\n\n"
        "## 📝 Resumen General de la Clase\n"
        "(Un resumen ejecutivo, claro y estructurado por temas principales de lo que se habló en la clase).\n\n"
        "## 🚨 Puntos Críticos y Alertas de Exámenes\n"
        "(Lista detallada de CADA VEZ que el profesor mencione: exámenes, lecciones, pruebas, "
        "entrega de proyectos o tareas importantes. Para cada punto, debes incluir obligatoriamente "
        "el contexto de lo que se dijo y la marca de tiempo estimada en formato MM:SS basada en la transcripción)."
    )

    user_message = (
        f"Transcripción completa de la clase:\n\n"
        f"{full_text}\n\n"
        f"---\nPrimeras 50 palabras con marcas de tiempo para referencia temporal:\n"
        + json.dumps(words[:50], ensure_ascii=False, indent=2)
    )

    logger.info("Enviando transcripción a Amazon Bedrock usando Converse API (%s)...", BEDROCK_MODEL_ID)
    
    # Cambiamos invoke_model por converse(). Esto es un golazo para tu presentación.
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [{"text": user_message}]
            }
        ],
        system=[{"text": system_prompt}],
        inferenceConfig={
            "maxTokens": 4096,
            "temperature": 0.3
        }
    )

    assistant_text = response["output"]["message"]["content"][0]["text"]
    logger.info("Análisis con Bedrock completado con éxito.")
    return assistant_text


def save_output(content: str, output_path: Path | None = None) -> Path:
    """Guarda el resultado final en un archivo Markdown."""
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / OUTPUT_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.info("Resultado guardado en: %s", output_path)
    return output_path


def process_class_audio(audio_file_path: str) -> str:
    """Pipeline completo: upload → transcribe → análisis IA → output."""
    clients = get_aws_clients()

    s3_key = upload_to_s3(clients["s3"], audio_file_path)
    result_uri = start_transcription(clients["transcribe"], s3_key)
    full_text, words = download_and_extract_transcript(clients["s3"], result_uri)
    analysis = analyze_with_bedrock(clients["bedrock"], full_text, words)
    output_path = save_output(analysis)

    return str(output_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ClassInsight - Transcripción y análisis de clases")
    parser.add_argument("audio_file", help="Ruta al archivo .mp3 de la clase")
    args = parser.parse_args()

    try:
        result_path = process_class_audio(args.audio_file)
        print(f"\nProceso finalizado. Resultado: {result_path}")
    except FileNotFoundError as e:
        logger.error("Error: %s", e)
    except ClientError as e:
        logger.error("Error de AWS: %s", e.response["Error"]["Message"])
    except RuntimeError as e:
        logger.error("Error en transcripción: %s", e)
    except Exception as e:
        logger.error("Error inesperado: %s", e)
