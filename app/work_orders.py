from flask import Blueprint, render_template

from .inspections import review

bp = Blueprint("work_orders", __name__, url_prefix="/work-orders")


@bp.route("/")
def list_view():
    return render_template("work_orders.html", orders=review.all_work_orders(), crew_labels=review.CREW_LABELS)
