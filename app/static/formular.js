    (function () {
      // Der Tab-Wechsel ist rein per CSS; der Platzhalter muss per JS mitziehen.
      var texte = JSON.parse(document.getElementById("anliegen-platzhalter").textContent);
      function sync() {
        var ta = document.getElementById("anliegen");
        var sel = document.querySelector('input[name="typ"]:checked');
        if (ta && sel && texte[sel.value]) { ta.placeholder = texte[sel.value]; }
      }
      function syncUrl() {
        var sel = document.querySelector('input[name="typ"]:checked');
        if (!sel || !window.history || !history.replaceState) { return; }
        var u = new URL(window.location.href);
        u.searchParams.set("typ", sel.value);
        history.replaceState(null, "", u.toString());
      }
      function syncBesondere() {
  var cb = document.querySelector('input[name="besondere_daten_einwilligung"]');
  var ok = !!(cb && cb.checked);
  Array.prototype.forEach.call(document.querySelectorAll('#lebenssituation option[data-besondere]'), function (o) {
    o.disabled = !ok; o.hidden = !ok;
    if (!ok && o.selected) { o.selected = false; document.getElementById("lebenssituation").value = ""; }
  });
  Array.prototype.forEach.call(document.querySelectorAll('.nur-besondere-option input'), function (i) {
    if (!ok) { i.checked = false; }
    i.disabled = !ok;
  });
  if (!ok) {
    ["pflegestufe", "behinderung"].forEach(function (id) { var s = document.getElementById(id); if (s) { s.value = ""; } });
  }
}
document.addEventListener("DOMContentLoaded", sync);
document.addEventListener("DOMContentLoaded", syncBesondere);
document.addEventListener("change", function (e) {
  if (e.target && e.target.name === "besondere_daten_einwilligung") { syncBesondere(); }
});
      Array.prototype.forEach.call(
        document.querySelectorAll('input[name="typ"]'),
        function (r) { r.addEventListener("change", function () { sync(); syncUrl(); }); }
      );
    })();
