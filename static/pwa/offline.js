(() => {
  "use strict";
  const DB_NAME = "emaus_offline_data";
  const DB_VERSION = 1;
  const STORE_NAME = "snapshots";
  const $ = id => document.getElementById(id);
  let snapshot = null;

  function setStatus(message, isError) {
    const el = $("statusMessage");
    el.textContent = message;
    el.style.color = isError ? "#ffb7b7" : "";
  }

  function openDatabase() {
    return new Promise((resolve, reject) => {
      if (!("indexedDB" in window)) {
        reject(new Error("Este navegador no permite almacenamiento offline."));
        return;
      }
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, {keyPath: "key"});
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("No se pudo abrir el almacenamiento local."));
    });
  }

  async function saveSnapshot(data) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put({key: "current", data, savedAt: new Date().toISOString()});
      tx.oncomplete = () => { db.close(); resolve(); };
      tx.onerror = () => { db.close(); reject(tx.error || new Error("No se pudo guardar la descarga.")); };
      tx.onabort = () => { db.close(); reject(tx.error || new Error("Se canceló el guardado local.")); };
    });
  }

  async function readSnapshot() {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const request = tx.objectStore(STORE_NAME).get("current");
      request.onsuccess = () => { const value = request.result || null; db.close(); resolve(value); };
      request.onerror = () => { db.close(); reject(request.error); };
    });
  }

  async function removeSnapshot() {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete("current");
      tx.oncomplete = () => { db.close(); resolve(); };
      tx.onerror = () => { db.close(); reject(tx.error); };
    });
  }

  function updateConnection() {
    const badge = $("connectionBadge");
    const online = navigator.onLine;
    badge.textContent = online ? "Con conexión" : "Sin conexión";
    badge.classList.toggle("online", online);
    badge.classList.toggle("offline", !online);
  }

  function addDetail(parent, title, lyric) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Ver letra y acordes";
    const pre = document.createElement("pre");
    pre.textContent = lyric || "Esta canción no tiene letra registrada.";
    details.append(summary, pre);
    parent.appendChild(details);
  }

  function showStats(record) {
    const stats = $("stats");
    stats.replaceChildren();
    const items = [
      snapshot.canciones.length + " canciones",
      snapshot.servicios.length + " servicios",
      snapshot.categorias.length + " categorías",
      "Descargado: " + new Date(record.savedAt).toLocaleString("es-EC")
    ];
    items.forEach(value => {
      const span = document.createElement("span");
      span.className = "stat";
      span.textContent = value;
      stats.appendChild(span);
    });
    stats.hidden = false;
  }

  function renderSongs() {
    const list = $("songsList");
    const query = $("songSearch").value.trim().toLocaleLowerCase("es");
    const categoryId = $("categoryFilter").value;
    const filtered = snapshot.canciones.filter(song => {
      const matchesCategory = !categoryId || String(song.categoria_id) === categoryId;
      const haystack = [song.numero, song.titulo, song.categoria, song.letra].join(" ").toLocaleLowerCase("es");
      return matchesCategory && (!query || haystack.includes(query));
    });
    $("songsCount").textContent = filtered.length + " canción(es) encontradas.";
    list.replaceChildren();
    const visible = filtered.slice(0, 100);
    visible.forEach(song => {
      const card = document.createElement("article");
      card.className = "song-card";
      const heading = document.createElement("div");
      heading.className = "song-heading";
      const title = document.createElement("div");
      const name = document.createElement("div");
      name.className = "song-title";
      const num = document.createElement("span");
      num.className = "song-number";
      num.textContent = song.numero == null ? "" : song.numero + " ·";
      name.append(num, document.createTextNode(song.titulo));
      const category = document.createElement("span");
      category.className = "song-category";
      category.textContent = song.categoria;
      title.append(name, category);
      heading.appendChild(title);
      if (song.usa_capodastro && song.traste_capodastro) {
        const capo = document.createElement("span");
        capo.className = "repertoire-meta";
        capo.textContent = "Capo " + song.traste_capodastro;
        heading.appendChild(capo);
      }
      card.appendChild(heading);
      addDetail(card, song.titulo, song.letra);
      list.appendChild(card);
    });
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No hay canciones que coincidan con la búsqueda.";
      list.appendChild(empty);
    } else if (filtered.length > visible.length) {
      const note = document.createElement("div");
      note.className = "section-note";
      note.textContent = "Se muestran las primeras 100 coincidencias. Escribe algo en el buscador para reducir resultados.";
      list.appendChild(note);
    }
  }

  function renderServices() {
    const select = $("serviceSelect");
    const current = select.value;
    select.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = snapshot.servicios.length ? "Selecciona un servicio" : "No hay servicios próximos descargados";
    select.appendChild(placeholder);
    snapshot.servicios.forEach(service => {
      const option = document.createElement("option");
      option.value = String(service.id);
      option.textContent = service.fecha + " · " + service.titulo + " · " + service.grupo;
      select.appendChild(option);
    });
    $("servicesCount").textContent = snapshot.servicios.length + " servicio(s) autorizado(s) descargado(s).";
    if (current && snapshot.servicios.some(s => String(s.id) === current)) select.value = current;
    renderSelectedService();
  }

  function renderSelectedService() {
    const detail = $("serviceDetail");
    detail.replaceChildren();
    const service = snapshot && snapshot.servicios.find(s => String(s.id) === $("serviceSelect").value);
    if (!service) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Selecciona un servicio para consultar su repertorio.";
      detail.appendChild(empty);
      return;
    }
    const card = document.createElement("article");
    card.className = "service-card";
    const title = document.createElement("h2");
    title.className = "service-heading";
    title.textContent = service.titulo;
    const meta = document.createElement("p");
    meta.className = "service-meta";
    meta.textContent = [service.fecha, service.hora_inicio, service.grupo, service.lugar, service.estado].filter(Boolean).join(" · ");
    card.append(title, meta);
    if (!service.repertorio.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Este servicio todavía no tiene canciones en su repertorio.";
      card.appendChild(empty);
    } else {
      service.repertorio.forEach((song, index) => {
        const item = document.createElement("div");
        item.className = "repertoire-item";
        const name = document.createElement("strong");
        name.textContent = (index + 1) + ". " + song.titulo;
        const info = document.createElement("div");
        info.className = "repertoire-meta";
        const details = [];
        if (song.usa_capodastro && song.traste_capodastro) details.push("Capodastro: traste " + song.traste_capodastro);
        if (song.semitonos_transpuestos) details.push("Transposición: " + (song.semitonos_transpuestos > 0 ? "+" : "") + song.semitonos_transpuestos + " semitono(s)");
        if (song.notacion_acordes) details.push("Notación: " + song.notacion_acordes);
        info.textContent = details.join(" · ");
        item.append(name, info);
        addDetail(item, song.titulo, song.letra);
        card.appendChild(item);
      });
    }
    detail.appendChild(card);
  }

  function render(record) {
    snapshot = record.data;
    $("contentSection").hidden = false;
    $("categoryFilter").replaceChildren();
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "Todas las categorías";
    $("categoryFilter").appendChild(all);
    snapshot.categorias.forEach(category => {
      const option = document.createElement("option");
      option.value = String(category.id);
      option.textContent = category.nombre;
      $("categoryFilter").appendChild(option);
    });
    renderSongs();
    renderServices();
    showStats(record);
    setStatus("Contenido disponible en este dispositivo. Puedes consultar el cancionero y los repertorios sin conexión.", false);
  }

  async function downloadData() {
    if (!navigator.onLine) {
      setStatus("No hay conexión. Puedes consultar la última descarga guardada.", true);
      return;
    }
    $("syncButton").disabled = true;
    setStatus("Descargando canciones y repertorios autorizados…", false);
    try {
      const response = await fetch("/offline/datos/", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: {"Accept": "application/json"}
      });
      if (!response.ok) {
        if (response.status === 401 || response.redirected) {
          throw new Error("Tu sesión no está activa. Inicia sesión en Emaús y vuelve a descargar el contenido.");
        }
        throw new Error("No se pudo descargar el contenido (HTTP " + response.status + ").");
      }
      const data = await response.json();
      if (!data.ok || !Array.isArray(data.canciones) || !Array.isArray(data.servicios)) {
        throw new Error("El servidor devolvió un formato de datos no válido.");
      }
      await saveSnapshot(data);
      const record = await readSnapshot();
      render(record);
    } catch (error) {
      setStatus(error.message || "Ocurrió un error al descargar los datos.", true);
    } finally {
      $("syncButton").disabled = false;
    }
  }

  function switchTab(tab) {
    const songs = tab === "songs";
    $("songsPanel").hidden = !songs;
    $("servicesPanel").hidden = songs;
    $("songsTab").classList.toggle("active", songs);
    $("servicesTab").classList.toggle("active", !songs);
    $("songsTab").setAttribute("aria-selected", songs ? "true" : "false");
    $("servicesTab").setAttribute("aria-selected", songs ? "false" : "true");
  }

  async function init() {
    updateConnection();
    window.addEventListener("online", updateConnection);
    window.addEventListener("offline", updateConnection);

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", {scope: "/"}).catch(error => console.warn("No se pudo registrar PWA:", error));
    }

    $("syncButton").addEventListener("click", downloadData);
    $("clearButton").addEventListener("click", async () => {
      if (!confirm("¿Eliminar las canciones y repertorios guardados en este dispositivo?")) return;
      try {
        await removeSnapshot();
        snapshot = null;
        $("contentSection").hidden = true;
        $("stats").hidden = true;
        setStatus("Se eliminó el contenido descargado de este dispositivo.", false);
      } catch (error) {
        setStatus("No se pudo eliminar el contenido local.", true);
      }
    });
    $("songsTab").addEventListener("click", () => switchTab("songs"));
    $("servicesTab").addEventListener("click", () => switchTab("services"));
    $("songSearch").addEventListener("input", () => snapshot && renderSongs());
    $("categoryFilter").addEventListener("change", () => snapshot && renderSongs());
    $("serviceSelect").addEventListener("change", renderSelectedService);

    let installPrompt = null;
    const installButton = $("installButton");
    window.addEventListener("beforeinstallprompt", event => {
      event.preventDefault();
      installPrompt = event;
      installButton.hidden = false;
    });
    installButton.addEventListener("click", async () => {
      if (!installPrompt) return;
      installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      installButton.hidden = true;
    });

    try {
      const record = await readSnapshot();
      if (record && record.data) render(record);
    } catch (error) {
      setStatus(error.message || "No se pudo leer el contenido local.", true);
    }
    if (!snapshot && navigator.onLine) {
      setStatus("Conéctate a tu cuenta y pulsa «Descargar / actualizar contenido» para preparar el modo offline.", false);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
