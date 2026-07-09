"""
RBAC — Control de acceso basado en permisos.

En lugar de verificar nombres de rol, cada ruta declara el PERMISO que
requiere. Los roles son solo agrupaciones de permisos (ver models.py:
PERMISSION_DEFS y ROLE_PERMISSION_MAP), lo que permite agregar roles
nuevos (fisioterapeuta, nutricionista...) sin tocar las rutas.

Uso:
    @permission_required('athletes.view')
    def index(): ...

Además provee helpers de scoping multi-tenant:
    current_club_id() → club del usuario actual (None para superadmin)
"""
from functools import wraps
from flask import redirect, url_for, flash, abort
from flask_login import current_user


def permission_required(*codes):
    """Permite el acceso si el usuario tiene AL MENOS UNO de los permisos."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not any(current_user.has_permission(c) for c in codes):
                flash('No tienes permiso para acceder a esta sección.', 'danger')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def superadmin_required(f):
    """Solo el Super Administrador de la plataforma."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.has_permission('platform.manage'):
            flash('Solo el Super Administrador puede acceder aquí.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


def club_required(f):
    """Requiere pertenecer a un club activo. Bloquea al superadmin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.has_permission('platform.manage'):
            flash('El Super Administrador no tiene acceso a los datos internos de los clubes.', 'warning')
            return redirect(url_for('platform.dashboard'))
        if not current_user.club_id:
            flash('Tu cuenta no está asociada a ningún club.', 'danger')
            return redirect(url_for('auth.logout'))
        # Club suspendido → bloquear
        from models import Club
        club = Club.query.get(current_user.club_id)
        if club and club.status == 'suspendido':
            flash('Tu club está suspendido. Contacta al administrador de la plataforma.', 'danger')
            return redirect(url_for('auth.logout'))
        return f(*args, **kwargs)
    return decorated


def current_club_id():
    """Club del usuario actual (None si es superadmin)."""
    if current_user.is_authenticated and current_user.club_id:
        return current_user.club_id
    return None


def scoped_or_404(model, id):
    """
    Obtiene un registro verificando que pertenezca al club del usuario.
    Evita que un club acceda a datos de otro (IDOR protection).
    """
    obj = model.query.get_or_404(id)
    club_id = current_club_id()
    obj_club = getattr(obj, 'club_id', None)
    if obj_club is not None and club_id is not None and obj_club != club_id:
        abort(404)
    return obj


def athlete_scoped_or_404(model, id):
    """Igual que scoped_or_404 pero para modelos que cuelgan de Athlete."""
    obj = model.query.get_or_404(id)
    club_id = current_club_id()
    if obj.athlete and obj.athlete.club_id and club_id and obj.athlete.club_id != club_id:
        abort(404)
    return obj


# ── Aliases de compatibilidad (código legado) ────────────────────────────────

def admin_only(f):
    return superadmin_required(f)

def dueno_only(f):
    return permission_required('club.users')(f)

def club_staff(f):
    return permission_required('assessments.manage')(f)

def billing_access(f):
    return permission_required('billing.view')(f)

def club_member(f):
    return permission_required('athletes.view')(f)

def role_required(*roles):
    """Legacy: mapea nombres de rol a chequeo de rol directo."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not current_user.has_role(*roles):
                flash('No tienes permiso para acceder aquí.', 'danger')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def admin_or_dueno(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not (current_user.has_permission('platform.manage') or
                current_user.has_permission('club.users')):
            flash('No tienes permiso.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated

def not_recepcion(f):
    return permission_required('athletes.manage')(f)
