import logging
import os

from flask import Flask
from flask_cors import CORS
from waitress import serve

from endpoints import api
from model_loader import load_model


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(api)
    load_model()
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    threads = int(os.environ.get("THREADS", "8"))

    logging.getLogger(__name__).info("Starting server on %s:%s", host, port)
    serve(create_app(), host=host, port=port, threads=threads)
