"""
Gestión de usuarios DEL CLUB (dueño) y configuración del club.
El superadmin gestiona dueños desde /platform, no desde aquí.
"""
import os, uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from models import User, Role, Venue, Group, log_activity
from app import db
from routes.decorators import (permission_required, club_required,
                               current_club_id, scoped_or_404)
from routes.password_policy import validate_password, sanitize_input

users_bp = Blueprint('users', __name__)
config_bp = Blueprint('config', __name__)

# Roles que un dueño puede asignar dentro de su club
CLUB_ROLES = ['entrenador', 'recepcion']


def _save_user_photo(file, user):
    """Guarda la foto de perfil. Retorna URL/filename o None."""
    if not file or not file.filename:
        return None
    from routes.storage import save_file, delete_file
    saved = save_file(file, 'photos', {'jpg', 'jpeg', 'png', 'webp'}, prefix='user_')
    if not saved:
        flash('La foto debe ser JPG, PNG o WebP.', 'warning')
        return None
    if user and user.photo:
        delete_file(user.photo, 'photos')
    return saved


def _club_assignable_roles():
    return Role.query.filter(Role.name.in_(CLUB_ROLES)).all()


def _club_users():
    """Usuarios del club actual (sin el dueño mismo... incluido para verse)."""
    return User.query.filter_by(club_id=current_club_id()).order_by(User.name).all()


# ═════════════════════════════════════════════════════════════════════════════
# USUARIOS DEL CLUB (solo dueño)
# ═════════════════════════════════════════════════════════════════════════════

@users_bp.route('/users')
@login_required
@club_required
@permission_required('club.users')
def index():
    users = _club_users()
    roles = _club_assignable_roles()
    return render_template('users/index.html', users=users, roles=roles)


@users_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@club_required
@permission_required('club.users')
def new():
    available_roles = _club_assignable_roles()
    if request.method == 'POST':
        allowed_ids = {str(r.id) for r in available_roles}
        selected_ids = [rid for rid in request.form.getlist('role_ids') if rid in allowed_ids]
        if not selected_ids:
            flash('Debes asignar al menos un rol (entrenador o recepción).', 'danger')
            return render_template('users/form.html', user=None, roles=available_roles)

        email = sanitize_input(request.form.get('email', ''))
        if User.query.filter_by(email=email).first():
            flash('Ese correo ya está registrado.', 'danger')
            return render_template('users/form.html', user=None, roles=available_roles)

        password = request.form.get('password', '')
        errors = validate_password(password)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('users/form.html', user=None, roles=available_roles)

        user = User(
            name=sanitize_input(request.form.get('name', '')),
            email=email,
            club_id=current_club_id(),
            active=request.form.get('active') == 'on',
        )
        user.set_password(password)
        photo = _save_user_photo(request.files.get('photo'), None)
        if photo:
            user.photo = photo
        for rid in selected_ids:
            role = Role.query.get(int(rid))
            if role:
                user.roles.append(role)
        db.session.add(user)
        db.session.commit()
        log_activity('Usuario de club creado', f'{user.name} — {user.roles_display}',
                     user=current_user)
        flash('Usuario creado exitosamente.', 'success')
        return redirect(url_for('users.index'))
    return render_template('users/form.html', user=None, roles=available_roles)


@users_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@club_required
@permission_required('club.users')
def edit(id):
    user = User.query.get_or_404(id)
    # Solo usuarios del mismo club
    if user.club_id != current_club_id():
        flash('No tienes permiso para editar este usuario.', 'danger')
        return redirect(url_for('users.index'))
    # El dueño no se edita a sí mismo por aquí (solo staff)
    if user.has_role('dueño') and user.id != current_user.id:
        flash('No puedes editar a otro dueño.', 'danger')
        return redirect(url_for('users.index'))

    available_roles = _club_assignable_roles()
    if request.method == 'POST':
        allowed_ids = {str(r.id) for r in available_roles}
        selected_ids = [rid for rid in request.form.getlist('role_ids') if rid in allowed_ids]

        user.name   = sanitize_input(request.form.get('name', ''))
        user.email  = sanitize_input(request.form.get('email', ''))
        user.active = request.form.get('active') == 'on'

        photo = _save_user_photo(request.files.get('photo'), user)
        if photo:
            user.photo = photo

        new_password = request.form.get('password', '')
        if new_password:
            errors = validate_password(new_password)
            if errors:
                for e in errors:
                    flash(e, 'danger')
                return render_template('users/form.html', user=user, roles=available_roles)
            user.set_password(new_password)

        # No cambiar roles del propio dueño
        if not user.has_role('dueño'):
            user.roles.clear()
            for rid in selected_ids:
                role = Role.query.get(int(rid))
                if role:
                    user.roles.append(role)
        db.session.commit()
        log_activity('Usuario de club editado', user.name, user=current_user)
        flash('Usuario actualizado.', 'success')
        return redirect(url_for('users.index'))
    return render_template('users/form.html', user=user, roles=available_roles)


