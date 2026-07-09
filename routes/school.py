import os, uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from models import User
from app import db
from routes.decorators import permission_required, club_required

school_bp = Blueprint('school', __name__)

ALLOWED = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED


@school_bp.route('/mi-escuela', methods=['GET', 'POST'])
@login_required
@club_required
@permission_required('club.config')
def settings():

    if request.method == 'POST':
        school_name = request.form.get('school_name', '').strip()
        school_color    = request.form.get('school_color',     '#1a56db').strip()
        color_sidebar   = request.form.get('color_sidebar_bg', '#0f172a').strip()
        color_topbar    = request.form.get('color_topbar_bg',  '#ffffff').strip()
        color_body      = request.form.get('color_body_bg',    '#f1f5f9').strip()
        remove_logo     = request.form.get('remove_logo')
        file            = request.files.get('school_logo')

        current_user.school_name      = school_name or None
        current_user.school_color     = school_color
        current_user.color_sidebar_bg = color_sidebar
        current_user.color_topbar_bg  = color_topbar
        current_user.color_body_bg    = color_body

        if remove_logo and current_user.school_logo:
            from routes.storage import delete_file
            delete_file(current_user.school_logo, 'schools')
            current_user.school_logo = None

        if file and file.filename and _allowed(file.filename):
            from routes.storage import save_file, delete_file
            saved = save_file(file, 'schools', ALLOWED, prefix='logo_')
            if saved:
                if current_user.school_logo:
                    delete_file(current_user.school_logo, 'schools')
                current_user.school_logo = saved

        db.session.commit()
        flash('Perfil de escuela actualizado correctamente.', 'success')
        return redirect(url_for('school.settings'))

    return render_template('school/settings.html')


def _delete_logo(fname):
    try:
        path = os.path.join('static', 'uploads', 'schools', fname)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
