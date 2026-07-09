import os, uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from models import User, Role, RegistrationRequest, log_activity
from app import db
from datetime import datetime
from routes.password_policy import validate_password, sanitize_input

auth_bp = Blueprint('auth', __name__)

ALLOWED_LOGO = {'png', 'jpg', 'jpeg', 'webp', 'svg'}


def _redirect_by_role():
    """Redirige al panel correcto según el rol."""
    if current_user.has_permission('platform.manage'):
        return redirect(url_for('platform.dashboard'))
    return redirect(url_for('dashboard.index'))


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role()
    if request.method == 'POST':
        email    = sanitize_input(request.form.get('email', ''))
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.active:
            # Verificar club suspendido
            if user.club and user.club.status == 'suspendido':
                flash('Tu club está suspendido. Contacta al administrador de la plataforma.', 'danger')
                return render_template('auth/login.html')
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            log_activity('Inicio de sesión', user.email, user=user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else _redirect_by_role()
        flash('Credenciales incorrectas o cuenta inactiva.', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/registrar-club', methods=['GET', 'POST'])
def register_club():
    """Formulario público: solicitud de registro de un club nuevo."""
    if request.method == 'POST':
        owner_name  = sanitize_input(request.form.get('owner_name', ''))
        owner_email = sanitize_input(request.form.get('owner_email', ''))
        password    = request.form.get('password', '')
        confirm     = request.form.get('confirm_password', '')
        club_name   = sanitize_input(request.form.get('club_name', ''))
        city        = sanitize_input(request.form.get('city', ''))
        address     = sanitize_input(request.form.get('address', ''))
        phone       = sanitize_input(request.form.get('phone', ''))
        description = sanitize_input(request.form.get('description', ''))

        # Validaciones
        errors = validate_password(password)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register_club.html')
        if password != confirm:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('auth/register_club.html')
        if not owner_name or not owner_email or not club_name:
            flash('Nombre, correo y nombre del club son obligatorios.', 'danger')
            return render_template('auth/register_club.html')
        if User.query.filter_by(email=owner_email).first():
            flash('Ya existe una cuenta con ese correo.', 'danger')
            return render_template('auth/register_club.html')
        if RegistrationRequest.query.filter_by(owner_email=owner_email,
                                               status='pendiente').first():
            flash('Ya tienes una solicitud pendiente con ese correo.', 'warning')
            return render_template('auth/register_club.html')

        # Logo opcional
        logo_name = None
        file = request.files.get('logo')
        if file and file.filename:
            from routes.storage import save_file
            logo_name = save_file(file, 'schools', ALLOWED_LOGO, prefix='req_')

        req = RegistrationRequest(
            owner_name=owner_name, owner_email=owner_email,
            password_hash=generate_password_hash(password),
            club_name=club_name, city=city, address=address,
            phone=phone, description=description, logo=logo_name,
            status='pendiente',
        )
        db.session.add(req)
        db.session.commit()
        log_activity('Nueva solicitud de registro', f'Club: {club_name} — {owner_email}')
        from routes.notifications import notify_new_registration_request
        notify_new_registration_request(club_name, owner_name)
        flash('Solicitud enviada. El administrador la revisará y recibirás acceso cuando sea aprobada.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register_club.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('auth.login'))