@users_bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
@club_required
@permission_required('club.users')
def delete(id):
    if id == current_user.id:
        flash('No puedes eliminar tu propia cuenta.', 'danger')
        return redirect(url_for('users.index'))
    db.session.expire_all()
    user = User.query.get_or_404(id)
    if user.club_id != current_club_id() or user.has_role('dueño'):
        flash('No tienes permiso para eliminar este usuario.', 'danger')
        return redirect(url_for('users.index'))
    name = user.name
    user.roles.clear()
    db.session.flush()
    db.session.delete(user)
    db.session.commit()
    log_activity('Usuario de club eliminado', name, user=current_user)
    flash(f'Usuario {name} eliminado.', 'warning')
    return redirect(url_for('users.index'))


# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DEL CLUB: sedes y grupos (dueño + entrenador con club.config)
# ═════════════════════════════════════════════════════════════════════════════

@config_bp.route('/config')
@login_required
@club_required
@permission_required('club.config')
def index():
    venues = Venue.query.filter_by(club_id=current_club_id()).all()
    groups = Group.query.filter_by(club_id=current_club_id()).all()
    return render_template('config/index.html', venues=venues, groups=groups)


@config_bp.route('/config/venue/new', methods=['POST'])
@login_required
@club_required
@permission_required('club.config')
def new_venue():
    db.session.add(Venue(
        club_id=current_club_id(),
        name=request.form.get('name'), address=request.form.get('address'),
        city=request.form.get('city'), phone=request.form.get('phone'),
    ))
    db.session.commit()
    flash('Sede creada.', 'success')
    return redirect(url_for('config.index'))


@config_bp.route('/config/venue/<int:id>/edit', methods=['POST'])
@login_required
@club_required
@permission_required('club.config')
def edit_venue(id):
    v = scoped_or_404(Venue, id)
    v.name = request.form.get('name'); v.address = request.form.get('address')
    v.city = request.form.get('city'); v.phone   = request.form.get('phone')
    v.active = request.form.get('active') == 'on'
    db.session.commit(); flash('Sede actualizada.', 'success')
    return redirect(url_for('config.index'))


@config_bp.route('/config/venue/<int:id>/delete', methods=['POST'])
@login_required
@club_required
@permission_required('club.config')
def delete_venue(id):
    v = scoped_or_404(Venue, id)
    db.session.delete(v); db.session.commit()
    flash('Sede eliminada.', 'warning')
    return redirect(url_for('config.index'))


@config_bp.route('/config/group/new', methods=['POST'])
@login_required
@club_required
@permission_required('club.config')
def new_group():
    db.session.add(Group(
        club_id=current_club_id(),
        name=request.form.get('name'), description=request.form.get('description'),
        venue_id=int(request.form.get('venue_id')), schedule=request.form.get('schedule'),
        monthly_fee=float(request.form.get('monthly_fee', 0)),
    ))
    db.session.commit(); flash('Grupo creado.', 'success')
    return redirect(url_for('config.index'))


@config_bp.route('/config/group/<int:id>/edit', methods=['POST'])
@login_required
@club_required
@permission_required('club.config')
def edit_group(id):
    g = scoped_or_404(Group, id)
    g.name = request.form.get('name'); g.description = request.form.get('description')
    g.venue_id = int(request.form.get('venue_id')); g.schedule = request.form.get('schedule')
    g.monthly_fee = float(request.form.get('monthly_fee', 0))
    g.active = request.form.get('active') == 'on'
    db.session.commit(); flash('Grupo actualizado.', 'success')
    return redirect(url_for('config.index'))


@config_bp.route('/config/group/<int:id>/delete', methods=['POST'])
@login_required
@club_required
@permission_required('club.config')
def delete_group(id):
    g = scoped_or_404(Group, id)
    db.session.delete(g); db.session.commit()
    flash('Grupo eliminado.', 'warning')
    return redirect(url_for('config.index'))
