from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

# ═════════════════════════════════════════════════════════════════════════════
# TABLAS DE ASOCIACIÓN
# ═════════════════════════════════════════════════════════════════════════════

user_roles_table = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True)
)

role_permissions_table = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True)
)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ═════════════════════════════════════════════════════════════════════════════
# RBAC: PERMISOS Y ROLES
# ═════════════════════════════════════════════════════════════════════════════

class Permission(db.Model):
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)   # ej: athletes.view
    description = db.Column(db.String(200))


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    permissions = db.relationship('Permission', secondary=role_permissions_table,
                                  lazy='subquery', backref=db.backref('roles', lazy=True))

    def has_permission(self, code):
        return any(p.code == code for p in self.permissions)


# ═════════════════════════════════════════════════════════════════════════════
# CLUB (multi-tenant)
# ═════════════════════════════════════════════════════════════════════════════

class Club(db.Model):
    __tablename__ = 'clubs'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(100))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(30))
    description = db.Column(db.Text)
    logo = db.Column(db.String(300))
    status = db.Column(db.String(20), default='activo')   # activo | suspendido
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Integraciones
    sms_api_key = db.Column(db.String(64), unique=True)    # webhook SMS bancarios
    ntfy_topic  = db.Column(db.String(100))                # notificaciones push del club
    # Correo propio del club (para notificaciones de cobros)
    mail_username = db.Column(db.String(150))   # cuenta Gmail del club
    mail_password = db.Column(db.String(150))   # contraseña de aplicación
    mail_server   = db.Column(db.String(100), default='smtp.gmail.com')
    mail_port     = db.Column(db.Integer, default=587)

    users = db.relationship('User', backref='club', lazy=True)
    athletes = db.relationship('Athlete', backref='club', lazy=True)
    venues = db.relationship('Venue', backref='club', lazy=True)

    @property
    def owner(self):
        for u in self.users:
            if u.has_role('dueño'):
                return u
        return None

    @property
    def member_count(self):
        return len(self.users)

    @property
    def athlete_count(self):
        return len(self.athletes)


class RegistrationRequest(db.Model):
    """Solicitud pública de registro de un club nuevo."""
    __tablename__ = 'registration_requests'
    id = db.Column(db.Integer, primary_key=True)
    # Datos del dueño
    owner_name = db.Column(db.String(100), nullable=False)
    owner_email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # Datos del club
    club_name = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(100))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(30))
    description = db.Column(db.Text)
    logo = db.Column(db.String(300))
    # Flujo
    status = db.Column(db.String(20), default='pendiente')  # pendiente|aprobada|rechazada
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)


class ActivityLog(db.Model):
    """Registro de actividad del sistema."""
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user_name = db.Column(db.String(100))
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)


def log_activity(action, details='', user=None, club_id=None):
    """Helper para registrar actividad."""
    try:
        entry = ActivityLog(
            user_id=user.id if user else None,
            user_name=user.name if user else 'Sistema',
            club_id=club_id or (user.club_id if user else None),
            action=action,
            details=details,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()


class BankTransaction(db.Model):
    """Transacción detectada automáticamente desde SMS bancarios."""
    __tablename__ = 'bank_transactions'
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=False)
    bank = db.Column(db.String(30))            # nequi | bancolombia | davivienda | otro
    amount = db.Column(db.Float, nullable=False)
    sender = db.Column(db.String(150))         # nombre detectado en el SMS
    raw_message = db.Column(db.Text)           # SMS original completo
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pendiente')  # pendiente|confirmada|descartada
    # Al confirmar, se puede vincular a un deportista y crear el Payment
    athlete_id = db.Column(db.Integer, db.ForeignKey('athletes.id'))
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'))
    confirmed_by = db.Column(db.String(100))
    confirmed_at = db.Column(db.DateTime)

    athlete = db.relationship('Athlete', foreign_keys=[athlete_id])


