# LeadScout AI Backend

FastAPI backend para LeadScout AI. Descubre, puntua y gestiona leads locales con datos reales desde Google Places y Supabase.

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Instalacion

```bash
uv sync
```

## Configuracion

```bash
cp .env .env
# Edita .env con tus claves
```

## Correr el servidor

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Endpoints disponibles

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/health` | Estado del servicio |
| GET | `/api/leads` | Listar leads (con filtros) |
| GET | `/api/leads/{id}` | Obtener lead por ID |
| POST | `/api/leads` | Crear lead manualmente |
| PATCH | `/api/leads/{id}` | Actualizar lead |
| DELETE | `/api/leads/{id}` | Eliminar lead |
| POST | `/api/explorer/search` | Buscar negocios via Google Places |
| GET | `/api/reports/summary` | Resumen y KPIs |
| GET | `/api/settings/workspace` | Datos del workspace |
| GET | `/api/settings/team` | Equipo |
| GET | `/api/settings/usage` | Uso de la plataforma |

### Filtros para GET /api/leads

```
?q=restaurante&status=nuevo&priority=alta&category=Gastronomia&min_score=0&max_score=40
```

### Ejemplo POST /api/explorer/search

```json
{
  "query": "restaurantes",
  "location": "San Salvador, El Salvador",
  "latitude": 13.6929,
  "longitude": -89.2182,
  "radius_km": 2,
  "category": "Gastronomia"
}
```

## Documentacion interactiva

Disponible en: http://127.0.0.1:8000/docs

## Variables de entorno necesarias

| Variable | Descripcion | Requerida |
|----------|-------------|-----------|
| `SUPABASE_URL` | URL del proyecto Supabase | Para produccion |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (solo backend) | Para produccion |
| `GOOGLE_PLACES_API_KEY` | API key de Google Places | Para explorer real |
| `PAGESPEED_API_KEY` | API key de PageSpeed Insights | Para scoring completo |

Sin estas variables el backend funciona con datos mock/seed.

## Conectar Supabase

1. Crea un proyecto en [supabase.com](https://supabase.com)
2. Ejecuta `migrations/initial_schema.sql` en el SQL editor de Supabase
3. Agrega `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` a `.env`

## Conectar con el frontend

Agrega al `.env.local` del frontend:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Scoring de brecha digital

| Score | Nivel |
|-------|-------|
| 0-20 | Critico |
| 21-40 | Debil |
| 41-60 | Moderado |
| 61-100 | Bueno |
