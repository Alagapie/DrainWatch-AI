// Upload page: drag-and-drop, removable file tiles, geolocation and upload progress.
(function () {
  const form = document.getElementById("upload-form");
  const input = document.getElementById("media");
  const dropzone = document.getElementById("dropzone");
  const selection = document.getElementById("selection");
  const summary = document.getElementById("selection-summary");
  const grid = document.getElementById("file-grid");
  const errorBox = document.getElementById("form-error");
  const submit = document.getElementById("submit");
  const submitText = submit.querySelector(".btn-text");
  const submitFill = submit.querySelector(".btn-fill");
  const geoStatus = document.getElementById("geo-status");

  const icon = (name) => `<svg class="icon"><use href="#i-${name}"/></svg>`;
  const formatSize = (bytes) =>
    bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1024)) + " KB";

  let objectUrls = [];

  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
    if (message) errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function setFiles(files) {
    const dt = new DataTransfer();
    [...files].forEach((f) => dt.items.add(f));
    input.files = dt.files;
    render();
  }

  function render() {
    objectUrls.forEach(URL.revokeObjectURL);
    objectUrls = [];
    grid.innerHTML = "";

    const files = [...input.files];
    selection.hidden = files.length === 0;
    dropzone.classList.toggle("compact", files.length > 0);
    dropzone.querySelector("strong").textContent = files.length
      ? "Add or replace files"
      : "Drag & drop your video or photos";
    if (!files.length) return;

    const videos = files.filter((f) => f.type.startsWith("video/"));
    const total = files.reduce((sum, f) => sum + f.size, 0);
    summary.textContent = videos.length
      ? `${videos.length} video · ${formatSize(total)}`
      : `${files.length} photo${files.length > 1 ? "s" : ""} · ${formatSize(total)}`;
    grid.classList.toggle("has-video", videos.length > 0);

    files.forEach((file, i) => {
      const url = URL.createObjectURL(file);
      objectUrls.push(url);
      const tile = document.createElement("figure");
      tile.className = "file-tile";
      tile.style.margin = "0";
      const media = file.type.startsWith("video/")
        ? Object.assign(document.createElement("video"), { src: url, controls: true, muted: true })
        : Object.assign(document.createElement("img"), { src: url, alt: file.name });
      const caption = document.createElement("figcaption");
      caption.innerHTML = `<span></span><span class="muted">${formatSize(file.size)}</span>`;
      caption.firstChild.textContent = file.name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "file-remove";
      remove.title = "Remove";
      remove.innerHTML = icon("x");
      remove.addEventListener("click", () => setFiles(files.filter((_, j) => j !== i)));
      tile.append(media, caption, remove);
      grid.appendChild(tile);
    });
    showError("");
  }

  input.addEventListener("change", render);
  document.getElementById("clear-files").addEventListener("click", () => setFiles([]));

  ["dragenter", "dragover"].forEach((type) =>
    dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((type) =>
    dropzone.addEventListener(type, () => dropzone.classList.remove("dragover"))
  );
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    setFiles(e.dataTransfer.files);
  });

  document.getElementById("geolocate").addEventListener("click", () => {
    if (!navigator.geolocation) return showError("This browser can't share its location.");
    geoStatus.className = "geo-status muted";
    geoStatus.textContent = "Finding you…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        document.getElementById("lat").value = pos.coords.latitude.toFixed(6);
        document.getElementById("lon").value = pos.coords.longitude.toFixed(6);
        geoStatus.className = "geo-status ok";
        geoStatus.innerHTML = `${icon("check")} Location added (±${Math.round(pos.coords.accuracy)} m)`;
      },
      (err) => {
        geoStatus.className = "geo-status muted";
        geoStatus.textContent = "Couldn't get your location. You can type it instead.";
        console.warn(err);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!input.files.length) return showError("Please add a video or at least one photo first.");

    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (ev) => {
      if (!ev.lengthComputable) return;
      const pct = Math.round((ev.loaded / ev.total) * 100);
      submitFill.style.width = pct + "%";
      submitText.textContent = pct < 100 ? `Uploading… ${pct}%` : "Saving your inspection…";
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (_) {}
      if (xhr.status === 201 && data.url) {
        submitText.textContent = "Done! Opening inspection…";
        window.location = data.url;
        return;
      }
      showError(data.error || (xhr.status === 413 ? "That upload is too large." : "Upload failed. Please try again."));
      reset();
    };
    xhr.onerror = () => {
      showError("Network problem during upload. Please try again.");
      reset();
    };

    submit.disabled = true;
    submitText.textContent = "Uploading… 0%";
    xhr.send(new FormData(form));
  });

  function reset() {
    submit.disabled = false;
    submitFill.style.width = "0";
    submitText.textContent = "Submit inspection";
  }
})();
