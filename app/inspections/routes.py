from flask import (abort, current_app, flash, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)

from . import bp, pipeline, storage

# Sub-folders of an inspection that may be served to the browser.
SERVABLE = ("media/", "preprocess/", "analysis/", "vlm/", "agent/")


def _wants_json() -> bool:
    return request.accept_mimetypes.best == "application/json"


def _load_or_404(inspection_id: str) -> dict:
    record = storage.load(inspection_id)
    if record is None:
        abort(404)
    return record


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

    pipeline.start(current_app._get_current_object(), record["inspection_id"])
    url = url_for("inspections.detail", inspection_id=record["inspection_id"])
    if _wants_json():
        return jsonify(inspection_id=record["inspection_id"], url=url), 201
    return redirect(url)


@bp.route("/")
def list_view():
    return render_template("inspections/list.html", inspections=storage.list_all())


@bp.route("/<inspection_id>")
def detail(inspection_id):
    record = _load_or_404(inspection_id)
    return render_template(
        "inspections/detail.html",
        insp=record,
        stages=storage.STAGES,
        running=pipeline.is_running(inspection_id),
        progress=pipeline.progress(inspection_id),
        pre=storage.load_result(inspection_id, "preprocess"),
        ana=storage.load_result(inspection_id, "analysis"),
        vlm=storage.load_result(inspection_id, "vlm"),
        agent=storage.load_result(inspection_id, "agent"),
    )


@bp.route("/<inspection_id>/process", methods=["POST"])
def process(inspection_id):
    _load_or_404(inspection_id)
    if not pipeline.start(current_app._get_current_object(), inspection_id):
        flash("This inspection is already being processed.", "info")
    return redirect(url_for("inspections.detail", inspection_id=inspection_id))


@bp.route("/<inspection_id>/status")
def status(inspection_id):
    record = _load_or_404(inspection_id)
    return jsonify(status=record["status"], errors=record["errors"],
                   running=pipeline.is_running(inspection_id),
                   progress=pipeline.progress(inspection_id))


@bp.route("/<inspection_id>/media/<path:filename>")
def media(inspection_id, filename):
    _load_or_404(inspection_id)
    return send_from_directory(storage.media_dir(inspection_id), filename)


@bp.route("/<inspection_id>/files/<path:filename>")
def files(inspection_id, filename):
    _load_or_404(inspection_id)
    if not filename.startswith(SERVABLE):
        abort(404)
    return send_from_directory(storage.inspection_dir(inspection_id), filename)
