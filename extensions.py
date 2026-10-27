from flask_socketio import SocketIO

import os

_PORT = int(os.environ.get("FLASK_PORT", 7788))
# solo la página del propio panel puede abrir el socket (antes "*": cualquier web
# podía escuchar el log de eventos)
socketio = SocketIO(cors_allowed_origins=[f"http://127.0.0.1:{_PORT}", f"http://localhost:{_PORT}"],
                    async_mode="threading")
