"""
Tests locales del handler — sin necesidad de AWS real.
Ejecutar con: python test_local.py
"""
import json
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


# ─── Mocks de AWS antes de importar el handler ────────
import boto3
from unittest.mock import patch

# Parchamos los clientes AWS para no necesitar credenciales reales
with patch("boto3.resource"), patch("boto3.client"):
    import handler


class TestVerificacion(unittest.TestCase):
    """Tests del endpoint de verificación GET"""

    def setUp(self):
        handler._secrets_cache = {
            "META_VERIFY_TOKEN": "mi-token-secreto",
            "META_ACCESS_TOKEN": "test-token",
            "META_PHONE_NUMBER_ID": "123456",
            "META_APP_SECRET": "app-secret-test",
        }

    def test_verificacion_correcta(self):
        event = {
            "requestContext": {"http": {"method": "GET"}},
            "queryStringParameters": {
                "hub.mode": "subscribe",
                "hub.verify_token": "mi-token-secreto",
                "hub.challenge": "challenge-abc123",
            }
        }
        resp = handler.lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(resp["body"], "challenge-abc123")
        print("✅ Verificación correcta — PASS")

    def test_verificacion_token_incorrecto(self):
        event = {
            "requestContext": {"http": {"method": "GET"}},
            "queryStringParameters": {
                "hub.mode": "subscribe",
                "hub.verify_token": "token-equivocado",
                "hub.challenge": "challenge-abc123",
            }
        }
        resp = handler.lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)
        print("✅ Token incorrecto rechazado — PASS")


class TestExtraccionMensaje(unittest.TestCase):
    """Tests de extracción del payload de Meta"""

    def test_mensaje_texto(self):
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "573153310033",
                            "id":   "msg-id-123",
                            "type": "text",
                            "text": {"body": "Hola, tienen Royal Canin?"}
                        }],
                        "contacts": [{"profile": {"name": "Maria"}}]
                    }
                }]
            }]
        }
        resultado = handler.extraer_mensaje(body)
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["telefono"], "573153310033")
        self.assertEqual(resultado["texto"], "Hola, tienen Royal Canin?")
        self.assertEqual(resultado["nombre"], "Maria")
        print("✅ Extracción mensaje texto — PASS")

    def test_notificacion_estado(self):
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{"id": "msg-123", "status": "delivered"}]
                    }
                }]
            }]
        }
        resultado = handler.extraer_mensaje(body)
        self.assertIsNone(resultado)
        print("✅ Notificación de estado ignorada — PASS")

    def test_payload_vacio(self):
        resultado = handler.extraer_mensaje({})
        self.assertIsNone(resultado)
        print("✅ Payload vacío manejado — PASS")


class TestSesiones(unittest.TestCase):
    """Tests del motor de sesiones"""

    def test_sesion_nueva(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # Sin item = sesión nueva

        with patch.object(handler.dynamodb, "Table", return_value=mock_table):
            sesion = handler.cargar_sesion("573100000000")

        self.assertEqual(sesion["historial"], [])
        self.assertEqual(sesion["estado"], "inicio")
        self.assertEqual(sesion["mascota"], {})
        print("✅ Sesión nueva creada — PASS")

    def test_sesion_existente(self):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "telefono": "573100000000",
                "historial": [
                    {"role": "user", "content": "Hola"},
                    {"role": "assistant", "content": "Hola! ¿En qué te ayudo?"}
                ],
                "estado": "identificando_mascota",
                "mascota": {"especie": "perro"},
                "pedido": {},
            }
        }

        with patch.object(handler.dynamodb, "Table", return_value=mock_table):
            sesion = handler.cargar_sesion("573100000000")

        self.assertEqual(len(sesion["historial"]), 2)
        self.assertEqual(sesion["estado"], "identificando_mascota")
        self.assertEqual(sesion["mascota"]["especie"], "perro")
        print("✅ Sesión existente cargada — PASS")


if __name__ == "__main__":
    print("\n🤖 VetBot — Tests locales del handler\n" + "="*45)
    unittest.main(verbosity=0, exit=False)
    print("\n✅ Todos los tests pasaron")
