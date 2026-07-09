"""
Almacenamiento de archivos: Cloudinary (producción) o disco local (desarrollo).

Si están definidas las variables de entorno de Cloudinary, los archivos
se suben a la nube y en la BD se guarda la URL completa (https://...).
Sin ellas, se guardan en static/uploads/ y en la BD va solo el filename.

Variables de entorno (definir en Render → Environment):
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET

Las plantillas usan el helper media_url() (registrado en app.py) que
resuelve ambos casos automáticamente.
"""
import os
import uuid

IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'svg'}
DOC_EXTS = {'pdf', 'jpg', 'jpeg', 'png'}


def cloudinary_enabled():
    return bool(os.environ.get('CLOUDINARY_CLOUD_NAME')
                and os.environ.get('CLOUDINARY_API_KEY')
                and os.environ.get('CLOUDINARY_API_SECRET'))


def _configure():
    import cloudinary
    cloudinary.config(
        cloud_name=os.environ['CLOUDINARY_CLOUD_NAME'],
        api_key=os.environ['CLOUDINARY_API_KEY'],
        api_secret=os.environ['CLOUDINARY_API_SECRET'],
        secure=True,
    )


def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def save_file(file, folder, allowed_exts=IMAGE_EXTS, prefix=''):
    """
    Guarda un FileStorage. Retorna:
      - URL https://... si Cloudinary está activo
      - filename local si no
      - None si el archivo es inválido
    """
    if not file or not file.filename:
        return None
    ext = _ext(file.filename)
    if ext not in allowed_exts:
        return None

    if cloudinary_enabled():
        try:
            import cloudinary.uploader
            _configure()
            public_id = f"sportmanager/{folder}/{prefix}{uuid.uuid4().hex[:12]}"
            # resource_type 'auto' soporta imágenes y PDFs
            result = cloudinary.uploader.upload(
                file, public_id=public_id, resource_type='auto',
                overwrite=True)
            return result['secure_url']
        except Exception:
            pass  # si la nube falla, cae al disco local

    # Local
    from flask import current_app
    fname = f"{prefix}{uuid.uuid4().hex[:12]}.{ext}"
    dest = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(dest, exist_ok=True)
    file.seek(0)
    file.save(os.path.join(dest, fname))
    return fname


def delete_file(value, folder):
    """Borra un archivo por su valor almacenado (URL o filename local)."""
    if not value:
        return
    if value.startswith('http'):
        if not cloudinary_enabled():
            return
        try:
            import cloudinary.uploader
            _configure()
            public_id = extract_public_id(value)
            if public_id:
                # Intentar como imagen y como raw (PDFs)
                for rt in ('image', 'raw'):
                    try:
                        cloudinary.uploader.destroy(public_id, resource_type=rt)
                    except Exception:
                        pass
        except Exception:
            pass
    else:
        from flask import current_app
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], folder, value)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def extract_public_id(url):
    """
    Extrae el public_id de una URL de Cloudinary.
    https://res.cloudinary.com/x/image/upload/v123/sportmanager/photos/abc.png
      → sportmanager/photos/abc
    """
    try:
        parts = url.split('/upload/')[1]
        # quitar versión v123456/
        segs = parts.split('/')
        if segs[0].startswith('v') and segs[0][1:].isdigit():
            segs = segs[1:]
        joined = '/'.join(segs)
        # quitar extensión
        return joined.rsplit('.', 1)[0]
    except Exception:
        return None


def fetch_bytes(value, folder):
    """
    Obtiene los bytes de un archivo (para incrustar en PDF/Excel).
    Funciona con URL de Cloudinary o archivo local.
    """
    if not value:
        return None
    if value.startswith('http'):
        try:
            import requests
            r = requests.get(value, timeout=10)
            if r.ok:
                return r.content
        except Exception:
            return None
        return None
    from flask import current_app
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], folder, value)
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return f.read()
    return None
