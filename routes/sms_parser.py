"""
Parser de SMS bancarios colombianos: Nequi, Bancolombia, Davivienda.

Extrae (banco, monto, remitente) del texto crudo del SMS.
Los formatos reales varían, por eso los patrones son flexibles:
buscan la palabra clave del banco + un monto en formato colombiano.

Ejemplos que reconoce:
  Nequi:       "Recibiste un pago de $50.000 de JUAN PEREZ en tu Nequi..."
  Bancolombia: "Bancolombia: Recibiste una transferencia por $150,000 de MARIA LOPEZ..."
  Davivienda:  "Davivienda le informa: recibio transferencia por $200.000 de PEDRO..."
"""
import re


def _parse_amount(text):
    """
    Extrae el primer monto tipo $50.000 / $1,250,000 / $50000.
    En Colombia el punto y la coma son separadores de miles.
    """
    m = re.search(r'\$\s*([\d.,]+)', text)
    if not m:
        return None
    raw = m.group(1)
    # Quitar separadores de miles (puntos y comas). Los SMS bancarios
    # colombianos no usan decimales, así que es seguro.
    cleaned = raw.replace('.', '').replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_sender(text):
    """Extrae el nombre después de 'de ' (mayúsculas típicas de los SMS)."""
    patterns = [
        r'(?:de|De|DE)\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s]{2,60}?)(?:\s+(?:en|a|por|el|la|tu|su)\b|[.,]|$)',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            name = m.group(1).strip()
            # Filtrar falsos positivos comunes
            if name.lower() not in ('tu', 'su', 'la', 'el') and len(name) > 2:
                return name[:150]
    return None


def parse_bank_sms(text):
    """
    Analiza el SMS y retorna dict {bank, amount, sender} o None si
    no parece un ingreso de dinero.
    """
    if not text:
        return None
    lower = text.lower()

    # Detectar banco
    if 'nequi' in lower:
        bank = 'nequi'
    elif 'bancolombia' in lower:
        bank = 'bancolombia'
    elif 'davivienda' in lower:
        bank = 'davivienda'
    else:
        bank = 'otro'

    # Solo ingresos: palabras que indican dinero ENTRANTE
    income_keywords = ('recibiste', 'recibió', 'recibio', 'te envió', 'te envio',
                       'consignación', 'consignacion', 'transferencia recibida',
                       'abono', 'recibió transferencia', 'recibio transferencia',
                       'pago recibido', 'recibiste un pago', 'te llegó', 'te llego')
    if not any(k in lower for k in income_keywords):
        return None

    amount = _parse_amount(text)
    if not amount or amount <= 0:
        return None

    return {
        'bank': bank,
        'amount': amount,
        'sender': _parse_sender(text),
    }
