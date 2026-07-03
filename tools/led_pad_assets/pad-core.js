(function () {
  async function request(path, options = {}) {
    const init = {headers: {"Content-Type": "application/json"}, ...options};
    if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
    const res = await fetch(path, init);
    const json = await res.json();
    if (!json.ok && json.error) throw new Error(json.error);
    return json;
  }
  window.LedPadApi = {
    config: () => request("/api/config"),
    renders: () => request("/api/renders"),
    palettes: () => request("/api/palettes"),
    runtime: () => request("/api/runtime_status"),
    play: (body) => request("/api/play", {method: "POST", body}),
    update: (body) => request("/api/update", {method: "POST", body}),
    stop: () => request("/api/stop", {method: "POST", body: {}}),
    emergencyStop: () => request("/api/emergency_stop", {method: "POST", body: {}}),
    takeover: () => request("/api/takeover", {method: "POST", body: {}}),
    release: () => request("/api/release", {method: "POST", body: {}}),
    session: (body) => request("/api/session", {method: "POST", body}),
    saveLook: (body) => request("/api/look/save", {method: "POST", body}),
    duplicate: (body) => request("/api/look/duplicate", {method: "POST", body}),
    move: (body) => request("/api/look/move", {method: "POST", body}),
    deleteLook: (body) => request("/api/look/delete", {method: "POST", body}),
    commit: () => request("/api/commit", {method: "POST", body: {}}),
    discard: () => request("/api/discard", {method: "POST", body: {}})
  };
}());
