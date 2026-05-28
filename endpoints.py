import logging

from flask import Blueprint, jsonify, request

import db
from model_loader import predict

api = Blueprint("api", __name__)
log = logging.getLogger(__name__)

MAX_POINTS = 100


@api.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@api.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = data.get("user_name")
    password = data.get("password")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "'user_name' required"}), 400
    if not isinstance(password, str) or not password:
        return jsonify({"error": "'password' required"}), 400
    name = name.strip()
    try:
        user_id = db.register(name, password)
    except db.UserExists:
        return jsonify({"error": "user_name already taken"}), 409
    log.info("register: %s -> user_id=%d", name, user_id)
    return jsonify({"user_id": user_id, "user_name": name}), 201


@api.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    name = data.get("user_name")
    password = data.get("password")
    if not isinstance(name, str) or not isinstance(password, str):
        return jsonify({"error": "'user_name' and 'password' required"}), 400
    user = db.login(name, password)
    if user is None:
        return jsonify({"error": "invalid credentials"}), 401
    log.info("login: user_id=%d", user["user_id"])
    return jsonify(user), 200


@api.route("/getPrediction", methods=["POST"])
def get_prediction():
    data = request.get_json(silent=True) or {}
    points = data.get("points")

    if not isinstance(points, list):
        return jsonify({"error": "'points' must be a list"}), 400

    if len(points) > MAX_POINTS:
        return jsonify({"error": f"too many points (max {MAX_POINTS})"}), 413

    try:
        prediction = predict(points)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    log.info("getPrediction: %d points -> %s (%.3f)",
             len(points), prediction["label"], prediction["confidence"])
    return jsonify(prediction), 200


@api.errorhandler(404)
def not_found(_):
    return jsonify({"error": "not found"}), 404


@api.errorhandler(Exception)
def internal_error(e):
    log.exception("unhandled error: %s", e)
    return jsonify({"error": "internal server error"}), 500
