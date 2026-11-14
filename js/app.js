/* Orbital Witness demo: loads data/index.json and data/<run>/case.json. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmt(v, d) {
    if (v == null || isNaN(v)) return "—";
    var a = Math.abs(v);
    if (d == null) d = a >= 10 ? 2 : a >= 1 ? 3 : 4;
    return (v > 0 ? "+" : "") + Number(v).toFixed(d);
  }
  function plain(v, d) { return v == null ? "—" : Number(v).toFixed(d == null ? 4 : d); }
  function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : null; }

  var LABELS = {
    supported: { cls: "supported", badge: "Supported", run: "本当の主張 / True claim" },
    contradicted: { cls: "refuted", badge: "Contradicted", run: "誤情報 / False claim" },
    refuted: { cls: "refuted", badge: "Refuted", run: "誤情報 / False claim" },
    inconclusive: { cls: "inconclusive", badge: "Inconclusive", run: "判定保留 / Inconclusive" }
  };
  function lab(l) { return LABELS[l] || { cls: "inconclusive", badge: l || "unknown", run: l || "run" }; }
  function setBadge(el, label) {
    var L = lab(label);
    el.className = "badge " + L.cls;
    el.textContent = L.badge;
  }

  var state = { runs: [], current: null, mode: "slider", cache: {} };

  function load() {
    fetch("data/index.json", { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("index.json " + r.status); return r.json(); })
      .then(function (idx) {
        state.runs = (idx && idx.runs) || [];
        if (!state.runs.length) throw new Error("no runs exported yet");
        buildSelectors();
        var q = new URLSearchParams(location.search).get("run");
        var first = state.runs.some(function (r) { return r.run_id === q; }) ? q : state.runs[0].run_id;
        select(first);
      })
      .catch(showError);
  }

  function showError(e) {
    var el = $("case-error");
    el.hidden = false;
    el.textContent = "Could not load run data: " + (e && e.message ? e.message : e) + ". Serve this folder over HTTP (e.g. python3 -m http.server).";
    $("hc-claim").textContent = "Run data unavailable.";
  }

  function buildSelectors() {
    if (state.runs.length < 2) return;
    var sel = $("run-select");
    sel.innerHTML = state.runs.map(function (r) {
      return '<option value="' + esc(r.run_id) + '">' + esc(lab(r.label).run) + " · " + esc(r.run_id) + "</option>";
    }).join("");
    sel.addEventListener("change", function () { select(sel.value); });
    $("run-select-wrap").hidden = false;

    var seg = document.createElement("div");
    seg.className = "seg hc-runs";
    seg.id = "hc-runs";
    seg.setAttribute("role", "tablist");
    seg.innerHTML = state.runs.map(function (r) {
      return '<button type="button" data-run="' + esc(r.run_id) + '">' + esc(lab(r.label).run) + "</button>";
    }).join("");
    seg.addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-run]");
      if (b) select(b.getAttribute("data-run"));
    });
    var card = $("hero-card");
    card.insertBefore(seg, card.children[1]);
  }

  function select(runId) {
    state.current = runId;
    if ($("run-select")) $("run-select").value = runId;
    var btns = document.querySelectorAll("#hc-runs button");
    for (var i = 0; i < btns.length; i++) btns[i].classList.toggle("on", btns[i].getAttribute("data-run") === runId);
    try {
      var u = new URL(location.href);
      u.searchParams.set("run", runId);
      history.replaceState(null, "", u.pathname + u.search + u.hash);
    } catch (e) { /* ignore */ }

    if (state.cache[runId]) return render(state.cache[runId]);
    fetch("data/" + encodeURIComponent(runId) + "/case.json", { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("case.json " + r.status); return r.json(); })
      .then(function (c) { state.cache[runId] = c; if (state.current === runId) render(c); })
      .catch(showError);
  }

  function render(c) {
    $("case-error").hidden = true;
    var v = c.verdict || {}, pre = c.prereg || {}, hyp = pre.hypothesis || {};
    var sha = pre.sha256 || v.prereg_sha256 || "";

    // hero card
    $("hc-run").textContent = c.run_id;
    $("hc-claim").textContent = c.claim;
    setBadge($("hc-badge"), v.label);
    $("hc-posterior").textContent = v.posterior != null ? Number(v.posterior).toFixed(3) : "—";
    $("hc-posterior").style.color = colorFor(v.posterior);
    $("hc-sha").textContent = sha.slice(0, 16) + "…";
    requestAnimationFrame(function () { $("hc-bar-fill").style.width = ((v.posterior || 0) * 100).toFixed(1) + "%"; });

    // claim panel
    $("c-run").textContent = c.run_id;
    setBadge($("c-badge"), v.label);
    $("c-claim").textContent = c.claim;
    var aoi = hyp.aoi || {}, tf = hyp.timeframe || {};
    var chips = [
      ["event", hyp.event_type],
      ["date", tf.event_date],
      ["aoi", aoi.place],
      ["center", aoi.lat != null ? Number(aoi.lat).toFixed(4) + ", " + Number(aoi.lon).toFixed(4) : null],
      ["box", aoi.half_km != null ? (aoi.half_km * 2) + " km square" : null],
      ["before", (tf.before || []).join(" → ")],
      ["after", (tf.after || []).join(" → ")],
      ["control", tf.baseline_years_back ? "same season −" + tf.baseline_years_back + " yr" : null],
      ["prior", hyp.prior_p],
      ["planner", pre.planner_model]
    ];
    $("c-meta").innerHTML = chips.filter(function (x) { return x[1] != null && x[1] !== ""; })
      .map(function (x) { return '<span class="chip"><b>' + esc(x[0]) + "</b>" + esc(x[1]) + "</span>"; }).join("");
    $("c-sealed-at").textContent = pre.sealed_at ? "at " + pre.sealed_at.replace("T", " ").replace(/\.\d+Z$/, "Z") : "";
    $("c-sha").textContent = sha;
    $("c-sha").title = sha;
    $("c-copy").onclick = function () {
      if (navigator.clipboard) navigator.clipboard.writeText(sha).then(function () {
        $("c-copy").textContent = "copied"; setTimeout(function () { $("c-copy").textContent = "copy"; }, 1400);
      });
    };

    renderImages(c);
    renderGauge(v);
    renderLedger(c);
    renderExplain(c);
    renderAlts(hyp.alternatives || []);
    renderPlanLog(c.plan_log || []);
    renderProbes(c.results || []);
    renderNews(c);
  }

  function colorFor(p) {
    if (p == null) return "#8a9bb4";
    return p >= 0.8 ? "#3ddc97" : p <= 0.2 ? "#ff5c6c" : "#ffb547";
  }

  /* ---------- imagery ---------- */
  function findImages(c) {
    var out = {};
    (c.results || []).forEach(function (r) {
      var a = r.artifacts || {};
      Object.keys(a).forEach(function (k) {
        var key = k.replace(/\.png$/, "");
        if (key === "before" || key === "after") out[key] = a[k];
        else if (/^change/.test(key)) out.change = a[k];
      });
    });
    return out;
  }

  function renderImages(c) {
    var imgs = findImages(c), stage = $("img-stage");
    var tf = ((c.prereg || {}).hypothesis || {}).timeframe || {};
    var mode = state.mode;
    var segBtns = document.querySelectorAll("#img-mode button");
    for (var i = 0; i < segBtns.length; i++) segBtns[i].classList.toggle("on", segBtns[i].getAttribute("data-mode") === mode);

    if (!imgs.before || !imgs.after) {
      stage.innerHTML = '<div class="noimg">No optical imagery for this run.</div>';
      $("img-note").textContent = "";
      return;
    }
    var bl = "BEFORE " + ((tf.before || [])[0] || ""), al = "AFTER " + ((tf.after || [])[0] || "");
    if (mode === "side") {
      stage.innerHTML = '<div class="side"><figure><img src="' + esc(imgs.before) + '" alt="Sentinel-2 before the event" loading="lazy"><figcaption>' + esc(bl) + '</figcaption></figure>' +
        '<figure><img src="' + esc(imgs.after) + '" alt="Sentinel-2 after the event" loading="lazy"><figcaption>' + esc(al) + "</figcaption></figure></div>";
    } else if (mode === "change" && imgs.change) {
      stage.innerHTML = '<div class="single"><figure><img src="' + esc(imgs.change) + '" alt="Change map of new water pixels" loading="lazy"><figcaption>NEW WATER (CHANGE MAP)</figcaption></figure></div>';
    } else {
      stage.innerHTML = '<div class="compare" id="cmp"><img src="' + esc(imgs.after) + '" alt="Sentinel-2 after the event"><img class="over" src="' + esc(imgs.before) + '" alt="Sentinel-2 before the event">' +
        '<span class="img-label l">' + esc(bl) + '</span><span class="img-label r">' + esc(al) + '</span><div class="handle"></div>' +
        '<input type="range" min="0" max="100" value="50" aria-label="Reveal before / after"></div>';
      var cmp = $("cmp"), rng = cmp.querySelector("input"), over = cmp.querySelector(".over"), hd = cmp.querySelector(".handle");
      var upd = function () { over.style.clipPath = "inset(0 " + (100 - rng.value) + "% 0 0)"; hd.style.left = rng.value + "%"; };
      rng.addEventListener("input", upd); upd();
    }
    $("img-note").textContent = mode === "change"
      ? "Pixels whose NDWI crossed into water after the event, relative to before. The ledger uses the difference against the same season one year earlier."
      : "Sentinel-2 L2A true colour around the area of interest. Drag the slider to compare before and after.";
  }

  document.getElementById("img-mode").addEventListener("click", function (ev) {
    var b = ev.target.closest("button[data-mode]");
    if (!b) return;
    state.mode = b.getAttribute("data-mode");
    if (state.current && state.cache[state.current]) renderImages(state.cache[state.current]);
  });

  /* ---------- gauge + formula ---------- */
  function renderGauge(v) {
    var p = v.posterior == null ? 0.5 : v.posterior;
    var cx = 160, cy = 160, r = 120;
    function pt(t, rr) { var a = Math.PI * (1 - t); return [cx + rr * Math.cos(a), cy - rr * Math.sin(a)]; }
    var s = pt(0, r), e = pt(1, r), n = pt(p, r - 18), pr = pt(v.prior == null ? 0.5 : v.prior, r + 14);
    var ticks = "";
    [0, 0.25, 0.5, 0.75, 1].forEach(function (t) {
      var a = pt(t, r + 6), b = pt(t, r + 14), lb = pt(t, r + 28);
      ticks += '<line x1="' + a[0] + '" y1="' + a[1] + '" x2="' + b[0] + '" y2="' + b[1] + '" stroke="#8a9bb4" stroke-width="1"/>';
      ticks += '<text x="' + lb[0] + '" y="' + (lb[1] + 4) + '" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="10" fill="#8a9bb4">' + t + "</text>";
    });
    var col = colorFor(p);
    $("gauge").innerHTML =
      '<svg viewBox="0 0 320 200" role="img" aria-label="Posterior probability ' + p + '">' +
      '<defs><linearGradient id="gg" x1="0" x2="1"><stop offset="0" stop-color="#ff5c6c"/><stop offset="0.5" stop-color="#ffb547"/><stop offset="1" stop-color="#3ddc97"/></linearGradient></defs>' +
      '<path d="M' + s[0] + " " + s[1] + " A" + r + " " + r + " 0 0 1 " + e[0] + " " + e[1] + '" fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="18" stroke-linecap="round"/>' +
      '<path d="M' + s[0] + " " + s[1] + " A" + r + " " + r + " 0 0 1 " + e[0] + " " + e[1] + '" fill="none" stroke="url(#gg)" stroke-width="18" stroke-linecap="round" opacity="0.85"/>' +
      ticks +
      '<circle cx="' + pr[0] + '" cy="' + pr[1] + '" r="3" fill="#8a9bb4"/>' +
      '<line x1="' + cx + '" y1="' + cy + '" x2="' + n[0] + '" y2="' + n[1] + '" stroke="#fff" stroke-width="3" stroke-linecap="round"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="7" fill="#fff"/>' +
      '<text x="' + cx + '" y="' + (cy + 34) + '" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="26" font-weight="700" fill="' + col + '">' + Number(p).toFixed(3) + "</text>" +
      "</svg>";

    var prior = v.prior == null ? 0.5 : v.prior;
    var L0 = Math.log(prior / (1 - prior)), L = L0, rows = "";
    rows += '<div class="row"><span>prior log-odds  ln(' + prior + "/" + (1 - prior).toFixed(2) + ")</span><span>" + fmt(L0, 3) + "</span></div>";
    (v.entries || []).forEach(function (e) {
      var x = e.log_lr || 0; L += x;
      rows += '<div class="row"><span>+ ' + esc(e.signature_id) + " (" + esc(e.outcome) + ')</span><span class="' + (x > 0 ? "pos" : x < 0 ? "neg" : "zero") + '">' + fmt(x, 3) + "</span></div>";
    });
    var post = 1 / (1 + Math.exp(-L));
    rows += '<div class="row sum"><span>posterior log-odds</span><span>' + fmt(L, 3) + "</span></div>";
    rows += '<div class="row"><span>P = 1 / (1 + e<sup>−L</sup>)</span><span style="color:' + col + '">' + post.toFixed(4) + "</span></div>";
    $("formula").innerHTML = rows;
  }

  /* ---------- ledger ---------- */
  function sigMap(c) {
    var m = {};
    ((((c.prereg || {}).hypothesis || {}).signatures) || []).forEach(function (s) { m[s.id] = s; });
    return m;
  }

  function ciBar(meas, th) {
    if (!meas || meas.lo == null) return "";
    var lo = Math.min(meas.lo, th == null ? meas.lo : th, 0), hi = Math.max(meas.hi, th == null ? meas.hi : th, 0);
    var pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
    var X = function (x) { return ((x - lo) / (hi - lo) * 100).toFixed(2) + "%"; };
    var w = ((meas.hi - meas.lo) / (hi - lo) * 100).toFixed(2) + "%";
    return '<div class="cibar" title="95% CI with threshold (dashed)"><span class="rng" style="left:' + X(meas.lo) + ";width:" + w + '"></span>' +
      '<span class="pt" style="left:' + X(meas.value) + '"></span>' + (th != null ? '<span class="th" style="left:' + X(th) + '"></span>' : "") + "</div>";
  }

  function renderLedger(c) {
    var sm = sigMap(c), entries = (c.verdict || {}).entries || [];
    var maxL = Math.max.apply(null, entries.map(function (e) { return Math.abs(e.log_lr || 0); }).concat([0.001]));
    $("ledger").querySelector("tbody").innerHTML = entries.map(function (e) {
      var s = sm[e.signature_id] || {}, m = e.measure, th = s.min_effect;
      var dir = s.direction === "decrease" ? "≤ −" : "≥ ";
      var measCell = m
        ? '<span class="val">' + esc(s.measure || "") + " " + fmt(m.value) + '</span><span class="ci">[' + fmt(m.lo) + ", " + fmt(m.hi) + "]</span>" + ciBar(m, th)
        : '<span class="muted">not measured</span>';
      var llr = e.log_lr || 0;
      return "<tr>" +
        '<td data-k="Signature"><div class="sig">' + esc(e.signature_id) + '</div><span class="sensor">' + esc(e.sensor || s.sensor || "") + " · " + esc(s.probe || "") + '</span><div class="reason" lang="ja">' + esc(e.reason || "") + "</div></td>" +
        '<td data-k="Measure (95% CI)">' + measCell + "</td>" +
        '<td data-k="Threshold" class="mono">' + (th != null ? esc(dir + th) : "—") + '<span class="ci">' + (s.direction === "decrease" ? "upper" : "lower") + " CI bound</span></td>" +
        '<td data-k="Outcome"><span class="pill ' + esc(e.outcome) + '">' + esc(e.outcome) + "</span></td>" +
        '<td data-k="log LR"><span class="llr ' + (llr > 0 ? "pos" : llr < 0 ? "neg" : "zero") + '">' + fmt(llr, 3) + '</span><div class="llrbar" style="width:' + Math.max(2, Math.abs(llr) / maxL * 100).toFixed(1) + "%;background:" + (llr > 0 ? "#3ddc97" : llr < 0 ? "#ff5c6c" : "#6b7a90") + '"></div></td>' +
        "</tr>";
    }).join("");

    var cards = "";
    entries.forEach(function (e) {
      var d = e.measure && e.measure.detail;
      if (!d) return;
      if (d.target != null && d.control != null) {
        cards += '<div class="card"><h4>Difference-in-differences · ' + esc(e.signature_id) + '</h4><div class="eq">target Δ ' + plain(d.target) + " − control Δ " + plain(d.control) + " = <b>" + fmt(e.measure.value) + "</b></div>" +
          '<div class="small muted">control = same season, one year earlier · CI by bootstrap</div></div>';
      } else if (d.precip_mm != null) {
        cards += '<div class="card"><h4>Weather anomaly · ' + esc(e.signature_id) + '</h4><div class="eq">' + plain(d.precip_mm, 1) + " mm vs " + plain(d.climatology_mean_mm, 2) + " mm normal → z = <b>" + fmt(e.measure.value, 2) + "</b></div>" +
          '<div class="small muted">' + esc((d.window || []).join(" → ")) + " · " + esc(d.history_years || "") + " yrs · " + esc(d.source || "") + "</div></div>";
      }
    });
    $("did").innerHTML = cards;
  }

  /* ---------- explanation, alternatives, plan log ---------- */
  function renderExplain(c) {
    var x = c.explanation || {}, h = "";
    if (x.summary) h += '<p class="summary">' + esc(x.summary) + "</p>";
    (x.signatures || []).forEach(function (s) { h += '<div class="sigline"><code>' + esc(s.signature_id) + "</code>" + esc(s.plain) + "</div>"; });
    if (x.media_vs_observation) h += '<div class="mvo"><span class="mono small muted">MEDIA VS. OBSERVATION</span><div style="white-space:pre-line">' + esc(x.media_vs_observation) + "</div></div>";
    if ((x.image_flags || []).length) h += '<div class="flags">' + x.image_flags.map(function (f) { return '<span class="flag">' + esc(f) + "</span>"; }).join("") + "</div>";
    h += '<p class="small muted" style="margin:12px 0 0" lang="en">The judge explains the verdict; it cannot change it. The posterior comes from the ledger formula.</p>';
    $("explain").innerHTML = h || '<p class="muted">No explanation recorded.</p>';
  }

  function renderAlts(a) {
    $("alts").innerHTML = a.length ? a.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") : '<li class="muted">None recorded.</li>';
  }

  function renderPlanLog(lines) {
    $("planlog").innerHTML = lines.length ? lines.map(function (l) {
      var tag = "";
      if (/記録のみ/.test(l)) tag = '<span class="lo">AI PROPOSAL · LOGGED ONLY</span>';
      else if (/却下/.test(l)) tag = '<span class="lo">AI PROPOSAL · REJECTED</span>';
      else if (/統合/.test(l)) tag = '<span class="mg">MERGED</span>';
      return '<li><span class="ts">›</span>' + tag + esc(l) + "</li>";
    }).join("") : '<li class="muted">empty</li>';
  }

  function renderProbes(results) {
    $("probes").innerHTML = results.map(function (r) {
      var ok = !r.error;
      var rows = [
        ["sandbox", r.sandbox_id ? r.sandbox_id.slice(0, 8) + "…" : "—"],
        ["code sha256", r.code_sha256 ? r.code_sha256.slice(0, 16) + "…" : "—"],
        ["CodeAF repairs", r.repairs != null ? r.repairs : "—"],
        ["scenes", r.scene_ids ? r.scene_ids.length + " Sentinel-2 L2A" : null],
        ["valid pixels", r.valid_ratio != null ? (r.valid_ratio * 100).toFixed(2) + "%" : null],
        ["finished", r.finished_at ? r.finished_at.replace("T", " ").replace(/\.\d+Z$/, "Z") : null],
        ["error", r.error || null]
      ];
      return '<div class="probe"><div class="probe-top"><span class="probe-name">' + esc(r.probe) + '</span><span class="mono small ' + (ok ? "ok" : "bad") + '">' + (ok ? "● completed" : "● failed") + "</span></div><dl>" +
        rows.filter(function (x) { return x[1] != null; }).map(function (x) { return "<dt>" + esc(x[0]) + "</dt><dd>" + esc(x[1]) + "</dd>"; }).join("") + "</dl></div>";
    }).join("") || '<p class="muted">No probes recorded.</p>';
  }

  /* ---------- news ---------- */
  function renderNews(c) {
    var corr = c.corroboration || {}, src = (corr.sources || []).slice();
    if (!src.length && c.scan && c.scan.sources) src = c.scan.sources.slice();
    var panel = $("news-panel");
    if (!src.length) { panel.hidden = true; return; }
    panel.hidden = false;
    var order = { support: 0, refute: 1, unrelated: 2 };
    src.sort(function (a, b) { return (order[a.stance] == null ? 3 : order[a.stance]) - (order[b.stance] == null ? 3 : order[b.stance]); });

    var sc = corr.stance_counts || {}, tot = (sc.support || 0) + (sc.refute || 0) + (sc.unrelated || 0);
    var cols = { support: "#3ddc97", refute: "#ff5c6c", unrelated: "#6b7a90" };
    $("stance").innerHTML = tot ? '<div class="stancebar">' + ["support", "refute", "unrelated"].map(function (k) {
      return '<span style="width:' + ((sc[k] || 0) / tot * 100) + "%;background:" + cols[k] + '"></span>';
    }).join("") + '</div><div class="stancelegend">' + ["support", "refute", "unrelated"].map(function (k) {
      return '<span><i style="background:' + cols[k] + '"></i>' + k + " " + (sc[k] || 0) + "</span>";
    }).join("") + (corr.window ? "<span>window " + esc(corr.window.join(" → ")) + "</span>" : "") +
      "<span>news is context only; it does not enter the ledger</span></div>" : "";

    var LIMIT = 6, ul = $("news");
    function draw(all) {
      ul.innerHTML = src.slice(0, all ? src.length : LIMIT).map(function (s) {
        var u = safeUrl(s.url), host = "";
        try { host = u ? new URL(u).hostname.replace(/^www\./, "") : ""; } catch (e) { host = ""; }
        var title = esc(s.title || host || "source");
        return "<li>" + (u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer nofollow">' + title + "</a>" : "<strong>" + title + "</strong>") +
          '<div class="meta">' + (s.stance ? '<span class="stance ' + esc(s.stance) + '">' + esc(s.stance) + "</span>" : "") +
          (s.found_by ? "<span>query: " + esc(s.found_by) + "</span>" : "") + (host ? "<span>" + esc(host) + "</span>" : "") +
          (s.published ? "<span>" + esc(String(s.published).replace(/ \d\d:\d\d:\d\d GMT$/, "")) + "</span>" : "") + "</div>" +
          (s.stance_note ? '<p class="note" lang="ja">' + esc(s.stance_note) + "</p>" : "") + "</li>";
      }).join("");
      var old = panel.querySelector(".more");
      if (old) old.remove();
      if (src.length > LIMIT) {
        var b = document.createElement("button");
        b.type = "button"; b.className = "more";
        b.textContent = all ? "Show fewer" : "Show all " + src.length + " sources";
        b.onclick = function () { draw(!all); };
        panel.appendChild(b);
      }
    }
    draw(false);
  }

  load();
})();
