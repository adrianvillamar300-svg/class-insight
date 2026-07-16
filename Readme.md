# 🎓 ClassInsight: Copiloto Educativo con IA Generativa y AWS

**ClassInsight** es una solución inteligente diseñada para optimizar el estudio universitario mediante Inteligencia Artificial y una arquitectura híbrida. Permite procesar grabaciones de audio de clases (.mp3), transcribirlas automáticamente con marcas de tiempo mediante **Amazon Transcribe**, y analizarlas con **Amazon Bedrock (Llama 3.1 8B Instruct)** para extraer resúmenes estructurados y alertas críticas de exámenes, lecciones o tareas, garantizando la privacidad absoluta de los datos académicos.

---

## 📁 Estructura del Proyecto

```
class_insight/
├── .env                     # Credenciales AWS (NO commitear)
├── .gitignore
├── README.md
├── images/
│   └── ciap.png
├── backend/
│   ├── __init__.py
│   ├── app.py               # API FastAPI (endpoints)
│   ├── requirements.txt     # Dependencias Python
│   ├── core/
│   │   ├── __init__.py
│   │   └── pipeline.py      # Lógica: S3 → Transcribe → Bedrock
│   ├── scripts/
│   │   └── probar_bedrock.py
│   └── data/
│       └── simulacion.txt
└── frontend/
    └── index.html           # Interfaz web (Tailwind CSS)
```

## 🏗️ Arquitectura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌───────────┐
│  Frontend   │────▶│  FastAPI     │────▶│  AWS S3     │────▶│ Transcribe│
│  (HTML/JS)  │     │  (Backend)   │     │  (Storage)  │     │  (STT)    │
└─────────────┘     └──────┬───────┘     └─────────────┘     └─────┬─────┘
                           │                                        │
                           │           ┌─────────────┐             │
                           └──────────▶│  Bedrock    │◀────────────┘
                                       │  (Llama 3)  │
                                       └─────────────┘
```

---

## 📋 Requisitos Previos

Asegúrate de tener instalado en tu máquina local:
- Python 3.10+
- Pip (Administrador de paquetes de Python)
- Una cuenta activa de AWS (con la capa gratuita o créditos de estudiante)

---

## 🛠️ Configuración en AWS (Paso a Paso)

### 1. Registro en AWS
- Regístrate en [AWS](https://aws.amazon.com/es/resources/create-account/) usando tu correo institucional (ej: `@espol.edu.ec`).

### 2. Crear un Bucket de Amazon S3
1. Ve al servicio **S3** en la consola de AWS.
2. Haz clic en **Create bucket**.
3. En **Bucket name**, ingresa un nombre único a nivel mundial (por ejemplo: `classinsight-ciap`).
4. Selecciona la región **US East (N. Virginia) us-east-1**.
5. Deja las demás opciones por defecto y haz clic en **Create bucket**.

### 3. Crear el Usuario IAM y Obtener Credenciales (Keys)
1. Ve al servicio **IAM** (Identity and Access Management).
2. En el menú izquierdo, ve a **Users** y haz clic en **Create user**.
3. Asigna un nombre al usuario (ej. `classinsight-backend`) y haz clic en *Next*.
4. Selecciona **Attach policies directly** (Asociar políticas directamente) y busca/marca las siguientes tres políticas:
   - `AmazonTranscribeFullAccess`
   - `AmazonBedrockFullAccess`
   - `AmazonS3FullAccess`
5. Haz clic en *Next* y luego en **Create user**.
6. Haz clic sobre el usuario creado, ve a la pestaña **Security credentials**.
7. En la sección **Access keys**, haz clic en **Create access key**.
8. Selecciona la opción **Local code**, avanza y descarga el archivo `.csv` con tus llaves:
   - `AWS Access Key ID`
   - `AWS Secret Access Key` *(Guárdala bien, no se volverá a mostrar)*.

---

## 🛠️ Configuración del Proyecto

### 1. Clonar el repositorio
```bash
git clone <repo-url>
cd class_insight
```

### 2. Crear y Activar el Entorno Virtual (`venv`)

Abre tu terminal dentro de la carpeta del proyecto y ejecuta:

**En Windows:**

```bash
cd backend
python -m venv venv
.\venv\Scripts\activate
```

**En Mac / Linux:**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar Dependencias

Con el entorno virtual activo, instala las librerías necesarias:

```bash
pip install -r requirements.txt
```

#### 3.1 Instalar dependencias del sistema

- ffmpeg:

   ```bash
   # Ubuntu/Debian
   sudo apt install ffmpeg

   # macOS
   brew install ffmpeg
   ```

- yt-dlp:

   ```bash
   pip install yt-dlp
   ```

### 4. Configurar Credenciales de AWS

Ejecuta el asistente de configuración interactivo de AWS en tu terminal:

```bash
aws configure
```

Ingresa los datos solicitados uno a uno:

* **AWS Access Key ID:** `[Tu Access Key ID de IAM]`
* **AWS Secret Access Key:** `[Tu Secret Access Key de IAM]`
* **Default region name:** `us-east-1`
* **Default output format:** `json`

## 5. Ejecutar 🚀

### Modo API (Frontend + Backend)

```bash
cd backend
python app.py
```

Abre `http://localhost:8000` en tu navegador.

### Modo CLI (solo backend)

```bash
cd backend
python -m core.pipeline ../backend/data/audio.mp3
```

---

## 📡 API Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | Frontend web |
| `GET` | `/health` | Health check |
| `POST` | `/api/analyze` | Subir archivo audio/video |
| `POST` | `/api/analyze-youtube` | Analizar video de YouTube |
| `GET` | `/api/progress/{job_id}` | Progreso en tiempo real (SSE) |

---

## 👥 Authors
- Jaren Pazmino
- Adrian Villamar

   Miembros del Club de Inteligencia Artificial Politécnico (CIAP)

![Club CIAP](images/ciap.png)