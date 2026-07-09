"""
Transacciones bancarias automáticas por SMS.

Flujo:
  1. El dueño genera su API key en /banco/configuracion
  2. Instala una app de reenvío de SMS en su Android (ej: "SMS Forwarder")
  3. Configura la app para reenviar SMS de Nequi/Bancolombia/Davivienda a:
       POST https://su-servidor.com/api/sms/<api_key>
     con el texto del SMS en el cuerpo (campo "message" o texto plano)
  4. El sistema parsea el SMS, crea la transacción pendiente y notifica
     al celular del club vía push.
  5. Recepción/dueño la revisa en /banco, la vincula a un deportista
     y la confirma → se crea el Payment automáticamente.
"""
import secrets
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import (Club, BankTransaction, Athlete, Payment,
                    log_activity, db)
from routes.decorators import permission_required, club_required, current_club_id
from routes.sms_parser import parse_bank_sms
from routes.notifications import notify_bank_transaction

bank_bp = Blueprint('bank', __name__)


# ═════════════════════════════════════════════════════════════════════════════
# WEBHOOK PÚBLICO — recibe los SMS reenviados desde el celular
# ═════════════════════════════════════════════════════════════════════════════

@bank_bp.route('/api/sms/<api_key>', methods=['POST'])
def sms_webhook(api_key):
    """
    Endpoint público autenticado por API key del club.
    Acepta JSON {"message": "..."} o texto plano en el body.
    """
    club = Club.query.filter_by(sms_api_key=api_key).first()
    if not club or club.status != 'activo':
        return jsonify({'error': 'API key inválida'}), 401

    # Extraer el texto del SMS (formatos comunes de apps de reenvío)
    text = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        text = data.get('message') or data.get('text') or data.get('body') or data.get('sms')
    if not text:
        text = request.form.get('message') or request.form.get('text') or request.form.get('body')
    if not text:
        text = request.get_data(as_text=True)

    if not text or not text.strip():
        return jsonify({'error': 'SMS vacío'}), 400

    parsed = parse_bank_sms(text.strip())
    if not parsed:
        # No es un ingreso — se ignora silenciosamente (la app reenvía todo)
        return jsonify({'status': 'ignorado', 'reason': 'no es un ingreso bancario'}), 200

    tx = BankTransaction(
        club_id=club.id,
        bank=parsed['bank'],
        amount=parsed['amount'],
        sender=parsed['sender'],
        raw_message=text.strip()[:2000],
        status='pendiente',
    )
    db.session.add(tx)
    db.session.commit()

    log_activity('Transacción SMS recibida',
                 f'{parsed["bank"]} ${parsed["amount"]:,.0f}', club_id=club.id)
    notify_bank_transaction(club, tx)

    return jsonify({'status': 'registrado', 'id': tx.id,
                    'bank': tx.bank, 'amount': tx.amount}), 201


# ═════════════════════════════════════════════════════════════════════════════
# PANEL DE TRANSACCIONES (dueño + recepción)
# ═════════════════════════════════════════════════════════════════════════════

@bank_bp.route('/banco')
@login_required
@club_required
@permission_required('billing.view')
def index():
    status = request.args.get('status', 'pendiente')
    query = BankTransaction.query.filter_by(club_id=current_club_id())
    if status:
        query = query.filter_by(status=status)
    transactions = query.order_by(BankTransaction.received_at.desc()).all()
    athletes = Athlete.query.filter_by(club_id=current_club_id()).order_by(
        Athlete.last_name).all()
    pending_count = BankTransaction.query.filter_by(
        club_id=current_club_id(), status='pendiente').count()
    return render_template('bank/index.html', transactions=transactions,
                           athletes=athletes, status_filter=status,
                           pending_count=pending_count)


@bank_bp.route('/banco/<int:id>/confirmar', methods=['POST'])
@login_required
@club_required
@permission_required('billing.manage')
def confirm(id):
    tx = BankTransaction.query.get_or_404(id)
    if tx.club_id != current_club_id():
        flash('Transacción no válida.', 'danger')
        return redirect(url_for('bank.index'))
    if tx.status != 'pendiente':
        flash('Esta transacción ya fue procesada.', 'warning')
        return redirect(url_for('bank.index'))

    athlete_id = request.form.get('athlete_id')
    concept = request.form.get('concept', 'Pago recibido por transferencia')

    payment = None
    if athlete_id:
        athlete = Athlete.query.get(int(athlete_id))
        if athlete and athlete.club_id == current_club_id():
            bank_names = {'nequi': 'Nequi', 'bancolombia': 'Bancolombia',
                          'davivienda': 'Davivienda', 'otro': 'Transferencia'}
            payment = Payment(
                athlete_id=athlete.id,
                type='pago',
                concept=concept,
                amount=tx.amount,
                status='pagado',
                payment_method=bank_names.get(tx.bank, 'Transferencia'),
                reference=f'SMS-{tx.id}',
                notes=f'Registrado automáticamente desde SMS de {tx.bank}. '
                      f'Remitente detectado: {tx.sender or "N/D"}',
            )
            db.session.add(payment)
            db.session.flush()
            tx.athlete_id = athlete.id
            tx.payment_id = payment.id

    tx.status = 'confirmada'
    tx.confirmed_by = current_user.name
    tx.confirmed_at = datetime.utcnow()
    db.session.commit()

    log_activity('Transacción confirmada',
                 f'${tx.amount:,.0f} ({tx.bank})' +
                 (f' → {tx.athlete.full_name}' if tx.athlete else ''),
                 user=current_user)
    flash(f'Transacción de ${tx.amount:,.0f} confirmada' +
          (' y pago registrado al deportista.' if payment else '.'), 'success')
    return redirect(url_for('bank.index'))


@bank_bp.route('/banco/<int:id>/descartar', methods=['POST'])
@login_required
@club_required
@permission_required('billing.manage')
def discard(id):
    tx = BankTransaction.query.get_or_404(id)
    if tx.club_id != current_club_id():
        flash('Transacción no válida.', 'danger')
        return redirect(url_for('bank.index'))
    tx.status = 'descartada'
    tx.confirmed_by = current_user.name
    tx.confirmed_at = datetime.utcnow()
    db.session.commit()
    flash('Transacción descartada.', 'warning')
    return redirect(url_for('bank.index'))


# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN: API key + notificaciones push (solo dueño)
# ═════════════════════════════════════════════════════════════════════════════

@bank_bp.route('/banco/configuracion', methods=['GET', 'POST'])
@login_required
@club_required
@permission_required('club.config')
def settings():
    club = Club.query.get(current_club_id())
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate_key':
            club.sms_api_key = secrets.token_urlsafe(24)
            db.session.commit()
            log_activity('API key de SMS generada', club.name, user=current_user)
            flash('Nueva API key generada. Actualiza la app de reenvío de SMS.', 'success')
        elif action == 'revoke_key':
            club.sms_api_key = None
            db.session.commit()
            flash('API key revocada. El webhook quedó desactivado.', 'warning')
        elif action == 'save_ntfy':
            club.ntfy_topic = request.form.get('ntfy_topic', '').strip() or None
            db.session.commit()
            flash('Tema de notificaciones guardado.', 'success')
        elif action == 'generate_ntfy':
            club.ntfy_topic = f'sportmanager-{secrets.token_urlsafe(8).lower()}'
            db.session.commit()
            flash('Tema de notificaciones generado. Suscríbete desde la app ntfy.', 'success')
        return redirect(url_for('bank.settings'))
    return render_template('bank/settings.html', club=club)
