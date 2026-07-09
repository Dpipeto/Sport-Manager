"""
Política de contraseñas de SportManager.
Reglas:
  - Mínimo 8 caracteres
  - Al menos una letra mayúscula
  - Al menos un número
  - Al menos un carácter especial: . , # $ % & /
No se usan consultas raw con datos de usuario → SQLAlchemy ORM
previene inyección SQL por diseño.
"""
import re
import html

SPECIAL_CHARS = set('.,#$%&/')
MIN_LENGTH = 8

# Reglas para mostrar en el frontend
RULES = [
    ('length',   f'Mínimo {MIN_LENGTH} caracteres'),
    ('upper',    'Al menos una letra mayúscula (A-Z)'),
    ('digit',    'Al menos un número (0-9)'),
    ('special',  'Al menos un carácter especial: . , # $ % & /'),
]


def validate_password(password: str) -> list[str]:
    """
    Valida la contraseña contra la política.
    Retorna lista de errores (vacía = contraseña válida).
    """
    errors = []
    if not password or len(password) < MIN_LENGTH:
        errors.append(f'La contraseña debe tener al menos {MIN_LENGTH} caracteres.')
    if not re.search(r'[A-Z]', password):
        errors.append('Debe incluir al menos una letra mayúscula.')
    if not re.search(r'\d', password):
        errors.append('Debe incluir al menos un número.')
    if not any(c in SPECIAL_CHARS for c in password):
        errors.append('Debe incluir al menos un carácter especial: . , # $ % & /')
    return errors


def sanitize_input(value: str) -> str:
    """
    Limpia texto de usuario antes de usarlo en contextos no-ORM
    (mensajes flash, nombres, etc.).
    Escapa HTML para prevenir XSS.
    """
    if value is None:
        return ''
    return html.escape(str(value).strip())
