"""
Panel del Super Administrador — Administración de la plataforma SaaS.
Sin acceso a datos internos de los clubes (deportistas, pagos, etc).
"""
import io
import csv
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import func, extract
from datetime import datetime
from models import (Club, RegistrationRequest, User, Role, ActivityLog,
                    log_activity, db)
from routes.decorators import superadmin_required
from routes.password_policy import validate_password, sanitize_input

platform_bp = Blueprint('platform', __name__, url_prefix='/platform')


# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD DE LA PLATAFORMA
# ═════════════════════════════════════════════════════════════════════════════

@platform_bp.route('/')
@platform_bp.route('/dashboard')
@login_required
@superadmin_required
def dashboard():
    # KPIs
    total_clubs      = Club.query.count()
    active_clubs     = Club.query.filter_by(status='activo').count()
    suspended_clubs  = Club.query.filter_by(status='suspendido').count()
    pending_requests = RegistrationRequest.query.filter_by(status='pendiente').count()
    total_users      = User.query.count()

    # Usuarios por rol
    users_by_role = {}
    for role in Role.query.all():
        count = len(role.users)
        if count:
            users_by_role[role.name] = count

    # Clubes registrados por mes (agregación en Python — compatible
    # con SQLite y PostgreSQL sin funciones específicas de dialecto)
    month_counts = {}
    for c in Club.query.all():
        if c.created_at:
            key = c.created_at.strftime('%Y-%m')
            month_counts[key] = month_counts.get(key, 0) + 1
    clubs_by_month = sorted(month_counts.items())[-12:]

    # Dueños nuevos por mes
    dueno_role = Role.query.filter_by(name='dueño').first()
    owners = dueno_role.users if dueno_role else []
    owners_by_month = {}
    for o in owners:
        if o.created_at:
            key = o.created_at.strftime('%Y-%m')
            owners_by_month[key] = owners_by_month.get(key, 0) + 1

    # Actividad reciente
    recent_activity = ActivityLog.query.order_by(
        ActivityLog.timestamp.desc()).limit(15).all()

    # Solicitudes recientes pendientes
    recent_requests = RegistrationRequest.query.filter_by(
        status='pendiente').order_by(RegistrationRequest.created_at.desc()).limit(5).all()

    return render_template('platform/dashboard.html',
        total_clubs=total_clubs, active_clubs=active_clubs,
        suspended_clubs=suspended_clubs, pending_requests=pending_requests,
        total_users=total_users, users_by_role=users_by_role,
        clubs_by_month=clubs_by_month, owners_by_month=owners_by_month,
        recent_activity=recent_activity, recent_requests=recent_requests)


# ═════════════════════════════════════════════════════════════════════════════
# CLUBES
# ═════════════════════════════════════════════════════════════════════════════

@platform_bp.route('/clubs')
@login_required
@superadmin_required
def clubs():
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    query = Club.query
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(Club.name.ilike(f'%{search}%'))
    all_clubs = query.order_by(Club.created_at.desc()).all()
    return render_template('platform/clubs.html', clubs=all_clubs,
                           status_filter=status, search=search)


@platform_bp.route('/clubs/<int:id>/toggle-status', methods=['POST'])
@login_required
@superadmin_required
def toggle_club_status(id):
    club = Club.query.get_or_404(id)
    club.status = 'suspendido' if club.status == 'activo' else 'activo'
    db.session.commit()
    log_activity(f'Club {"suspendido" if club.status == "suspendido" else "reactivado"}',
                 f'Club: {club.name}', user=current_user)
    flash(f'Club {club.name} ahora está {club.status}.',
          'warning' if club.status == 'suspendido' else 'success')
    return redirect(url_for('platform.clubs'))