# ═════════════════════════════════════════════════════════════════════════════
# USUARIOS
# ═════════════════════════════════════════════════════════════════════════════

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))   # legacy
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))   # multi-tenant
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    # Branding del club (para dueños/entrenadores)
    school_name  = db.Column(db.String(150))
    school_logo  = db.Column(db.String(300))
    school_color = db.Column(db.String(7),  default='#1a56db')
    color_sidebar_bg = db.Column(db.String(7), default='#0f172a')
    color_topbar_bg  = db.Column(db.String(7), default='#ffffff')
    color_body_bg    = db.Column(db.String(7), default='#f1f5f9')
    ntfy_topic = db.Column(db.String(100))   # tema de notificaciones push personales
    photo = db.Column(db.String(200))         # foto de perfil

    roles = db.relationship('Role', secondary=user_roles_table, lazy='subquery',
                            backref=db.backref('users', lazy=True))

    # ── RBAC ────────────────────────────────────────────────────────────────
    def has_role(self, *role_names):
        return any(r.name in role_names for r in self.roles)

    def has_permission(self, code):
        """RBAC: verifica si alguno de los roles del usuario tiene el permiso."""
        return any(r.has_permission(code) for r in self.roles)

    @property
    def is_superadmin(self):
        return self.has_role('superadmin')

    @property
    def primary_role(self):
        priority = ['superadmin', 'dueño', 'entrenador', 'recepcion']
        for p in priority:
            for r in self.roles:
                if r.name == p:
                    return r
        return self.roles[0] if self.roles else None

    @property
    def roles_display(self):
        names = {'superadmin': 'Super Admin', 'dueño': 'Dueño', 'entrenador': 'Entrenador', 'recepcion': 'Recepción'}
        return ', '.join(names.get(r.name, r.name.capitalize()) for r in self.roles) if self.roles else 'Sin rol'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# ═════════════════════════════════════════════════════════════════════════════
# ENTIDADES DEL CLUB (todas con club_id)
# ═════════════════════════════════════════════════════════════════════════════

class Venue(db.Model):
    __tablename__ = 'venues'
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    city = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    groups = db.relationship('Group', backref='venue', lazy=True)


