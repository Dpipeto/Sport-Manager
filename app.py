from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
import os

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
migrate = Migrate()


def _migrate_columns(db):
    """
    Agrega columnas/tablas nuevas a una BD SQLite existente sin perder datos.
    En PostgreSQL no aplica: db.create_all() crea el esquema completo
    (las instalaciones Postgres parten de cero o usan Flask-Migrate).
    """
    import sqlalchemy as sa
    if db.engine.dialect.name != 'sqlite':
        return
    with db.engine.connect() as conn:
        tables = {row[0] for row in conn.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='table'"))}

        # ── Columnas nuevas en users ─────────────────────────────────────────
        if 'users' in tables:
            cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(users)"))}
            for col, typedef in [
                ('school_name',      'VARCHAR(150)'),
                ('school_logo',      'VARCHAR(300)'),
                ('school_color',     "VARCHAR(7) DEFAULT '#1a56db'"),
                ('color_sidebar_bg', "VARCHAR(7) DEFAULT '#0f172a'"),
                ('color_topbar_bg',  "VARCHAR(7) DEFAULT '#ffffff'"),
                ('color_body_bg',    "VARCHAR(7) DEFAULT '#f1f5f9'"),
                ('club_id',          'INTEGER REFERENCES clubs(id)'),
            ]:
                if col not in cols:
                    conn.execute(sa.text(f"ALTER TABLE users ADD COLUMN {col} {typedef}"))

        # ── position en athletes ─────────────────────────────────────────────
        if 'athletes' in tables:
            cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(athletes)"))}
            if 'position' not in cols:
                conn.execute(sa.text("ALTER TABLE athletes ADD COLUMN position VARCHAR(80)"))

        # ── club_id en tablas del club ───────────────────────────────────────
        for table in ('athletes', 'venues', 'groups'):
            if table in tables:
                cols = {row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})"))}
                if 'club_id' not in cols:
                    conn.execute(sa.text(
                        f"ALTER TABLE {table} ADD COLUMN club_id INTEGER REFERENCES clubs(id)"))

        # ── Columnas nuevas en clubs ─────────────────────────────────────────
        if 'clubs' in tables:
            cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(clubs)"))}
            for col, typedef in [
                ('sms_api_key', 'VARCHAR(64)'),
                ('ntfy_topic',  'VARCHAR(100)'),
            ]:
                if col not in cols:
                    conn.execute(sa.text(f"ALTER TABLE clubs ADD COLUMN {col} {typedef}"))

        # ── ntfy_topic en users ───────────────────────────────────────────────
        if 'users' in tables:
            cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(users)"))}
            if 'ntfy_topic' not in cols:
                conn.execute(sa.text("ALTER TABLE users ADD COLUMN ntfy_topic VARCHAR(100)"))
            if 'photo' not in cols:
                conn.execute(sa.text("ALTER TABLE users ADD COLUMN photo VARCHAR(200)"))

        # ── user_roles ───────────────────────────────────────────────────────
        if 'user_roles' not in tables:
            conn.execute(sa.text(
                "CREATE TABLE user_roles ("
                "  user_id INTEGER NOT NULL REFERENCES users(id),"
                "  role_id INTEGER NOT NULL REFERENCES roles(id),"
                "  PRIMARY KEY (user_id, role_id))"
            ))
            if 'users' in tables:
                conn.execute(sa.text(
                    "INSERT OR IGNORE INTO user_roles (user_id, role_id) "
                    "SELECT id, role_id FROM users WHERE role_id IS NOT NULL"))

        conn.commit()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sport-manager-secret-2024')

    # ── Base de datos ─────────────────────────────────────────────────────────
    # En producción (Render/Railway) define DATABASE_URL → PostgreSQL.
    # Sin esa variable, usa SQLite local para desarrollo.
    db_url = os.environ.get('DATABASE_URL', 'sqlite:///sportmanager.db')
    if db_url.startswith('postgres://'):
        # Render entrega 'postgres://' pero SQLAlchemy 2.x exige 'postgresql://'
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@sportmanager.com')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor inicia sesión para acceder.'
    login_manager.login_message_category = 'warning'

    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.athletes import athletes_bp
    from routes.billing import billing_bp
    from routes.assessments import assessments_bp
    from routes.users import users_bp
    from routes.config import config_bp
    from routes.school import school_bp
    from routes.platform import platform_bp
    from routes.bank import bank_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(athletes_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(assessments_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(school_bp)
    app.register_blueprint(platform_bp)
    app.register_blueprint(bank_bp)

    # Helper global de plantillas: resuelve URL de Cloudinary o ruta local
    from flask import url_for as _url_for

    @app.template_global()
    def media_url(value, folder='photos'):
        if not value:
            return ''
        if str(value).startswith('http'):
            return value
        return _url_for('static', filename=f'uploads/{folder}/{value}')

    with app.app_context():
        db.create_all()
        _migrate_columns(db)
        from models import seed_data
        seed_data()
        # Visible en logs de Render — para verificar qué BD está en uso
        dialect = db.engine.dialect.name
        if dialect == 'sqlite':
            print('⚠️  BASE DE DATOS: SQLite (EFÍMERA — los datos se '
                  'pierden al reiniciar). Configura DATABASE_URL para usar PostgreSQL.',
                  flush=True)
        else:
            print(f'✅ BASE DE DATOS: {dialect} (persistente)', flush=True)

    return app
