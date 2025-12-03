# app/services/email_service.py

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app


def send_email(to_email: str, to_name: str, subject: str, html_body: str):
    mail_server = current_app.config.get("MAIL_SERVER", "smtp.gmail.com")
    mail_port = current_app.config.get("MAIL_PORT", 465)
    mail_user = current_app.config.get("MAIL_USERNAME")
    mail_password = current_app.config.get("MAIL_PASSWORD")
    mail_from = current_app.config.get("MAIL_DEFAULT_SENDER", mail_user)
    mail_from_name = current_app.config.get("MAIL_DEFAULT_NAME", "Sistema AHML")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{mail_from_name} <{mail_from}>"
    msg["To"] = f"{to_name} <{to_email}>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(mail_server, mail_port, context=context) as server:
        server.login(mail_user, mail_password)
        server.sendmail(mail_from, to_email, msg.as_string())


def send_temp_password_email(user, temp_password: str):
    subject = "Tu cuenta en AHML"
    name = user.first_name or user.email
    html = f"""
    <p>Hola {name},</p>
    <p>Se ha creado una cuenta para ti en el sistema AHML.</p>
    <p><b>Número de empleado:</b> {user.employee_id}</p>
    <p><b>Correo:</b> {user.email}</p>
    <p><b>Contraseña temporal:</b> {temp_password}</p>
    <p>Por seguridad, inicia sesión y cambia tu contraseña en tu primer acceso.</p>
    <p>--<br>Sistema AHML</p>
    """
    send_email(user.email, name, subject, html)


def send_password_updated_email(user, new_password: str):
    """Correo cuando un admin actualiza la contraseña de un usuario existente."""
    subject = "Tu contraseña ha sido actualizada - AHML"
    name = user.first_name or user.email
    html = f"""
    <p>Hola {name},</p>
    <p>Un administrador actualizó la contraseña de tu cuenta.</p>
    <p><b>Número de empleado:</b> {user.employee_id}</p>
    <p><b>Correo:</b> {user.email}</p>
    <p><b>Nueva contraseña:</b> {new_password}</p>
    <p>Por seguridad, inicia sesión y cambia la contraseña cuanto antes.</p>
    <p>--<br>Sistema AHML</p>
    """
    send_email(user.email, name, subject, html)

def send_recovered_password_email(user, temp_password: str):
    subject = "Restablecimiento de contraseña - AHML"
    name = user.first_name or user.email
    html = f"""
    <p>Hola {name},</p>
    <p>Un administrador restableció la contraseña de tu cuenta.</p>
    <p><b>Número de empleado:</b> {user.employee_id}</p>
    <p><b>Correo:</b> {user.email}</p>
    <p><b>Nueva contraseña temporal:</b> {temp_password}</p>
    <p>Por seguridad, inicia sesión y cambia la contraseña de inmediato.</p>
    <p>--<br>Sistema AHML</p>
    """
    send_email(user.email, name, subject, html)