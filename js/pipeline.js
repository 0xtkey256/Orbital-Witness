/* Inline SVG pipeline diagram: a wide layout for desktop and a tall one for phones. */
(function () {
  var SP = {
    agentfield: { c: "#a78bfa", n: "AGENTFIELD" },
    tavily: { c: "#4fd1ff", n: "TAVILY" },
    nosana: { c: "#f472b6", n: "NOSANA" },
    daytona: { c: "#3ddc97", n: "DAYTONA" },
    codeaf: { c: "#ffb547", n: "CODEAF" },
    seal: { c: "#3ddc97", n: "SHA-256" },
    formula: { c: "#e6edf7", n: "FORMULA" },
    none: { c: "#8a9bb4", n: "" }
  };

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }

  function box(x, y, w, h, title, sub, sp, opts) {
    opts = opts || {};
    var s = SP[sp] || SP.none;
    var o = '<g>';
    o += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="10" fill="' + (opts.fill || "#0d1526") + '" stroke="' + s.c + '" stroke-opacity="' + (opts.dash ? 0.6 : 0.55) + '" stroke-width="1.4"' + (opts.dash ? ' stroke-dasharray="5 5"' : "") + '/>';
    o += '<rect x="' + x + '" y="' + y + '" width="4" height="' + h + '" rx="2" fill="' + s.c + '"/>';
    var tx = x + 16;
    if (s.n) o += '<text class="t-sp" x="' + tx + '" y="' + (y + 18) + '" fill="' + s.c + '" style="fill:' + s.c + '">' + esc(opts.spLabel || s.n) + '</text>';
    o += '<text class="t-title" x="' + tx + '" y="' + (y + (s.n ? 38 : 28)) + '">' + esc(title) + '</text>';
    if (sub) o += '<text class="t-sub" x="' + tx + '" y="' + (y + (s.n ? 56 : 46)) + '">' + esc(sub) + '</text>';
    return o + '</g>';
  }

  function arrow(d, color) {
    return '<path d="' + d + '" fill="none" stroke="' + (color || "#4fd1ff") + '" stroke-width="1.6" class="flow" marker-end="url(#ah)"/>';
  }

  var defs = '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#4fd1ff"/></marker>' +
    '<marker id="ahA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#ffb547"/></marker></defs>';

  function wide() {
    var W = 1200, H = 540, o = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Pipeline: Claim, Scout, Planner, Skeptic, Seal, parallel probes in Daytona sandboxes with CodeAF repair, Ledger, Judge, Report">' + defs;
    var bw = 200, bh = 70, y1 = 30, xs = [20, 255, 490, 725, 980];
    o += box(xs[0], y1, bw, bh, "Viral claim", "text from social media", "none", { spLabel: "INPUT" });
    o += box(xs[1], y1, bw, bh, "Scout", "news for & against", "tavily");
    o += box(xs[2], y1, bw, bh, "Planner", "hypothesis + signatures", "nosana", { spLabel: "NOSANA · QWEN2.5-VL" });
    o += box(xs[3], y1, bw, bh, "Skeptic", "rival explanations", "nosana");
    o += box(xs[4], y1, bw, bh, "Seal", "thresholds frozen", "seal");
    for (var i = 0; i < 4; i++) o += arrow("M" + (xs[i] + bw + 4) + " " + (y1 + 35) + " H" + (xs[i + 1] - 6));
    // Seal -> Daytona
    o += arrow("M1080 " + (y1 + bh + 4) + " V172");
    // Daytona group
    o += '<rect x="380" y="178" width="800" height="200" rx="14" fill="rgba(61,220,151,0.04)" stroke="#3ddc97" stroke-opacity="0.5" stroke-dasharray="6 6"/>';
    o += '<text class="t-sp" x="398" y="200" style="fill:#3ddc97">DAYTONA · ISOLATED SANDBOXES, IN PARALLEL</text>';
    var px = [400, 660, 920];
    o += box(px[0], 214, 240, 70, "Optical · Sentinel-2", "NDWI new water, DiD + CI", "daytona", { spLabel: "PROBE" });
    o += box(px[1], 214, 240, 70, "Weather · ERA5", "precip z-score vs 15 yrs", "daytona", { spLabel: "PROBE" });
    o += box(px[2], 214, 240, 70, "SAR · Sentinel-1", "VV drop (optional)", "daytona", { spLabel: "PROBE", dash: true });
    // CodeAF loop
    o += '<rect x="400" y="304" width="760" height="56" rx="10" fill="rgba(255,181,71,0.06)" stroke="#ffb547" stroke-opacity="0.55"/>';
    o += '<text class="t-sp" x="416" y="324" style="fill:#ffb547">CODEAF · VIA OPENROUTER</text>';
    o += '<text class="t-sub" x="416" y="344">probe crashes → patch code → re-run under the same sealed plan</text>';
    o += '<path d="M1040 304 C1040 292, 1060 292, 1060 288" fill="none" stroke="#ffb547" stroke-width="1.5" marker-end="url(#ahA)"/>';
    o += '<path d="M1100 288 C1100 292, 1120 296, 1120 302" fill="none" stroke="#ffb547" stroke-width="1.5" marker-end="url(#ahA)"/>';
    // Daytona -> Ledger
    o += box(40, 240, 300, 74, "Evidence ledger", "Σ log LR, prior → posterior", "formula", { spLabel: "FORMULA, NOT LLM" });
    o += arrow("M376 277 H346");
    // Row 3
    var y3 = 430;
    o += arrow("M190 318 V" + (y3 - 6));
    o += box(40, y3, 300, 74, "Judge", "plain-language explanation", "nosana", { spLabel: "NOSANA · VLM" });
    o += arrow("M344 " + (y3 + 37) + " H374");
    o += box(380, y3, 240, 74, "Report", "case.json + images", "none", { spLabel: "OUTPUT" });
    // AgentField band
    o += '<rect x="660" y="' + y3 + '" width="520" height="74" rx="10" fill="rgba(167,139,250,0.07)" stroke="#a78bfa" stroke-opacity="0.6"/>';
    o += '<text class="t-sp" x="678" y="' + (y3 + 20) + '" style="fill:#a78bfa">AGENTFIELD · CONTROL PLANE</text>';
    o += '<text class="t-title" x="678" y="' + (y3 + 42) + '">witness-scout · witness-lab · witness-core</text>';
    o += '<text class="t-sub" x="678" y="' + (y3 + 60) + '">skill discovery · memory · notes / trace across every step</text>';
    return o + '</svg>';
  }

  function tall() {
    var W = 360, x = 14, w = 332, h = 66, gap = 26, y = 10, o = "";
    function step(t, s, sp, opt) { o += box(x, y, w, h, t, s, sp, opt); y += h; o += arrow("M180 " + (y + 3) + " V" + (y + gap - 4)); y += gap; }
    step("Viral claim", "text from social media", "none", { spLabel: "INPUT" });
    step("Scout", "news for & against", "tavily");
    step("Planner", "hypothesis + signatures", "nosana", { spLabel: "NOSANA · QWEN2.5-VL" });
    step("Skeptic", "rival explanations", "nosana");
    step("Seal", "thresholds frozen with SHA-256", "seal");
    var gy = y;
    o += '<rect x="8" y="' + gy + '" width="344" height="320" rx="14" fill="rgba(61,220,151,0.04)" stroke="#3ddc97" stroke-opacity="0.5" stroke-dasharray="6 6"/>';
    o += '<text class="t-sp" x="22" y="' + (gy + 22) + '" style="fill:#3ddc97">DAYTONA · PARALLEL SANDBOXES</text>';
    var py = gy + 36;
    o += box(22, py, 316, 62, "Optical · Sentinel-2", "new water, DiD + CI", "daytona", { spLabel: "PROBE" }); py += 72;
    o += box(22, py, 316, 62, "Weather · ERA5", "precip z-score", "daytona", { spLabel: "PROBE" }); py += 72;
    o += box(22, py, 316, 62, "SAR · Sentinel-1", "VV drop (optional)", "daytona", { spLabel: "PROBE", dash: true }); py += 72;
    o += '<rect x="22" y="' + py + '" width="316" height="58" rx="10" fill="rgba(255,181,71,0.06)" stroke="#ffb547" stroke-opacity="0.55"/>';
    o += '<text class="t-sp" x="36" y="' + (py + 22) + '" style="fill:#ffb547">CODEAF REPAIR LOOP</text>';
    o += '<text class="t-sub" x="36" y="' + (py + 42) + '">crash → patch → re-run (OpenRouter)</text>';
    y = gy + 320; o += arrow("M180 " + (y + 3) + " V" + (y + gap - 4)); y += gap;
    step("Evidence ledger", "Σ log LR, prior → posterior", "formula", { spLabel: "FORMULA, NOT LLM" });
    step("Judge", "plain-language explanation", "nosana", { spLabel: "NOSANA · VLM" });
    o += box(x, y, w, h, "Report", "case.json + images", "none", { spLabel: "OUTPUT" }); y += h + 16;
    o += '<rect x="8" y="' + y + '" width="344" height="78" rx="10" fill="rgba(167,139,250,0.07)" stroke="#a78bfa" stroke-opacity="0.6"/>';
    o += '<text class="t-sp" x="22" y="' + (y + 20) + '" style="fill:#a78bfa">AGENTFIELD · CONTROL PLANE</text>';
    o += '<text class="t-title" x="22" y="' + (y + 42) + '" style="font-size:13px">scout · lab · core nodes</text>';
    o += '<text class="t-sub" x="22" y="' + (y + 62) + '">skill discovery · memory · trace</text>';
    y += 90;
    return '<svg viewBox="0 0 ' + W + ' ' + y + '" role="img" aria-label="Pipeline diagram">' + defs.replace(/id="ah/g, 'id="t-ah') .replace(/id="t-ahA"/, 'id="t-ahA"') + o.replace(/url\(#ah/g, "url(#t-ah") + '</svg>';
  }

  document.getElementById("pipeline-wide").innerHTML = wide();
  document.getElementById("pipeline-tall").innerHTML = tall();
})();