class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    venue_id = db.Column(db.Integer, db.ForeignKey('venues.id'))
    schedule = db.Column(db.String(200))
    monthly_fee = db.Column(db.Float, default=0.0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    athletes = db.relationship('AthleteGroup', backref='group', lazy=True)


class Athlete(db.Model):
    __tablename__ = 'athletes'
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    document_type = db.Column(db.String(20), default='CC')
    document_number = db.Column(db.String(30))
    birth_date = db.Column(db.Date)
    gender = db.Column(db.String(10))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.String(200))
    city = db.Column(db.String(100))
    emergency_contact = db.Column(db.String(100))
    emergency_phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='activo')
    position = db.Column(db.String(80))   # posición de juego (armador, delantero, etc.)
    entry_date = db.Column(db.Date, default=date.today)
    notes = db.Column(db.Text)
    photo = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    groups = db.relationship('AthleteGroup', backref='athlete', lazy=True,
                             cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='athlete', lazy=True,
                               cascade='all, delete-orphan')
    documents = db.relationship('AthleteDocument', backref='athlete', lazy=True,
                                cascade='all, delete-orphan')
    assessments = db.relationship('Assessment', backref='athlete', lazy=True,
                                  cascade='all, delete-orphan')
    injuries = db.relationship('Injury', backref='athlete', lazy=True,
                               cascade='all, delete-orphan')

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        if self.birth_date:
            today = date.today()
            return today.year - self.birth_date.year - (
                (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
            )
        return None

    @property
    def total_debt(self):
        total_charges = sum(p.amount for p in self.payments if p.type == 'cargo')
        total_paid = sum(p.amount for p in self.payments if p.type == 'pago')
        return total_charges - total_paid


class AthleteGroup(db.Model):
    __tablename__ = 'athlete_groups'
    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey('athletes.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    enrolled_date = db.Column(db.Date, default=date.today)
    active = db.Column(db.Boolean, default=True)


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey('athletes.id'), nullable=False)
    type = db.Column(db.String(10), nullable=False)
    concept = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=date.today)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='pendiente')
    payment_method = db.Column(db.String(50))
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    email_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AthleteDocument(db.Model):
    __tablename__ = 'athlete_documents'
    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey('athletes.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200))
    file_type = db.Column(db.String(10))
    description = db.Column(db.String(200))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Assessment(db.Model):
    __tablename__ = 'assessments'
    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey('athletes.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    type = db.Column(db.String(50))
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    bmi = db.Column(db.Float)
    body_fat = db.Column(db.Float)
    muscle_mass = db.Column(db.Float)
    waist = db.Column(db.Float)
    hip = db.Column(db.Float)
    chest = db.Column(db.Float)
    flexibility = db.Column(db.Float)
    strength = db.Column(db.Float)
    resistance = db.Column(db.Float)
    speed = db.Column(db.Float)
    coordination = db.Column(db.Float)
    vo2_max = db.Column(db.Float)
    resting_hr = db.Column(db.Integer)
    max_hr = db.Column(db.Integer)
    blood_pressure_sys = db.Column(db.Integer)
    blood_pressure_dia = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Injury(db.Model):
    __tablename__ = 'injuries'
    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey('athletes.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    injury_type = db.Column(db.String(100))
    body_part = db.Column(db.String(100))
    severity = db.Column(db.String(20))
    description = db.Column(db.Text)
    treatment = db.Column(db.Text)
    recovery_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='activa')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ═════════════════════════════════════════════════════════════════════════════
# SEED: PERMISOS, ROLES, SUPERADMIN
# ═════════════════════════════════════════════════════════════════════════════

PERMISSION_DEFS = [
    # Deportistas
    ('athletes.view',    'Ver deportistas del club'),
    ('athletes.manage',  'Crear y editar deportistas'),
    ('athletes.delete',  'Eliminar deportistas'),
    # Asistencia y rendimiento
    ('training.manage',  'Registrar asistencia, observaciones y rendimiento'),
    # Finanzas
    ('billing.view',     'Ver cobros, pagos e historial financiero'),
    ('billing.manage',   'Registrar pagos, ingresos, gastos y deudas'),
    # Valoraciones
    ('assessments.view',   'Ver valoraciones físicas'),
    ('assessments.manage', 'Registrar valoraciones y lesiones'),
    # Club
    ('club.config',   'Configurar el club (sedes, grupos, marca)'),
    ('club.users',    'Administrar usuarios del club'),
    ('club.reports',  'Ver reportes del club'),
    # Plataforma (solo superadmin)
    ('platform.manage', 'Administrar la plataforma completa'),
]

ROLE_PERMISSION_MAP = {
    'superadmin': ['platform.manage'],
    'dueño': [
        'athletes.view', 'athletes.manage', 'athletes.delete',
        'training.manage',
        'billing.view', 'billing.manage',
        'assessments.view', 'assessments.manage',
        'club.config', 'club.users', 'club.reports',
    ],
    'entrenador': [
        'athletes.view', 'athletes.manage',
        'training.manage',
        'assessments.view', 'assessments.manage',
    ],
    'recepcion': [
        'athletes.view',
        'billing.view', 'billing.manage',
        'club.reports',
    ],
}

ROLE_DEFS = [
    ('superadmin', 'Super Administrador de la plataforma'),
    ('dueño',      'Dueño del club — administra todo su club'),
    ('entrenador', 'Entrenador — parte deportiva del club'),
    ('recepcion',  'Recepción/Tesorería — parte financiera del club'),
]


def seed_data():
    """Crea permisos, roles, superadmin y repara datos existentes."""
    # 1. Permisos
    for code, desc in PERMISSION_DEFS:
        if not Permission.query.filter_by(code=code).first():
            db.session.add(Permission(code=code, description=desc))
    db.session.commit()

    # 2. Roles (renombra 'admin' legado a 'superadmin')
    legacy_admin = Role.query.filter_by(name='admin').first()
    if legacy_admin and not Role.query.filter_by(name='superadmin').first():
        legacy_admin.name = 'superadmin'
        legacy_admin.description = 'Super Administrador de la plataforma'
        db.session.commit()

    for name, desc in ROLE_DEFS:
        if not Role.query.filter_by(name=name).first():
            db.session.add(Role(name=name, description=desc))
    db.session.commit()

    # 3. Asignar permisos a roles
    for role_name, perm_codes in ROLE_PERMISSION_MAP.items():
        role = Role.query.filter_by(name=role_name).first()
        if role:
            existing = {p.code for p in role.permissions}
            for code in perm_codes:
                if code not in existing:
                    perm = Permission.query.filter_by(code=code).first()
                    if perm:
                        role.permissions.append(perm)
    db.session.commit()

    # 4. Superadmin por defecto
    if User.query.count() == 0:
        sa_role = Role.query.filter_by(name='superadmin').first()
        sa = User(name='Super Administrador', email='admin@sport.com')
        sa.set_password('admin123')
        sa.roles.append(sa_role)
        db.session.add(sa)
        db.session.commit()

    # 5. Reparaciones de datos legados
    for user in User.query.all():
        if user.role_id and not user.roles:
            role = Role.query.get(user.role_id)
            if role:
                user.roles.append(role)
    db.session.commit()

    # 6. Club por defecto para datos legados sin club
    orphan_users = [u for u in User.query.all()
                    if not u.club_id and not u.has_role('superadmin') and u.roles]
    orphan_athletes = Athlete.query.filter_by(club_id=None).count()
    if orphan_users or orphan_athletes:
        default_club = Club.query.filter_by(name='Mi Club').first()
        if not default_club:
            default_club = Club(name='Mi Club', status='activo',
                                description='Club creado automáticamente para datos existentes')
            db.session.add(default_club)
            db.session.flush()
        for u in orphan_users:
            u.club_id = default_club.id
        Athlete.query.filter_by(club_id=None).update({'club_id': default_club.id})
        Venue.query.filter_by(club_id=None).update({'club_id': default_club.id})
        Group.query.filter_by(club_id=None).update({'club_id': default_club.id})
        db.session.commit()
