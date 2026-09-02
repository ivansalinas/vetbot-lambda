# VetBot Panel Admin - Setup Local

## Estructura del Proyecto

\\\
/src                    <= Lambda codigo PRODUCTION (NO TOCAR)
/build, /deploy, /layer <= Lambda deployment
/scripts                <= Scripts utiles
/backend                <= Backend Node.js (TU LO HACES - LUNES)
/frontend               <= Frontend React (TU LO HACES - LUNES)
/docs                   <= Documentacion
/aws-secrets            <= Credenciales AWS (PRIVADO - NO commitir)
\\\

## Setup Backend (LUNES)

\\\ash
cd backend
npm install
npm start
# Corre en localhost:3001
\\\

## Setup Frontend (LUNES)

\\\ash
cd frontend
npm install
npm run dev
# Corre en localhost:5173
\\\

## Variables de Entorno

Crear \.env\ en cada carpeta (backend, frontend).
NO commitir .env (ver .gitignore).

## Credenciales AWS

- Almacenadas en \ws-secrets/secret.json\
- PROTEGIDAS: No se committen a Git
- Ver .gitignore en /aws-secrets

## Lambda (handler.py)

NO MODIFICAR durante desarrollo.
Cambios via Secrets Manager (Panel Admin).

## Git Setup (DOMINGO)

\\\ash
git init
git remote add origin https://github.com/tuuser/vetbot-backend.git
git add .
git commit -m "Init: VetBot backend"
git push -u origin main
\\\

## Timeline

- Hoy (Viernes):       PC limpio
- Fin de semana:       Git setup
- Lunes 2 SEP 9 AM:    EMPEZAR CÓDIGO
- Semana 1 (2-6 SEP):  Backend + Frontend base
- Semana 2 (9-13 SEP): Fase 1 completa + GO-LIVE
- Semana 3-4:          Fase 2 (secciones avanzadas)

## Documentacion

Ver /docs para especificaciones completas:
- 00_RESUMEN_EJECUTIVO_INICIO.md
- 01_ARQUITECTURA_BACKEND_MODULAR.md
- 02_INVENTARIO_Y_LIMPIEZA_PC.md
- 03_DOCUMENTO_MAESTRA_EJECUCION.md
- 04_ACLARACIONES_CRITICAS_PRE_INICIO.md

