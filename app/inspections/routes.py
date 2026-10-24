from flask import abort, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

from . import bp, storage


def _wants_json() -> bool:
    return request.accept_mimetypes.best == "application/json"


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "GET":
        return render_template("inspections/new.html")

    try:
        record = storage.create_inspection(request.files.getlist("media"), request.form)
    except storage.UploadError as e:
        if _wants_json():
            return jsonify(error=str(e)), 400
        flash(str(e), "error")
        return render_template("inspections/new.html", form=request.form), 400

    url = url_for("inspections.detail", inspection_id=record["inspection_id"])
    if _wants_json():
        return jsonify(inspection_id=record["inspection_id"], url=url), 201
    return redirect(url)


@bp.route("/")
def list_view():
    return render_template("inspections/list.html", inspections=storage.list_all())


@bp.route("/<inspection_id>")
def detail(inspection_id):
    record = storage.load(inspection_id)
    if record is None:
        abort(404)
    return render_template("inspections/detail.html", insp=record, stages=storage.STAGES)


@bp.route("/<inspection_id>/media/<path:filename>")
def media(inspection_id, filename):
    if storage.load(inspection_id) is None:
        abort(404)
    return send_from_directory(storage.media_dir(inspection_id), filename)
