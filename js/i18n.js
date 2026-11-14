/* EN / 日本語 switch. Static text is matched by exact string; mixed-markup blocks use data-i18n keys.
   Dynamic content rendered by app.js is translated as it appears (MutationObserver). */
(function () {
  "use strict";

  var HTML = {
    pitch: 'バズった主張を AI が<em>事前登録された実験</em>に変え、衛星と気象データで検証するエージェント。判定は LLM ではなく数式で出します。',
    how_lede: 'AgentField 上の 3 つのノード（<span class="mono">witness-scout</span>・<span class="mono">witness-lab</span>・<span class="mono">witness-core</span>）が、うわさを再現可能な判定へと運びます。',
    why_lede: '生成 AI によって、現実世界についての主張は「捏造」も「別の AI での検証」も安くなりました。どちらも信頼は生みません。一方で正解はすでに存在します。無料の衛星が地球上のあらゆる地点を数日おきに撮っています。足りないのは、主張が拡散する速さで、それを確かめる仕組みです。',
    why_answer: '<strong>私たちの答え：</strong>AI には実験を設計させ、判定からは締め出す。仮説と閾値は画素を 1 枚も読む前に封印し、結果は誰でも再実行できる数式で出します。'
  };

  var T = {
    // nav / hero
    "Why now": "なぜ今か", "How it works": "仕組み", "Live case": "実例", "Stack": "技術", "Use cases": "用途",
    "// claim verification from orbit": "// 軌道からの主張検証",
    "See the live case": "実例を見る",
    "FEATURED RUN": "注目の実行",
    "posterior P(claim)": "事後確率 P(主張)",
    "sealed sha256": "封印 sha256",
    "Sealed before looking": "見る前に封印",
    "Hypothesis, signatures and thresholds are hashed with SHA-256 before any pixel is read. AI proposals to move thresholds are logged, never applied.":
      "仮説・シグネチャ・閾値は、画素を読む前に SHA-256 で封印。閾値を動かす AI の提案は記録されるだけで、適用されません。",
    "Difference-in-differences": "差の差",
    "Every change is compared against the same season one year earlier, with bootstrap confidence intervals.":
      "すべての変化を前年同季節の変化と比較し、ブートストラップで信頼区間を出します。",
    "A skeptic in the loop": "懐疑役のエージェント",
    "A skeptic agent lists rival explanations first: tide, cloud shadow, irrigation, permanent water, wrong date.":
      "懐疑役が先に対立仮説を挙げます：潮位、雲の影、灌漑、恒久的な水域、日付の取り違え。",
    "Verdict by formula": "判定は数式で",
    "Posterior log-odds = prior log-odds + Σ log LR over the evidence ledger. Each signature confirms, refutes or abstains.":
      "事後対数オッズ = 事前対数オッズ + 証拠台帳の Σ log LR。各シグネチャは支持・反証・保留のいずれか。",
    // why now
    "// the problem": "// 課題",
    "Fakes are free": "偽物はタダで作れる",
    "AI-generated flood photos, recycled old videos and place-swapped captions spread faster than any newsroom can check them.":
      "AI 生成の洪水写真、使い回しの古い動画、場所をすり替えたキャプション。どの編集部の検証よりも速く拡散します。",
    "LLM verdicts are opinions": "LLM の判定は意見にすぎない",
    "Ask a model to fact-check and it writes a convincing rationale after the fact. It can argue either side, and nobody can re-run it.":
      "モデルにファクトチェックを頼むと、もっともらしい理由を後付けで書きます。どちらの立場でも論じられ、誰も再実行できません。",
    "Agents act on claims": "エージェントが主張に基づいて動く",
    "Insurance payouts, aid allocation and supply-chain audits are being automated. A machine that pays out needs evidence a machine can audit.":
      "保険金の支払い、支援物資の配分、サプライチェーン監査が自動化されつつあります。機械が支払うなら、機械が監査できる証拠が要ります。",
    "Orbit already saw it": "衛星はすでに見ている",
    "Sentinel-2 and ERA5 are open and global. The missing piece is an agent that asks the right question first and lets the data answer.":
      "Sentinel-2 と ERA5 は全球・無料で公開されています。足りないのは、先に正しい問いを立て、答えはデータに任せるエージェントです。",
    // how / case
    "// pipeline": "// パイプライン",
    "// case file": "// 事件簿",
    "Featured case": "注目の事例",
    "run": "実行",
    "Pre-registration sealed": "事前登録の封印",
    "copy": "コピー", "copied": "コピーしました",
    "Sentinel-2 imagery": "Sentinel-2 画像",
    "Slider": "スライダー", "Side by side": "並べて表示", "Change map": "変化マップ",
    "Posterior": "事後確率",
    "computed, not generated": "生成ではなく計算",
    "Evidence ledger": "証拠台帳",
    "one measure = one piece of evidence": "1 つの測定 = 1 つの証拠",
    "Signature": "シグネチャ", "Measure (95% CI)": "測定値（95% 信頼区間）", "Threshold": "閾値", "Outcome": "結果",
    "Judge explanation": "判定の説明",
    "Skeptic: alternatives tested": "懐疑役：検証した対立仮説",
    "Plan log": "計画ログ",
    "thresholds frozen after seal": "封印後は閾値を固定",
    "Probe provenance": "プローブの来歴",
    "Daytona sandboxes": "Daytona サンドボックス",
    "News corroboration": "報道との照合",
    "Pixels whose NDWI crossed into water after the event, relative to before. The ledger uses the difference against the same season one year earlier.":
      "出来事の後に NDWI が水域へ変わった画素（出来事の前と比較）。台帳では前年同季節との差を使います。",
    "Sentinel-2 L2A true colour around the area of interest. Drag the slider to compare before and after.":
      "対象範囲の Sentinel-2 L2A トゥルーカラー。スライダーを動かして前後を比較できます。",
    "No optical imagery for this run.": "この実行には光学画像がありません。",
    "supported": "裏付けあり", "contradicted": "反証", "inconclusive": "判定不能",
    "SUPPORTED": "裏付けあり", "CONTRADICTED": "反証", "INCONCLUSIVE": "判定不能",
    "confirm": "支持", "refute": "反証", "null": "保留",
    // stack
    "// stack": "// 技術スタック",
    "Built with": "使用技術",
    "Orchestrates the three nodes (witness-scout, witness-lab, witness-core), discovers probe skills, and keeps memory, notes and the trace.":
      "3 つのノード（witness-scout・witness-lab・witness-core）を統括し、プローブを動的に発見し、メモリ・ノート・トレースを保持します。",
    "Searches news both supporting and debunking the claim. Optional: the run continues without it.":
      "主張を支持する報道と否定する報道の両方を検索します。任意で、無くても検証は続きます。",
    "Runs each sensor probe in its own isolated sandbox, in parallel. The sandbox only reads Sentinel-2 COG pixels from S3; metadata is prefetched.":
      "センサーのプローブを 1 本ずつ隔離サンドボックスで並列実行。サンドボックスは S3 の Sentinel-2 画素だけを読み、メタデータは事前取得します。",
    "Repairs probe code that crashes inside Daytona, via OpenRouter, then re-runs it under the same sealed plan.":
      "Daytona 内で落ちたプローブのコードを OpenRouter 経由で修復し、同じ封印済みの計画のまま再実行します。",
    "Hosts Qwen2.5-VL-7B on vLLM on an RTX 3090 for planning, the skeptic, and image interpretation.":
      "RTX 3090 上の vLLM で Qwen2.5-VL-7B をホストし、計画・懐疑役・画像の判読を担います。",
    // uses
    "// who it is for": "// 誰のためか",
    "Newsroom fact-checking": "報道のファクトチェック",
    "Check a viral flood, fire or blast claim against orbit within minutes, with a sealed method editors can publish.":
      "拡散した洪水・火災・爆発の主張を数分で衛星と照合。編集部が公開できる、封印済みの手法で。",
    "Parametric insurance": "パラメトリック保険",
    "Verify that a trigger event actually happened at the insured site before paying a claim.":
      "保険金を支払う前に、支払い条件となる出来事が契約地点で本当に起きたかを確認します。",
    "Humanitarian damage assessment": "人道支援の被害把握",
    "Triage reports of flooding or destruction so responders go where the evidence points.":
      "冠水や破壊の報告を選別し、救援が証拠の示す場所へ向かえるようにします。",
    "Deforestation due diligence": "森林破壊のデューデリジェンス",
    "Test supplier claims of \"no clearing since 2020\" against the canopy record.":
      "「2020 年以降伐採なし」というサプライヤーの主張を、樹冠の記録と照合します。",
    "Hackathon demo. Imagery: Copernicus Sentinel-2. Weather: Open-Meteo ERA5.":
      "ハッカソンのデモ。画像：Copernicus Sentinel-2。気象：Open-Meteo ERA5。",
    // pipeline diagram labels
    "Claim": "主張", "Report": "レポート", "Judge": "判定の説明", "Evidence ledger ": "証拠台帳",
    "plain-language explanation": "平易な言葉での説明",
    "case.json + images": "case.json と画像",
    "Show fewer": "少なく表示"
  };

  var lang = "en", orig = new WeakMap(), busy = false, EN = {}, REV = {};
  var JP = /[\u3040-\u30ff\u4e00-\u9fff]/;
  // Japanese strings inside run data (claims, LLM explanations) → English, built by scripts/export_web.py
  fetch("data/index.json").then(function (r) { return r.json(); }).then(function (idx) {
    var runs = (idx.runs || idx || []).map(function (x) { return x.run_id || x; });
    return Promise.all(runs.map(function (id) {
      return fetch("data/" + id + "/en.json").then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; });
    }));
  }).then(function (maps) { maps.forEach(function (m) { for (var k in m) { EN[k] = m[k]; REV[m[k].trim()] = k; } }); if (lang === "en") apply(); })
    .catch(function () {});
  try { lang = new URLSearchParams(location.search).get("lang") || localStorage.getItem("ow-lang") || ""; } catch (e) { lang = ""; }
  if (!lang) lang = (navigator.language || "").toLowerCase().indexOf("ja") === 0 ? "ja" : "en";

  // bilingual labels rendered by app.js ("本当の主張 / True claim") → one language
  var LABELS = [["本当の主張 / True claim", "True claim", "本当の主張"], ["誤情報 / False claim", "False claim", "誤情報"]];
  function labels(n) {
    var src = orig.has(n) ? orig.get(n) : n.nodeValue, out = src, hit = false;
    LABELS.forEach(function (l) { if (out.indexOf(l[0]) >= 0) { out = out.replace(l[0], lang === "ja" ? l[2] : l[1]); hit = true; } });
    if (!hit) return false;
    if (!orig.has(n)) orig.set(n, n.nodeValue);
    n.nodeValue = out; return true;
  }
  function translateNode(n) {
    var raw = n.nodeValue, key = raw.trim();
    if (!key) return;
    if (labels(n)) return;
    if (lang === "ja") {
      var src = orig.has(n) ? orig.get(n) : raw;
      var k2 = src.trim(), ja = T[k2];
      if (ja === undefined && /^Show all \d+ sources$/.test(k2)) ja = "全 " + k2.match(/\d+/)[0] + " 件を表示";
      if (ja === undefined && !orig.has(n) && REV[k2] !== undefined) ja = REV[k2];  // English run text without a stored original
      if (ja !== undefined) {
        if (!orig.has(n)) orig.set(n, raw);
        n.nodeValue = src.replace(k2, ja);
      } else if (orig.has(n)) {  // e.g. run data shown in English before the switch
        n.nodeValue = orig.get(n); orig.delete(n);
      }
    } else {
      var s0 = orig.has(n) ? orig.get(n) : raw, k0 = s0.trim();
      if (JP.test(k0) && EN[k0] !== undefined) {
        if (!orig.has(n)) orig.set(n, raw);
        n.nodeValue = s0.replace(k0, EN[k0]);
      } else if (orig.has(n)) {
        n.nodeValue = orig.get(n); orig.delete(n);
      }
    }
  }
  function walk(root) {
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) { var p = n.parentNode && n.parentNode.nodeName; return p === "SCRIPT" || p === "STYLE" ? 2 : 1; }
    });
    var n; while ((n = w.nextNode())) translateNode(n);
  }
  function applyHtml() {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var k = el.getAttribute("data-i18n");
      if (!el.dataset.en) el.dataset.en = el.innerHTML;
      el.innerHTML = lang === "ja" && HTML[k] ? HTML[k] : el.dataset.en;
    });
  }
  function apply() {
    busy = true;
    document.documentElement.lang = lang;
    applyHtml(); walk(document.body);
    var b = document.getElementById("lang-toggle");
    if (b) b.innerHTML = lang === "ja" ? '<b>日本語</b> / EN' : '<b>EN</b> / 日本語';
    mo.takeRecords(); busy = false;
  }
  var mo = new MutationObserver(function (recs) {
    if (busy) return;
    busy = true;
    recs.forEach(function (r) {
      r.addedNodes.forEach(function (n) { n.nodeType === 3 ? translateNode(n) : n.nodeType === 1 && walk(n); });
      if (r.type === "characterData") { orig.delete(r.target); translateNode(r.target); }
    });
    mo.takeRecords(); busy = false;
  });

  function init() {
    mo.observe(document.body, { childList: true, subtree: true, characterData: true });
    var b = document.getElementById("lang-toggle");
    if (b) b.addEventListener("click", function () {
      lang = lang === "ja" ? "en" : "ja";
      try { localStorage.setItem("ow-lang", lang); } catch (e) {}
      apply();
    });
    apply();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
