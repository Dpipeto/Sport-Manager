from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from models import Assessment, Injury, Athlete
from app import db
from datetime import date
from routes.decorators import permission_required, club_required, current_club_id, scoped_or_404, athlete_scoped_or_404

assessments_bp = Blueprint('assessments', __name__)


# ── Valoraciones (admin + entrenador) ─────────────────────────────────────────
@assessments_bp.route('/assessments')
@login_required
@club_required
@permission_required('assessments.view')
def index():
    athletes = Athlete.query.filter_by(club_id=current_club_id()).order_by(Athlete.last_name).all()
    return render_template('assessments/index.html', athletes=athletes)


@assessments_bp.route('/assessments/athlete/<int:athlete_id>')
@login_required
@club_required
@permission_required('assessments.view')
def athlete_assessments(athlete_id):
    athlete     = scoped_or_404(Athlete, athlete_id)
    assessments = Assessment.query.filter_by(athlete_id=athlete_id).order_by(Assessment.date.desc()).all()
    injuries    = Injury.query.filter_by(athlete_id=athlete_id).order_by(Injury.date.desc()).all()
    return render_template('assessments/athlete.html',
                           athlete=athlete, assessments=assessments, injuries=injuries)


@assessments_bp.route('/assessments/new/<int:athlete_id>', methods=['GET', 'POST'])
@login_required
@club_required
@permission_required('assessments.view')
def new_assessment(athlete_id):
    athlete = scoped_or_404(Athlete, athlete_id)
    if request.method == 'POST':
        a = Assessment(
            athlete_id=athlete_id,
            date=_parse_date(request.form.get('date')) or date.today(),
            type=request.form.get('type'),
            weight=_float(request.form.get('weight')),
            height=_float(request.form.get('height')),
            bmi=_float(request.form.get('bmi')),
            body_fat=_float(request.form.get('body_fat')),
            muscle_mass=_float(request.form.get('muscle_mass')),
            waist=_float(request.form.get('waist')),
            hip=_float(request.form.get('hip')),
            chest=_float(request.form.get('chest')),
            flexibility=_float(request.form.get('flexibility')),
            strength=_float(request.form.get('strength')),
            resistance=_float(request.form.get('resistance')),
            speed=_float(request.form.get('speed')),
            coordination=_float(request.form.get('coordination')),
            vo2_max=_float(request.form.get('vo2_max')),
            resting_hr=_int(request.form.get('resting_hr')),
            max_hr=_int(request.form.get('max_hr')),
            blood_pressure_sys=_int(request.form.get('blood_pressure_sys')),
            blood_pressure_dia=_int(request.form.get('blood_pressure_dia')),
            notes=request.form.get('notes'),
        )
        db.session.add(a)
        db.session.commit()
        flash('Valoración registrada.', 'success')
        return redirect(url_for('assessments.athlete_assessments', athlete_id=athlete_id))
    return render_template('assessments/form.html', athlete=athlete)


@assessments_bp.route('/assessments/<int:id>/delete', methods=['POST'])
@login_required
@club_required
@permission_required('assessments.view')
def delete_assessment(id):
    a = athlete_scoped_or_404(Assessment, id)
    athlete_id = a.athlete_id
    db.session.delete(a)
    db.session.commit()
    flash('Valoración eliminada.', 'warning')
    return redirect(url_for('assessments.athlete_assessments', athlete_id=athlete_id))


@assessments_bp.route('/assessments/injury/new/<int:athlete_id>', methods=['GET', 'POST'])
@login_required
@club_required
@permission_required('assessments.view')
def new_injury(athlete_id):
    athlete = scoped_or_404(Athlete, athlete_id)
    if request.method == 'POST':
        inj = Injury(
            athlete_id=athlete_id,
            date=_parse_date(request.form.get('date')) or date.today(),
            injury_type=request.form.get('injury_type'),
            body_part=request.form.get('body_part'),
            severity=request.form.get('severity'),
            description=request.form.get('description'),
            treatment=request.form.get('treatment'),
            recovery_date=_parse_date(request.form.get('recovery_date')),
            status=request.form.get('status', 'activa'),
        )
        db.session.add(inj)
        db.session.commit()
        flash('Lesión registrada.', 'success')
        return redirect(url_for('assessments.athlete_assessments', athlete_id=athlete_id))
    return render_template('assessments/injury_form.html', athlete=athlete)


@assessments_bp.route('/assessments/injury/<int:id>/delete', methods=['POST'])
@login_required
@club_required
@permission_required('assessments.view')
def delete_injury(id):
    inj = athlete_scoped_or_404(Injury, id)
    athlete_id = inj.athlete_id
    db.session.delete(inj)
    db.session.commit()
    flash('Lesión eliminada.', 'warning')
    return redirect(url_for('assessments.athlete_assessments', athlete_id=athlete_id))


def _parse_date(s):
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None

def _float(v):
    try:
        return float(v) if v else None
    except (ValueError, TypeError):
        return None

def _int(v):
    try:
        return int(v) if v else None
    except (ValueError, TypeError):
        return None
