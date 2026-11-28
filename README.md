# Planificador Académico

Aplicación de planificación académica con React, FastAPI y LangGraph. La interfaz se comunica con FastAPI. El backend integra Supabase Auth, PostgreSQL, Storage y Groq.

## Requisitos previos

- Python 3.10+
- Node.js 20.19+ (rama 20) o 22.12+ y npm

## 1. Variables de entorno

Copia los archivos de ejemplo sin modificar los originales:

- **Backend**: copia `backend/.env.example` a `backend/.env`
- **Frontend**: copia `frontend/.env.example` a `frontend/.env`

Valores esperados para ejecución local:

- `backend/.env`: `FRONTEND_ORIGIN=http://localhost:5173`
- `frontend/.env`: `VITE_API_BASE_URL=http://localhost:8000/api/v1`

Para usar cursos y sílabos, completa `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` y `GROQ_API_KEY` en `backend/.env`. Habilita el inicio de sesión por correo y contraseña en Supabase Auth y crea allí las dos cuentas de prueba. Usa una base de desarrollo para aplicar las migraciones.

## 2. Ejecutar el Backend (FastAPI)

Para preparar una base de desarrollo, coloca los archivos SQL que se entregan por separado en `backend/supabase/migrations/` y ejecuta `python -m scripts.apply_migrations` desde `backend/` con el entorno virtual activo. Puedes arrancar FastAPI y comprobar el endpoint de salud antes de recibir los SQL.

Desde la carpeta `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

El endpoint de salud quedará disponible en:

- `GET http://localhost:8000/api/v1/health` → `{"status": "ok"}`

## 3. Ejecutar el Worker Durable (PostgreSQL)

La extracción de sílabos y la planificación de estudio se encolan en PostgreSQL y se procesan en un proceso separado (sin `BackgroundTasks` en FastAPI). En otra terminal, desde la carpeta `backend/` con el entorno virtual activado:

```powershell
python -m app.worker
```

Parámetros opcionales en `backend/.env`:

- `WORKER_JOB_TIMEOUT_SECONDS=120` (tiempo máximo acotado por ejecución)
- `WORKER_LEASE_SECONDS=180` (lease en PostgreSQL; debe ser mayor que `WORKER_JOB_TIMEOUT_SECONDS`)
- `WORKER_POLL_INTERVAL_SECONDS=1.0`
- `WORKER_MAX_ATTEMPTS=3`

El worker reclama ejecuciones con `UPDATE ... FOR UPDATE SKIP LOCKED`, recupera ejecuciones con lease expirado sin duplicar resultados, registra etapa y tiempos (`stage`, `stage_timings`) y sanea errores de proveedores antes de exponerlos al usuario. El acceso directo de `anon`/`authenticated` a tablas de aplicación y a Storage queda deshabilitado; solo el backend accede mediante `DATABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`.

## 4. Ejecutar el Frontend (React + Vite)

En otra terminal, desde la carpeta `frontend/`:

```powershell
npm ci
npm run dev
```

Abre `http://localhost:5173`. El sílabo ficticio y el guion de demostración se entregan por separado con la carpeta `docs/`.

En **Sílabo y revisión**, primero pulsa **Subir sílabo PDF**. Cuando aparezca el documento guardado, pulsa **Extraer con IA**. Puedes recargar durante la carga o el análisis y volver al mismo curso. Si se interrumpió la transferencia, espera a que venza la reserva de cinco minutos y vuelve a seleccionar el archivo. Si el PDF ya está guardado y falla el análisis, usa **Reintentar análisis** sobre el documento existente.

## Verificación local

- Para el ensayo, usa cuentas de prueba de tu proyecto de Supabase. Si guardas sus credenciales en `backend/.env.test.local`, el archivo queda excluido. La API y el worker cargan su configuración desde `backend/.env`.
- Backend, desde `backend/`: `python -m unittest discover -s tests -v`.
- Frontend, desde `frontend/`: `npm run build`.
- Contratos HTTP: `http://localhost:8000/docs`.
