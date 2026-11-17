.pragma library
// Verbindung zum Hintergrunddienst kitd (läuft auf demselben Pi).
var BASE = "http://127.0.0.1:8080";

function _req(method, path, body, cb) {
    var x = new XMLHttpRequest();
    x.onreadystatechange = function () {
        if (x.readyState !== XMLHttpRequest.DONE) return;
        var j = null;
        try { j = JSON.parse(x.responseText); } catch (e) { j = null; }
        if (cb) cb(x.status === 200 || x.status === 403 ? j : null);
    };
    x.open(method, BASE + path);
    if (body !== undefined) {
        x.setRequestHeader("Content-Type", "application/json");
        x.send(JSON.stringify(body));
    } else {
        x.send();
    }
}

function get(path, cb) { _req("GET", path, undefined, cb); }
function cmd(body, cb) { _req("POST", "/api/cmd", body, cb); }

function de(v, d) {
    if (v === undefined || v === null || isNaN(v)) return "—";
    return Number(v).toFixed(d === undefined ? 1 : d).replace(".", ",");
}

function hms(s) {
    if (s === undefined || s === null) return "—";
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h + ":" + (m < 10 ? "0" : "") + m + " h";
}
