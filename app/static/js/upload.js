// Upload page: drag-and-drop, previews, geolocation and upload progress.
(function () {
  const form = document.getElementById("upload-form");
  const input = document.getElementById("media");
  const dropzone = document.getElementById("dropzone");
  const fileList = document.getElementById("file-list");
  const preview = document.getElementById("preview");
  const errorBox = document.getElementById("form-error");
  const progress = document.getElementById("progress");
  const bar = progress.querySelector(".progress-bar");
  const label = progress.querySelector(".progress-label");
  const submit = document.getElementById("submit");

  const formatSize = (bytes) =>
    bytes > 1048576 ? (bytes / 1048576).toFixed(1) + " MB" : Math.ceil(bytes / 1024) + " KB";

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = !message;
  }

  function render() {
    fileList.innerHTML = "";
    preview.querySelectorAll("[data-url]").forEach((el) => URL.revokeObjectURL(el.dataset.url));
    preview.innerHTML = "";
    for (const file of input.files) {
      const li = document.createElement("li");
      li.innerHTML = `<span></span><span class="muted">${formatSize(file.size)}</span>`;
      li.firstChild.textContent = file.name;
      fileList.appendChild(li);

      const url = URL.createObjectURL(file);
      let el;
      if (file.type.startsWith("video/")) {
        el = document.createElement("video");
        el.controls = true;
        el.muted = true;
      } else if (file.type.startsWith("image/")) {
        el = document.createElement("img");
        el.alt = file.name;
      } else {
        continue;
      }
      el.src = url;
      el.dataset.url = url;
      preview.appendChild(el);
    }
    showError("");
  }

  input.addEventListener("change", render);

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
    input.files = e.dataTransfer.files;
    render();
  });

  document.getElementById("geolocate").addEventListener("click", () => {
    if (!navigator.geolocation) return showError("This browser cannot share its location.");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        document.getElementById("lat").value = pos.coords.latitude.toFixed(6);
        document.getElementById("lon").value = pos.coords.longitude.toFixed(6);
      },
      (err) => showError("Could not get location: " + err.message),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!input.files.length) return showError("Select a video or at least one photo.");

    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (ev) => {
      if (!ev.lengthComputable) return;
      const pct = Math.round((ev.loaded / ev.total) * 100);
      bar.style.width = pct + "%";
      label.textContent = pct < 100 ? `Uploading… ${pct}%` : "Saving…";
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (_) {}
      if (xhr.status === 201 && data.url) {
        window.location = data.url;
        return;
      }
      showError(data.error || (xhr.status === 413 ? "Upload is too large." : "Upload failed."));
      reset();
    };
    xhr.onerror = () => {
      showError("Network error during upload.");
      reset();
    };

    progress.hidden = false;
    submit.disabled = true;
    xhr.send(new FormData(form));
  });

  function reset() {
    submit.disabled = false;
    progress.hidden = true;
    bar.style.width = "0";
  }
})();
