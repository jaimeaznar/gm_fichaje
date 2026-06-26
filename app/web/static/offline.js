/* Red de seguridad offline ligera (REQ-22).
 *
 * Equipo de oficina con red estable: NO se monta Service Worker + IndexedDB. Basta una cola
 * en localStorage. Si el POST htmx del evento falla por red (htmx:sendError), se guarda el
 * fichaje con su HORA REAL y una clave de idempotencia (client_event_id) y se muestra
 * "pendiente de sincronizar". Al recuperar conexion se reenvia a POST /fichaje/sync: el
 * servidor valida la ventana de tolerancia y deduplica por client_event_id (nunca duplica).
 */
(function () {
  "use strict";
  var KEY = "gm_offline_queue";

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; }
    catch (e) { return []; }
  }
  function save(q) { localStorage.setItem(KEY, JSON.stringify(q)); }
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "evt-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  function render() {
    var q = load();
    var banner = document.getElementById("offline-banner");
    var count = document.getElementById("offline-count");
    if (!banner) return;
    if (q.length) {
      if (count) count.textContent = q.length;
      banner.style.display = "block";
    } else {
      banner.style.display = "none";
    }
  }

  function enqueue(eventType) {
    var q = load();
    q.push({
      event_type: eventType,
      occurred_at: new Date().toISOString(),
      client_event_id: uuid(),
      modalidad: "presencial"
    });
    save(q);
    render();
  }

  async function flush() {
    var q = load();
    if (!q.length) return;
    var remaining = [];
    var synced = 0;
    for (var i = 0; i < q.length; i++) {
      var item = q[i];
      try {
        var r = await fetch("/fichaje/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(item)
        });
        if (r.ok) { synced++; }
        else if (r.status >= 500) { remaining.push(item); }
        /* 4xx = rechazo definitivo (fuera de ventana / transicion invalida): se descarta. */
      } catch (e) {
        remaining.push(item); /* sigue sin red */
      }
    }
    save(remaining);
    render();
    if (synced > 0 && window.htmx) {
      htmx.ajax("GET", "/fichar/estado", { target: "#estado", swap: "outerHTML" });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    render();
    document.body.addEventListener("htmx:sendError", function (evt) {
      var elt = evt.detail && evt.detail.elt;
      var et = elt && elt.getAttribute("data-event-type");
      if (et) enqueue(et);
    });
    window.addEventListener("online", flush);
    if (navigator.onLine) flush();
  });
})();