@platform_bp.route('/clubs/<int:id>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_club(id):
    club = Club.query.get_or_404(id)
    name = club.name
    # Eliminar usuarios del club (sus roles primero)
    for u in club.users:
        u.roles.clear()
        db.session.delete(u)
    db.session.delete(club)
    db.session.commit()
    log_activity('Club eliminado', f'Club: {name}', user=current_user)
    flash(f'Club {name} y sus usuarios fueron eliminados.', 'warning')
    return redirect(url_for('platform.clubs'))


# ═════════════════════════════════════════════════════════════════════════════
# SOLICITUDES DE REGISTRO
# ═════════════════════════════════════════════════════════════════════════════

@platform_bp.route('/requests')
@login_required
@superadmin_required
def requests_list():
    status = request.args.get('status', 'pendiente')
    query = RegistrationRequest.query
    if status:
        query = query.filter_by(status=status)
    reqs = query.order_by(RegistrationRequest.created_at.desc()).all()
    return render_template('platform/requests.html', requests=reqs, status_filter=status)


@platform_bp.route('/requests/<int:id>', methods=['GET', 'POST'])
@login_required
@superadmin_required
def request_detail(id):
    req = RegistrationRequest.query.get_or_404(id)
    if request.method == 'POST':
        # Edición previa a aprobación
        req.owner_name  = sanitize_input(request.form.get('owner_name', ''))
        req.owner_email = sanitize_input(request.form.get('owner_email', ''))
        req.club_name   = sanitize_input(request.form.get('club_name', ''))
        req.city        = sanitize_input(request.form.get('city', ''))
        req.address     = sanitize_input(request.form.get('address', ''))
        req.phone       = sanitize_input(request.form.get('phone', ''))
        req.description = sanitize_input(request.form.get('description', ''))
        db.session.commit()
        flash('Solicitud actualizada.', 'success')
        return redirect(url_for('platform.request_detail', id=id))
    return render_template('platform/request_detail.html', req=req)


@platform_bp.route('/requests/<int:id>/approve', methods=['POST'])
@login_required
@superadmin_required
def approve_request(id):
    req = RegistrationRequest.query.get_or_404(id)
    if req.status != 'pendiente':
        flash('Esta solicitud ya fue procesada.', 'warning')
        return redirect(url_for('platform.requests_list'))

    if User.query.filter_by(email=req.owner_email).first():
        flash('Ya existe un usuario con ese correo. Edita la solicitud antes de aprobar.', 'danger')
        return redirect(url_for('platform.request_detail', id=id))

    # 1. Crear el club
    club = Club(
        name=req.club_name, city=req.city, address=req.address,
        phone=req.phone, description=req.description,
        logo=req.logo, status='activo',
    )
    db.session.add(club)
    db.session.flush()

    # 2. Crear el dueño
    dueno_role = Role.query.filter_by(name='dueño').first()
    owner = User(
        name=req.owner_name, email=req.owner_email,
        club_id=club.id, active=True,
        school_name=req.club_name,
    )
    owner.password_hash = req.password_hash   # ya viene hasheada del registro
    owner.roles.append(dueno_role)
    db.session.add(owner)

    # 3. Actualizar solicitud
    req.status = 'aprobada'
    req.reviewed_at = datetime.utcnow()
    db.session.commit()

    log_activity('Solicitud aprobada',
                 f'Club: {club.name} — Dueño: {owner.name}', user=current_user)
    flash(f'Club "{club.name}" creado. El dueño ya puede iniciar sesión.', 'success')
    return redirect(url_for('platform.requests_list'))


@platform_bp.route('/requests/<int:id>/reject', methods=['POST'])
@login_required
@superadmin_required
def reject_request(id):
    req = RegistrationRequest.query.get_or_404(id)
    if req.status != 'pendiente':
        flash('Esta solicitud ya fue procesada.', 'warning')
        return redirect(url_for('platform.requests_list'))
    req.status = 'rechazada'
    req.reviewed_at = datetime.utcnow()
    req.review_notes = sanitize_input(request.form.get('notes', ''))
    db.session.commit()
    log_activity('Solicitud rechazada', f'Club: {req.club_name}', user=current_user)
    flash('Solicitud rechazada.', 'warning')
    return redirect(url_for('platform.requests_list'))


# ═════════════════════════════════════════════════════════════════════════════
# DUEÑOS DE CLUB
# ═════════════════════════════════════════════════════════════════════════════

@platform_bp.route('/owners')
@login_required
@superadmin_required
def owners():
    dueno_role = Role.query.filter_by(name='dueño').first()
    owner_list = sorted(dueno_role.users, key=lambda u: u.name) if dueno_role else []
    return render_template('platform/owners.html', owners=owner_list)


@platform_bp.route('/owners/<int:id>/toggle-active', methods=['POST'])
@login_required
@superadmin_required
def toggle_owner(id):
    owner = User.query.get_or_404(id)
    if not owner.has_role('dueño'):
        flash('Este usuario no es dueño de club.', 'danger')
        return redirect(url_for('platform.owners'))
    owner.active = not owner.active
    db.session.commit()
    log_activity(f'Dueño {"activado" if owner.active else "desactivado"}',
                 f'{owner.name} ({owner.email})', user=current_user)
    flash(f'{owner.name} {"activado" if owner.active else "desactivado"}.', 'success')
    return redirect(url_for('platform.owners'))


@platform_bp.route('/owners/<int:id>/reset-password', methods=['POST'])
@login_required
@superadmin_required
def reset_owner_password(id):
    owner = User.query.get_or_404(id)
    if not owner.has_role('dueño'):
        flash('Este usuario no es dueño de club.', 'danger')
        return redirect(url_for('platform.owners'))
    new_password = request.form.get('new_password', '')
    errors = validate_password(new_password)
    if errors:
        for e in errors:
            flash(e, 'danger')
        return redirect(url_for('platform.owners'))
    owner.set_password(new_password)
    db.session.commit()
    log_activity('Contraseña restablecida', f'Dueño: {owner.name}', user=current_user)
    flash(f'Contraseña de {owner.name} restablecida.', 'success')
    return redirect(url_for('platform.owners'))


@platform_bp.route('/owners/<int:id>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_owner(id):
    owner = User.query.get_or_404(id)
    if not owner.has_role('dueño'):
        flash('Este usuario no es dueño de club.', 'danger')
        return redirect(url_for('platform.owners'))
    name = owner.name
    db.session.expire_all()
    owner.roles.clear()
    db.session.flush()
    db.session.delete(owner)
    db.session.commit()
    log_activity('Dueño eliminado', f'{name}', user=current_user)
    flash(f'Dueño {name} eliminado.', 'warning')
    return redirect(url_for('platform.owners'))


# ═════════════════════════════════════════════════════════════════════════════
# USUARIOS (vista global de solo lectura)
# ═════════════════════════════════════════════════════════════════════════════

@platform_bp.route('/users')
@login_required
@superadmin_required
def users_overview():
    """Vista global: solo nombre, rol, club y estado. Sin datos internos."""
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('platform/users.html', users=all_users)


# ═════════════════════════════════════════════════════════════════════════════
# LOGS DEL SISTEMA
# ═════════════════════════════════════════════════════════════════════════════

@platform_bp.route('/logs')
@login_required
@superadmin_required
def logs():
    page = request.args.get('page', 1, type=int)
    pagination = ActivityLog.query.order_by(
        ActivityLog.timestamp.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template('platform/logs.html', pagination=pagination)


# ═════════════════════════════════════════════════════════════════════════════
# EXPORTAR / REPORTES
# ═════════════════════════════════════════════════════════════════════════════

@platform_bp.route('/export/clubs')
@login_required
@superadmin_required
def export_clubs():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Club', 'Ciudad', 'Estado', 'Usuarios', 'Deportistas', 'Creado'])
    for c in Club.query.all():
        writer.writerow([c.id, c.name, c.city or '', c.status,
                         c.member_count, c.athlete_count,
                         c.created_at.strftime('%Y-%m-%d') if c.created_at else ''])
    mem = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    return send_file(mem, mimetype='text/csv', download_name='clubes.csv',
                     as_attachment=True)


@platform_bp.route('/export/users')
@login_required
@superadmin_required
def export_users():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Nombre', 'Email', 'Roles', 'Club', 'Activo', 'Último acceso'])
    for u in User.query.all():
        writer.writerow([u.id, u.name, u.email, u.roles_display,
                         u.club.name if u.club else '—',
                         'Sí' if u.active else 'No',
                         u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else 'Nunca'])
    mem = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    return send_file(mem, mimetype='text/csv', download_name='usuarios.csv',
                     as_attachment=True)


# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN / PLANES (preparado para futuro)
# ═════════════════════════════════════════════════════════════════════════════

@platform_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@superadmin_required
def settings():
    import secrets as _secrets
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_ntfy':
            current_user.ntfy_topic = request.form.get('ntfy_topic', '').strip() or None
            db.session.commit()
            flash('Tema de notificaciones guardado.', 'success')
        elif action == 'generate_ntfy':
            current_user.ntfy_topic = f'sportmanager-admin-{_secrets.token_urlsafe(8).lower()}'
            db.session.commit()
            flash('Tema generado. Suscríbete desde la app ntfy en tu celular.', 'success')
        elif action == 'test_ntfy' and current_user.ntfy_topic:
            from routes.notifications import send_push
            send_push(current_user.ntfy_topic, 'Prueba de notificación',
                      'Si ves esto en tu celular, las notificaciones funcionan ✔',
                      tags='white_check_mark')
            flash('Notificación de prueba enviada. Revisa tu celular.', 'info')
        return redirect(url_for('platform.settings'))
    return render_template('platform/settings.html')
