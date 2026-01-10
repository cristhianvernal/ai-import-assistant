# Guía de Despliegue en Render

Tienes dos formas de desplegar en Render. La **Opción 1 (Blueprint)** es la más automatizada.

## Opción 1: Usando Blueprint (Recomendado)

Esta opción usa el archivo `render.yaml` que acabo de crear para configurar todo automáticamente.

1.  Sube tus cambios a GitHub (incluyendo `Dockerfile` y `render.yaml`).
2.  Ve a [Render Dashboard](https://dashboard.render.com/).
3.  Haz clic en **New +** -> **Blueprint**.
4.  Conecta tu repositorio.
5.  Render detectará el archivo `render.yaml`.
6.  Te pedirá que ingreses los valores para `GOOGLE_API_KEY` y `DATABASE_URL`.
7.  Haz clic en **Apply**. ¡Listo!

## Opción 2: Web Service Manual

Si prefieres hacerlo manualmente:

1.  En Render, crea un **New +** -> **Web Service**.
2.  Conecta tu repo.
3.  Settings:
    *   **Runtime**: Docker
    *   **Region**: Oregon (u otra)
    *   **Branch**: main
4.  **Environment Variables**:
    *   Añade `GOOGLE_API_KEY` = `...`
    *   Añade `DATABASE_URL` = `...`
5.  Haz clic en **Create Web Service**.

## Notas sobre la Base de Datos
Asegúrate de que tu base de datos (actualmente configurada como `aws-0-us-west-2.pooler.supabase.com`) acepte conexiones desde cualquier IP (0.0.0.0/0) o desde las IPs de Render, ya que Render rota sus IPs. Supabase por defecto suele permitir conexiones si tienes la contraseña correcta.
