// Inspection detail page: live progress polling, before/after slider, frame gallery toggles.
(function () {
  // Live progress: poll until processing finishes, then reload to show results.
  const live = document.getElementById("live");
  if (live) {
    const message = document.getElementById("live-message");
    const bar = document.getElementById("live-bar");
    const poll = async () => {
      try {
        const res = await fetch(live.dataset.statusUrl, { headers: { Accept: "application/json" } });
        const data = await res.json();
        if (!data.running) return window.location.reload();
        if (data.progress) {
          message.textContent = data.progress.message;
          bar.style.width = Math.round(data.progress.fraction * 100) + "%";
        }
      } catch (_) { /* keep polling */ }
      setTimeout(poll, 1000);
    };
    setTimeout(poll, 800);
  }

  // Before/after comparison slider.
  document.querySelectorAll(".compare").forEach((box) => {
    const range = box.querySelector("input[type=range]");
    range.addEventListener("input", () => box.style.setProperty("--pos", range.value + "%"));
  });

  // Frame gallery: keyframes/all and enhanced/original toggles.
  const grid = document.getElementById("frame-grid");
  if (!grid) return;
  const frames = [...grid.querySelectorAll(".frame")];

  document.querySelectorAll("[data-filter]").forEach((btn) =>
    btn.addEventListener("click", () => {
      btn.parentElement.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === btn));
      const keyOnly = btn.dataset.filter === "key";
      frames.forEach((f) => (f.hidden = keyOnly && !f.classList.contains("is-key")));
    })
  );

  document.querySelectorAll("[data-version]").forEach((btn) =>
    btn.addEventListener("click", () => {
      btn.parentElement.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === btn));
      grid.querySelectorAll("img").forEach((img) => {
        img.src = img.dataset[btn.dataset.version];
        img.parentElement.href = img.src;
      });
    })
  );
})();
