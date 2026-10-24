from flask import Blueprint

bp = Blueprint("inspections", __name__, url_prefix="/inspections")

from . import routes  # noqa: E402,F401
