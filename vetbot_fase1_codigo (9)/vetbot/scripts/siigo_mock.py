"""
VetBot — Siigo Mock API
Simula exactamente la respuesta de GET /v1/products de Siigo Cloud API.
Cuando lleguen las credenciales reales, solo cambias el cliente en handler.py.

MODO DE USO:
    Como módulo en handler.py (modo mock):
        from siigo_mock import SiigoClient
        siigo = SiigoClient(mock=True)
        producto = siigo.get_product("RC-MAXI-15")

    Como módulo en handler.py (modo real — producción):
        from siigo_mock import SiigoClient
        siigo = SiigoClient(mock=False, partner_id="...", client_secret="...")
        producto = siigo.get_product("RC-MAXI-15")

    Test desde consola:
        python siigo_mock.py --codigo RC-MAXI-15
        python siigo_mock.py --todos
"""

import json, argparse, time, urllib.request, urllib.parse
from typing import Optional

# ─── CATÁLOGO MOCK — IDÉNTICO AL EXCEL ────────────────
# Simula exactamente lo que devolvería GET /v1/products de Siigo
MOCK_INVENTARIO = {
    "RC-MAXI-15":    {"price": 189000, "stock": 45,  "active": True,  "name": "Royal Canin Maxi Adult 15kg"},
    "RC-MAXI-LIGHT": {"price": 195000, "stock": 32,  "active": True,  "name": "Royal Canin Maxi Light 15kg"},
    "RC-MINI-2":     {"price": 38000,  "stock": 60,  "active": True,  "name": "Royal Canin Mini Adult 2kg"},
    "RC-PUPPY-4":    {"price": 72000,  "stock": 48,  "active": True,  "name": "Royal Canin Puppy 4kg"},
    "HILLS-AD-15":   {"price": 215000, "stock": 20,  "active": True,  "name": "Hills Science Diet Adult 15kg"},
    "ACANA-AC-11":   {"price": 285000, "stock": 15,  "active": True,  "name": "Acana Classics 11.4kg"},
    "RC-CAT-4":      {"price": 68000,  "stock": 40,  "active": True,  "name": "Royal Canin Feline Health 4kg"},
    "RC-KITTEN-2":   {"price": 42000,  "stock": 35,  "active": True,  "name": "Royal Canin Kitten 2kg"},
    "AGILITY-CAT-3": {"price": 32000,  "stock": 55,  "active": True,  "name": "Agility Gold Gatos 3kg"},
    "DENTASTIX-L":   {"price": 28000,  "stock": 80,  "active": True,  "name": "DentaStix Large x28"},
    "DENTASTIX-M":   {"price": 24000,  "stock": 75,  "active": True,  "name": "DentaStix Medium x28"},
    "WHISKAS-SNACK": {"price": 12000,  "stock": 100, "active": True,  "name": "Whiskas Temptations 85g"},
    "FRONT-L":       {"price": 38000,  "stock": 50,  "active": True,  "name": "Frontline Spot-On Perros L"},
    "FRONT-M":       {"price": 34000,  "stock": 45,  "active": True,  "name": "Frontline Spot-On Perros M"},
    "FRONT-CAT":     {"price": 32000,  "stock": 40,  "active": True,  "name": "Frontline Spot-On Gatos"},
    "SHAMP-DOG-250": {"price": 28000,  "stock": 30,  "active": True,  "name": "Shampoo Virbac 250ml"},
    "CATSAN-10":     {"price": 45000,  "stock": 25,  "active": True,  "name": "Arena Catsan Ultra 10L"},
    "CORREA-M":      {"price": 22000,  "stock": 20,  "active": True,  "name": "Correa Ajustable Nylon M"},
    "CAMA-DOG-M":    {"price": 85000,  "stock": 10,  "active": True,  "name": "Cama Acolchada Perros M"},
    "JUGUETE-KONG":  {"price": 55000,  "stock": 18,  "active": True,  "name": "Kong Classic Talla M"},
    # Producto agotado — para probar el flujo de "no disponible"
    "PROD-AGOTADO":  {"price": 99000,  "stock": 0,   "active": True,  "name": "Producto de Prueba Agotado"},
}


