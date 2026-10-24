import os

from flask import Flask, redirect, render_template, url_for

from .config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    os.makedirs(app.config["INSPECTIONS_DIR"], exist_ok=True)

    from .inspections import bp as inspections_bp
    app.register_blueprint(inspections_bp)

    @app.route("/")
    def index():
        return redirect(url_for("inspections.new"))

    @app.errorhandler(404)
    def not_found(_):
        return render_template("errors/error.html", code=404, message="Page not found."), 404

    @app.errorhandler(413)
    def too_large(_):
        limit = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return render_template("errors/error.html", code=413,
                               message=f"Upload is too large (limit {limit} MB)."), 413

    return app
