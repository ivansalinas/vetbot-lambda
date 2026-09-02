# VetBot — Pa'Mascotas Medellín
**Automatiza Digital · Ivan Salinas · 2025**

---

## Estructura del proyecto
```
vetbot/
├── src/
│   ├── handler.py          # Lambda handler principal (WhatsApp + Bedrock + DynamoDB)
│   └── test_local.py       # Tests sin necesitar AWS real
├── deploy/
│   ├── setup_infra.py      # Crea todos los recursos AWS (DynamoDB, S3, IAM, Secrets)
│   ├── deploy_lambda.py    # Empaqueta y despliega Lambda + API Gateway
│   └── vetbot_lambda.zip   # ZIP generado automáticamente por deploy_lambda.py
├── requirements.txt
└── README.md
```

---

## ORDEN DE EJECUCIÓN — FASE 1

### PRE-REQUISITO: Verificar perfil CLI
```powershell
aws sts get-caller-identity --profile vetbot-pamascotas
# Debe mostrar Account: 330631894163
```

---

### PASO 1 — Crear infraestructura AWS
```powershell
cd vetbot/deploy
python setup_infra.py --profile vetbot-pamascotas
```

**Qué crea:**
- ✅ DynamoDB: `vetbot-sesiones` (TTL 30min), `vetbot-clientes`, `vetbot-pedidos`
- ✅ S3: `vetbot-pamascotas-fotos-330631894163`, `vetbot-pamascotas-logs-330631894163`
- ✅ IAM Role: `vetbot-lambda-role` con permisos Lambda + DynamoDB + Bedrock + S3
- ✅ Secrets Manager: `vetbot/pamascotas/credentials` (con placeholders)
- ✅ CloudWatch: `/aws/lambda/vetbot-handler` (30 días retención)

**Tiempo estimado:** 2-3 minutos

---

### PASO 2 — Desplegar Lambda + API Gateway
```powershell
cd vetbot/deploy
python deploy_lambda.py --profile vetbot-pamascotas
```

**Qué crea:**
- ✅ ZIP del `handler.py`
- ✅ Lambda `vetbot-handler` (Python 3.12, 512MB, timeout 29s)
- ✅ API Gateway HTTP con rutas GET y POST en `/webhook`
- ✅ Stage `prod` con auto-deploy

**Al final te muestra:**
```
🔗 URL del webhook: https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod/webhook
🔑 Verify Token: vetbot-pamascotas-2025
```

**Tiempo estimado:** 1-2 minutos

---

### PASO 3 — Configurar webhook en Meta (Sandbox)
1. Ir a https://developers.facebook.com
2. Tu App → WhatsApp → Configuración → Webhooks
3. **Webhook URL:** la URL del paso anterior
4. **Verify Token:** `vetbot-pamascotas-2025`
5. Clic en "Verificar y guardar"
6. Suscribir a eventos: `messages`, `message_deliveries`, `message_reads`

---

### PASO 4 — Actualizar credenciales cuando el cliente las entregue
```powershell
aws secretsmanager update-secret `
  --secret-id vetbot/pamascotas/credentials `
  --secret-string '{\"META_ACCESS_TOKEN\":\"TU_TOKEN\",\"META_PHONE_NUMBER_ID\":\"TU_PHONE_ID\",\"META_APP_SECRET\":\"TU_SECRET\",\"META_VERIFY_TOKEN\":\"vetbot-pamascotas-2025\",\"SIIGO_PARTNER_ID\":\"TU_PARTNER_ID\",\"SIIGO_CLIENT_SECRET\":\"TU_CLIENT_SECRET\",\"SIIGO_ACCESS_TOKEN\":\"\"}' `
  --profile vetbot-pamascotas
```

---

### ACTUALIZAR CÓDIGO (cuando hagas cambios al handler)
```powershell
cd vetbot/deploy
python deploy_lambda.py --profile vetbot-pamascotas --update-only
```

---

## TESTS LOCALES (sin necesitar AWS)
```powershell
cd vetbot/src
python test_local.py
# Debe mostrar 7 tests en verde
```

---

## VARIABLES DE ENTORNO de la Lambda
| Variable | Valor |
|---|---|
| TABLE_SESIONES | vetbot-sesiones |
| TABLE_CLIENTES | vetbot-clientes |
| TABLE_PEDIDOS | vetbot-pedidos |
| SECRET_NAME | vetbot/pamascotas/credentials |
| REGION | us-east-1 |

---

## CREDENCIALES PENDIENTES del cliente
| Credencial | Dónde obtenerla |
|---|---|
| META_ACCESS_TOKEN | Meta Developers → Tu App → WhatsApp → API Setup |
| META_PHONE_NUMBER_ID | Meta Developers → Tu App → WhatsApp → API Setup |
| META_APP_SECRET | Meta Developers → Tu App → Configuración básica |
| SIIGO_PARTNER_ID | Consola Siigo Nube → Configuración → Integraciones → API |
| SIIGO_CLIENT_SECRET | Consola Siigo Nube → Configuración → Integraciones → API |

---

## ARQUITECTURA
```
Cliente WhatsApp
      ↓ POST /webhook
API Gateway (HTTP API)
      ↓ AWS_PROXY
Lambda vetbot-handler (Python 3.12)
      ├── DynamoDB vetbot-sesiones  (contexto conversación, TTL 30min)
      ├── DynamoDB vetbot-clientes  (CRM)
      ├── Secrets Manager           (credenciales Meta + Siigo)
      ├── Bedrock Claude Haiku 3    (generación respuesta)
      └── Meta WhatsApp API         (envío respuesta al cliente)
```

---

## CUENTA AWS
- **Management:** Automatiza (920372991650) — ivan.salinas@automatiza.digital
- **Sub-cuenta:** vetbot-pamascotas (330631894163) — automatizadigital.pamascotas@gmail.com
- **CLI Profile:** `vetbot-pamascotas`
- **Región:** us-east-1
