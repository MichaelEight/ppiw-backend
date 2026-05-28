import logging
import sqlite3

from flask import Blueprint, jsonify, request

import db
from model_loader import predict

api = Blueprint("api", __name__)
log = logging.getLogger(__name__)

MAX_POINTS = 100
MAX_LEADERBOARD_N = 100


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


@api.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id: int):
    user = db.get_user(user_id)
    if user is None:
        return jsonify({"error": "user not found"}), 404
    return jsonify(user), 200


@api.route("/users/<int:user_id>/stats", methods=["GET"])
def user_stats(user_id: int):
    user = db.get_user(user_id)
    if user is None:
        return jsonify({"error": "user not found"}), 404
    return jsonify({
        "user_id": user_id,
        "user_name": user["user_name"],
        "rank": db.user_rank(user_id),
        "total_playtime": db.total_playtime(user_id),
        "wins": db.count_wins(user_id),
    }), 200


@api.route("/games", methods=["POST"])
def create_game():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    points = data.get("points")
    length = data.get("length")
    won = data.get("won")
    lives_left = data.get("lives_left")

    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return jsonify({"error": "'user_id' (int) required"}), 400
    if not isinstance(points, int) or isinstance(points, bool):
        return jsonify({"error": "'points' (int) required"}), 400
    if not isinstance(length, int) or isinstance(length, bool):
        return jsonify({"error": "'length' (int seconds) required"}), 400
    if not isinstance(won, bool):
        return jsonify({"error": "'won' (bool) required"}), 400
    if lives_left is not None and (not isinstance(lives_left, int) or isinstance(lives_left, bool)):
        return jsonify({"error": "'lives_left' must be int or null"}), 400

    try:
        game_id = db.add_entry(user_id, points, length, won, lives_left)
    except sqlite3.IntegrityError:
        return jsonify({"error": "user_id does not exist"}), 404

    log.info("game: user_id=%d points=%d won=%s -> id=%d", user_id, points, won, game_id)
    return jsonify({
        "id": game_id,
        "user_id": user_id,
        "points": points,
        "length": length,
        "won": won,
        "lives_left": lives_left,
    }), 201


@api.route("/leaderboard", methods=["GET"])
def leaderboard():
    raw = request.args.get("n", "10")
    try:
        n = int(raw)
    except ValueError:
        return jsonify({"error": "'n' must be int"}), 400
    if n < 1 or n > MAX_LEADERBOARD_N:
        return jsonify({"error": f"'n' must be in 1..{MAX_LEADERBOARD_N}"}), 400
    return jsonify({"top": db.top_n(n)}), 200


@api.route("/stats/avg7d", methods=["GET"])
def stats_avg7d():
    return jsonify({"avg_points_last_7d": db.avg_points_last_7d()}), 200


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
