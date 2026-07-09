"""
Dashboard del CLUB — scoped por club_id.
El superadmin es redirigido a /platform.
"""
from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import date, timedelta
from models import Athlete, Payment, Group, db
from routes.decorators import club_required, current_club_id

dashboard_bp = Blueprint('dashboard', __name__)


def _club_analytics(club_id):
    """Analytics del club actual (sin Spark, directo con SQLAlchemy)."""
    athletes = Athlete.query.filter_by(club_id=club_id).all()

    status_counts = {}
    for a in athletes:
        status_counts[a.status] = status_counts.get(a.status, 0) + 1

    # Nuevos deportistas por mes (últimos 6 meses)
    months_data = []
    today = date.today()
    for i in range(5, -1, -1):
        month_date = date(today.year, today.month, 1) - timedelta(days=30 * i)
        key = month_date.strftime('%Y-%m')
        label = month_date.strftime('%b %Y')
        count = sum(1 for a in athletes
                    if a.created_at and a.created_at.strftime('%Y-%m') == key)
        months_data.append({'month': label, 'count': count})

    # Ingresos por mes
    athlete_ids = [a.id for a in athletes]
    income_data = []
    if athlete_ids:
        for i in range(5, -1, -1):
            month_date = date(today.year, today.month, 1) - timedelta(days=30 * i)
            key = month_date.strftime('%Y-%m')
            label = month_date.strftime('%b %Y')
            month_payments = Payment.query.filter(
                Payment.athlete_id.in_(athlete_ids),
                Payment.type == 'pago',
            ).all()
            total = sum(p.amount for p in month_payments
                        if p.date and p.date.strftime('%Y-%m') == key)
            income_data.append({'month': label, 'total': float(total)})
    else:
        income_data = [{'month': '', 'total': 0}]

    return {
        'status_counts': status_counts,
        'monthly_new': months_data,
        'monthly_income': income_data,
    }


@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Superadmin → panel de plataforma
    if current_user.has_permission('platform.manage'):
        return redirect(url_for('platform.dashboard'))
    return _club_dashboard()


@club_required
def _club_dashboard():
    club_id = current_club_id()

    total_athletes     = Athlete.query.filter_by(club_id=club_id).count()
    active_athletes    = Athlete.query.filter_by(club_id=club_id, status='activo').count()
    inactive_athletes  = Athlete.query.filter_by(club_id=club_id, status='inactivo').count()
    suspended_athletes = Athlete.query.filter_by(club_id=club_id, status='suspendido').count()

    athlete_ids = [a.id for a in Athlete.query.filter_by(club_id=club_id).all()]

    today = date.today()
    monthly_income = 0
    total_pending = 0
    recent_payments = []
    if athlete_ids:
        month_key = today.strftime('%Y-%m')
        monthly_income = sum(
            p.amount for p in Payment.query.filter(
                Payment.athlete_id.in_(athlete_ids),
                Payment.type == 'pago').all()
            if p.date and p.date.strftime('%Y-%m') == month_key
        )

        total_charges = db.session.query(func.sum(Payment.amount)).filter(
            Payment.athlete_id.in_(athlete_ids), Payment.type == 'cargo').scalar() or 0
        total_paid = db.session.query(func.sum(Payment.amount)).filter(
            Payment.athlete_id.in_(athlete_ids), Payment.type == 'pago').scalar() or 0
        total_pending = max(total_charges - total_paid, 0)

        recent_payments = Payment.query.filter(
            Payment.athlete_id.in_(athlete_ids)).order_by(
            Payment.created_at.desc()).limit(5).all()

    recent_athletes = Athlete.query.filter_by(club_id=club_id).order_by(
        Athlete.created_at.desc()).limit(5).all()
    total_groups = Group.query.filter_by(club_id=club_id, active=True).count()

    analytics = _club_analytics(club_id)

    return render_template('dashboard/index.html',
                           total_athletes=total_athletes,
                           active_athletes=active_athletes,
                           inactive_athletes=inactive_athletes,
                           suspended_athletes=suspended_athletes,
                           monthly_income=monthly_income,
                           total_pending=total_pending,
                           recent_athletes=recent_athletes,
                           recent_payments=recent_payments,
                           total_groups=total_groups,
                           analytics=analytics)


@dashboard_bp.route('/dashboard/analytics')
@login_required
def analytics_api():
    if current_user.has_permission('platform.manage'):
        return jsonify({})
    return jsonify(_club_analytics(current_club_id()))
