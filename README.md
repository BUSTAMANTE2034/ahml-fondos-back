# AHML Fondos – Backend (Flask)

Backend en **Flask** para gestionar usuarios, fondos documentales, expedientes, préstamos, tipologías y todo el flujo de archivo del sistema AHML.

Incluye:

- Autenticación con sesión (flask-login)
- Gestión de usuarios con roles (`admin`, `manager`, `archivist`, `visitor`)
- Creación y recuperación de contraseñas vía correo
- Modelos con timestamps controlados por la base de datos
- API REST con **flask-restx**
- Migraciones con **Flask-Migrate / Alembic**
- MySQL como base de datos

---

## 1. Requisitos

- Python 3.9+ (tú lo estás usando con 3.9)
- MySQL 5.7+ / 8.x
- (opcional) virtualenv

---

## 2. Clonar e instalar

```bash
git clone <tu-repo>
cd ahml-fondos-back

# crear entorno
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
# source venv/bin/activate

# instalar dependencias
pip install -r requirements.txt
```

---

## 3. Variables de entorno (`.env`)

En la raíz ya tienes un `.env`. Si no, crea uno así:

```env
FLASK_ENV=development
DEBUG=true
SECRET_KEY=super-secret-key

# Base de datos
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=tu_password
DB_NAME=ahml-fondos

# Admin inicial (lo crea al levantar la app si no existe)
ADMIN_EMAIL=administrator@yopmail.com
ADMIN_PASSWORD=Admin123$
ADMIN_FIRST_NAME=Admin
ADMIN_LAST_NAME=System

# Correo
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=465
MAIL_USERNAME=tu_correo@gmail.com
MAIL_PASSWORD=tu_password_app
MAIL_DEFAULT_SENDER=tu_correo@gmail.com
MAIL_DEFAULT_NAME=Sistema AHML
```

El archivo `app/config.py` ya lee todo eso y además configura el pool de SQLAlchemy para que no se caiga la conexión:

```python
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_pre_ping": True,
    "pool_recycle": 28000,
    "connect_args": {
        "connect_timeout": 10,
        "read_timeout": 10,
        "write_timeout": 10,
    },
}
```

---

## 4. Crear BD

En MySQL crea la base:

```sql
CREATE DATABASE `ahml-fondos` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

(o el nombre que pusiste en `DB_NAME`).

---

## 5. Migraciones

Con el entorno activado:

```bash
flask db init        # solo la primera vez
flask db migrate -m "create schema"
flask db upgrade
```

⚠️ Si al hacer `flask db migrate` te tira que la tabla `user` no existe es porque tu app, al arrancar, intenta crear el superadmin. Lo más fácil es:

1. comentar temporalmente la llamada a `create_superadmin()` en `app/__init__.py`
2. correr las migraciones
3. descomentarla otra vez
4. levantar el server para que la cree

---

## 6. Ejecutar la app

```bash
flask run
# desactivar entorno
deactivate

```

Verás algo como:

```text
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
```

Cuando arranca, dentro del `app/__init__.py`:

- carga la config
- inicializa `db`, `bcrypt`, `login_manager`
- registra blueprints (`app/api`)
- crea las tablas (`db.create_all()`) si hace falta
- crea el superadmin si no existe

---

## 7. Estructura del proyecto

```text
ahml-fondos-back/
├── app/
│   ├── api/               # endpoints (users, auth, etc.)
│   ├── models/            # todos los modelos: user, fund, section, series, ...
│   ├── schemas/           # marshmallow schemas
│   ├── services/          # email_service, etc.
│   ├── utils/             # seguridad, helpers
│   ├── __init__.py        # create_app()
│   ├── cli.py             # comandos flask propios
│   ├── config.py          # configuración central (env, db, mail)
│   └── extensions.py      # db, bcrypt, login_manager
├── migrations/            # alembic
├── main.py                # entrypoint opcional
├── requirements.txt
├── .env
└── README.md
```

---

## 8. Autenticación

Autenticación es **con sesión/cookie** usando `flask-login`, no con JWT.

### 8.1 Login

`POST /auth/login`

```json
{
  "email": "administrator@yopmail.com",
  "password": "Admin123$",
  "remember_me": true
}
```

Responde con el usuario y **el servidor te manda la cookie de sesión**.  
Para probar en Bruno/Postman, copia esa cookie y mándala en el header:

```http
Cookie: session=<valor-de-la-cookie>
```

### 8.2 Yo mismo

`GET /auth/me`

Devuelve el usuario autenticado.

---

## 9. Endpoints principales

### 9.1 Usuarios

- `GET /users` – lista con filtros y paginación
- `POST /users` – crea usuario con contraseña temporal y manda correo
- `GET /users/<id>` – detalle
- `PUT /users/<id>` – actualiza datos y **si viene `password`** la actualiza usando SQL directo y manda correo
- `DELETE /users/<id>` – soft delete (`deleted_at` + `is_active=False`)

Todos protegidos con `@login_required` y `@role_required(...)`.

### 9.2 Auth extra

- `POST /auth/change-password` – el propio usuario cambia su contraseña
- `POST /auth/recover-password` – **solo admin**: genera temporal para un usuario y se la manda por mail

---

## 10. Pruebas rápidas con Bruno/Postman

1. Hacer `POST /auth/login`
2. Copiar la cookie `session=...`
3. En la colección, agregar header:

   ```text
   Cookie: session=<lo-que-te-dio-el-login>
   ```

4. Ya puedes llamar a `/users`, `/auth/recover-password`, etc.

Ejemplo body de recuperación:

```json
POST /auth/recover-password
{
  "user_id": 5
}
```

---

## 11. Correo

El servicio está en `app/services/email_service.py` y tiene:

- `send_temp_password_email(...)` – cuando se crea cuenta
- `send_password_updated_email(...)` – cuando un admin cambia password
- `send_recovered_password_email(...)` – cuando un admin la recupera

Usa SMTP SSL (`smtplib.SMTP_SSL`), así que tu cuenta debe aceptar app password o autenticación que soporte eso.

---

## 12. Notas sobre la BD y timestamps

Actualizamos los modelos para que las fechas las ponga **MySQL**:

```python
created_at = db.Column(
    db.DateTime,
    server_default=db.func.now(),
    nullable=False,
)
updated_at = db.Column(
    db.DateTime,
    server_default=db.func.now(),
    server_onupdate=db.func.now(),
    nullable=False,
)
deleted_at = db.Column(db.DateTime, nullable=True)
```

Y en los endpoints, cuando hacemos soft delete:

```python
user.deleted_at = db.func.now()
```

para que también venga del servidor.

---

## 13. Comandos útiles

```bash
# activar entorno
venv\Scripts\activate

# desactivar entorno
deactivate

# correr servidor
flask run

# generar migración
flask db migrate -m "algo"

# aplicar migración
flask db upgrade
```

---

## 14. Troubleshooting rápido

- **“The method is not allowed for the requested URL.”** → revisa que estés usando el método correcto (`POST` para `/auth/recover-password`).
- **No pasa el login en Bruno** → falta la cookie `session=...`
- **Timeout en UPDATE de password** → ya lo solucionaste cambiando a `mysqlconnector` o ejecutando SQL directo.
- **No llegan los correos** → revisa credenciales en `.env` y que el puerto sea 465 si usas SSL.
