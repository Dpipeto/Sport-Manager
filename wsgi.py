"""Punto de entrada para producción (gunicorn en Render, Railway, etc.)"""
from app import create_app

app = create_app()