class SiigoClient:
    """
    Cliente para la API de Siigo Cloud.
    Funciona en modo mock (sin credenciales) o real (con credenciales del cliente).

    La interfaz es IDÉNTICA en ambos modos — solo cambia el constructor.
    El resto del código del bot no necesita saber si está en mock o real.
    """

    def __init__(self, mock: bool = True,
                 partner_id: str = None,
                 client_secret: str = None,
                 access_token: str = None):
        self.mock         = mock
        self.partner_id   = partner_id
        self.client_secret= client_secret
        self._access_token= access_token
        self._token_expiry= 0

        if not mock and not (partner_id and client_secret):
            raise ValueError("En modo real necesitas partner_id y client_secret")

    # ── AUTENTICACIÓN OAUTH2 ──────────────────────────
    def _get_token(self) -> str:
        """Obtiene o refresca el token OAuth2 de Siigo."""
        if self.mock:
            return "mock-token-pamascotas-2025"

        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        # POST /v1/auth/token
        url  = "https://api.siigo.com/auth/token"
        body = json.dumps({
            "grant_type":    "client_credentials",
            "client_id":     self.partner_id,
            "client_secret": self.client_secret,
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            self._access_token = data["access_token"]
            self._token_expiry  = time.time() + data.get("expires_in", 3600) - 60
            return self._access_token

    # ── GET PRODUCTO ──────────────────────────────────
    def get_product(self, codigo: str) -> Optional[dict]:
        """
        Obtiene stock y precio de un producto por su código Siigo.

        Returns:
            {
                "code":               "RC-MAXI-15",
                "name":               "Royal Canin Maxi Adult 15kg",
                "available_quantity": 45,
                "price":              189000,
                "active":             True,
                "stock_control":      True,
            }
            o None si el producto no existe.
        """
        if self.mock:
            return self._mock_get_product(codigo)
        return self._real_get_product(codigo)

    def _mock_get_product(self, codigo: str) -> Optional[dict]:
        """Respuesta simulada — idéntica al formato real de Siigo."""
        data = MOCK_INVENTARIO.get(codigo)
        if not data:
            return None
        return {
            "code":               codigo,
            "name":               data["name"],
            "available_quantity": data["stock"],
            "price":              data["price"],
            "active":             data["active"],
            "stock_control":      True,
            "price_list":         [{"position": 1, "value": data["price"]}],
            "_mock":              True,  # Flag para saber que es mock
        }

    def _real_get_product(self, codigo: str) -> Optional[dict]:
        """Llamada real a la API de Siigo Cloud."""
        token = self._get_token()
        url   = f"https://api.siigo.com/v1/products?code={urllib.parse.quote(codigo)}"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Partner-Id":    self.partner_id,
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                results = data.get("results", [])
                if not results:
                    return None
                p = results[0]
                return {
                    "code":               p.get("code", codigo),
                    "name":               p.get("name", ""),
                    "available_quantity": p.get("available_quantity", 0),
                    "price":              p.get("price_list", [{}])[0].get("value", 0),
                    "active":             p.get("active", False),
                    "stock_control":      p.get("stock_control", False),
                    "price_list":         p.get("price_list", []),
                    "_mock":              False,
                }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def is_available(self, codigo: str) -> tuple[bool, int, int]:
        """
        Verifica disponibilidad de un producto.

        Returns:
            (disponible: bool, precio: int, stock: int)
        """
        producto = self.get_product(codigo)
        if not producto:
            return False, 0, 0
        if not producto.get("active"):
            return False, 0, 0
        if not producto.get("stock_control"):
            # Sin control de stock → asumir disponible
            return True, producto.get("price", 0), 999
        stock = producto.get("available_quantity", 0)
        precio= producto.get("price", 0)
        return stock > 0, precio, stock


# ── INTEGRACIÓN CON HANDLER.PY ────────────────────────
def get_siigo_client_from_secrets(secrets: dict) -> SiigoClient:
    """
    Factory que crea el cliente correcto según los secrets.
    Si los secrets tienen PENDIENTE, usa mock automáticamente.
    Usar en handler.py así:

        from siigo_mock import get_siigo_client_from_secrets
        siigo = get_siigo_client_from_secrets(get_secrets())
        disponible, precio, stock = siigo.is_available(codigo)
    """
    partner_id    = secrets.get("SIIGO_PARTNER_ID", "PENDIENTE")
    client_secret = secrets.get("SIIGO_CLIENT_SECRET", "PENDIENTE")
    access_token  = secrets.get("SIIGO_ACCESS_TOKEN", "")

    if "PENDIENTE" in (partner_id, client_secret):
        print("[SIIGO] Usando modo MOCK — credenciales no configuradas")
        return SiigoClient(mock=True)

    return SiigoClient(
        mock=False,
        partner_id=partner_id,
        client_secret=client_secret,
        access_token=access_token or None,
    )


# ── TEST DESDE CONSOLA ─────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Siigo Mock API")
    parser.add_argument("--codigo", type=str, help="Código del producto a consultar")
    parser.add_argument("--todos",  action="store_true", help="Mostrar todos los productos mock")
    args = parser.parse_args()

    siigo = SiigoClient(mock=True)
    print(f"\n🏪 Siigo Mock API — Pa'Mascotas\n{'─'*50}")

    if args.todos:
        print(f"{'Código':<18} {'Stock':>6} {'Precio':>10}  {'Nombre'}")
        print("─" * 70)
        for codigo, data in MOCK_INVENTARIO.items():
            estado = "✅" if data["stock"] > 0 else "❌"
            print(f"{codigo:<18} {data['stock']:>5}u  ${data['price']:>9,}  {estado} {data['name']}")

    elif args.codigo:
        p = siigo.get_product(args.codigo)
        if p:
            disponible, precio, stock = siigo.is_available(args.codigo)
            print(f"Código:      {p['code']}")
            print(f"Nombre:      {p['name']}")
            print(f"Stock:       {p['available_quantity']} unidades")
            print(f"Precio:      ${p['price']:,} COP")
            print(f"Disponible:  {'✅ Sí' if disponible else '❌ No'}")
            print(f"Modo:        {'MOCK 🟡' if p['_mock'] else 'REAL 🟢'}")
        else:
            print(f"❌ Producto no encontrado: {args.codigo}")
    else:
        parser.print_help()
