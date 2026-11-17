# Enterprise Agent Hub application scaffold

Imported from [Lee Admin Template](https://github.com/calvin-207/lee-admin-template), pinned at commit `205f65de635b2561f239417915faccbb3fcb89ee`.

The backend and frontend application source, CI workflows, Dependabot and PR template were copied. Existing Enterprise Agent Hub README/ROADMAP/docs remain untouched.

Generated Django collected static files (`backend/static`), local databases, Redis dumps, runtime media, logs and environment secrets were excluded.

Setup:
- `cd backend && cp config.py_template config.py && pip install -r requirements.txt && python manage.py migrate`
- Configure your own database, Redis, SECRET_KEY/DEBUG/ALLOWED_HOSTS (no secrets committed).
- `cd frontend && npm install && npm run dev`
- Start Django ASGI with `daphne main.asgi:application` for WebSocket support.

Follow-up project work: define the Agent Runtime, tools gateway, approvals and execution audit as new Django apps.
