import logging

from flask import Blueprint, jsonify, request

api = Blueprint("api", __name__)
log = logging.getLogger(__name__)

MAX_POINTS = 100


@api.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@api.route("/getPrediction", methods=["POST"])
def get_prediction():
    data = request.get_json(silent=True) or {}
    points = data.get("points")

    if not isinstance(points, list):
        return jsonify({"error": "'points' must be a list"}), 400

    if len(points) > MAX_POINTS:
        return jsonify({"error": f"too many points (max {MAX_POINTS})"}), 413
    
    # TODO: Call model to receive prediction
    # prediction = model.predict(points)

    log.info("getPrediction: received %d points", len(points))
    return jsonify({"message": f"Received {len(points)} points"}), 200


@api.errorhandler(404)
def not_found(_):
    return jsonify({"error": "not found"}), 404


@api.errorhandler(Exception)
def internal_error(e):
    log.exception("unhandled error: %s", e)
    return jsonify({"error": "internal server error"}), 500
