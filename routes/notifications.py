"""
Notificaciones push al celular vía ntfy.sh (gratuito, sin registro).

Cómo funciona para el usuario:
  1. Instala la app "ntfy" (Play Store / App Store)
  2. Se suscribe a su tema privado (ej: sportmanager-club-x7k2m9)
  3. El sistema hace POST a https://ntfy.sh/<tema> y la notificación
     llega al celular al instante.

El tema funciona como una "clave": quien lo conozca puede suscribirse,
por eso se generan con sufijos aleatorios.
"""
import threading

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

NTFY_SERVER = 'https://ntfy.sh'


def _post(topic, title, message, tags='bell', priority='default', click_url=None):
    if not _HAS_REQUESTS or not topic:
        return
    try:
        headers = {
            'Title': title.encode('utf-8'),
            'Tags': tags,
            'Priority': priority,
        }
        if click_url:
            headers['Click'] = click_url
        requests.post(f'{NTFY_SERVER}/{topic}',
                      data=message.encode('utf-8'),
                      headers=headers, timeout=5)
    except Exception:
        pass   # las notificaciones nunca deben romper la app


def send_push(topic, title, message, tags='bell', priority='default', click_url=None):
    """Envía la notificación en un hilo aparte para no bloquear la respuesta."""
    if not topic:
        return
    threading.Thread(
        target=_post,
        args=(topic, title, message, tags, priority, click_url),
        daemon=True,
    ).start()


# ── Notificaciones específicas del sistema ───────────────────────────────────

def notify_new_registration_request(club_name, owner_name):
    """Notifica a todos los superadmins que llegó una solicitud nueva."""
    from models import User
    superadmins = [u for u in User.query.all()
                   if u.has_permission('platform.manage') and u.ntfy_topic]
    for sa in superadmins:
        send_push(
            sa.ntfy_topic,
            'Nueva solicitud de club',
            f'{owner_name} quiere registrar el club "{club_name}". '
            f'Entra al panel para revisarla.',
            tags='inbox_tray', priority='high',
        )


def notify_bank_transaction(club, tx):
    """Notifica al club que llegó un pago detectado por SMS."""
    if not club or not club.ntfy_topic:
        return
    bank_names = {'nequi': 'Nequi', 'bancolombia': 'Bancolombia',
                  'davivienda': 'Davivienda'}
    send_push(
        club.ntfy_topic,
        f'Pago recibido — {bank_names.get(tx.bank, tx.bank or "Banco")}',
        f'${tx.amount:,.0f}' + (f' de {tx.sender}' if tx.sender else '') +
        '. Confírmalo en Transacciones Bancarias.',
        tags='moneybag', priority='high',
    )
