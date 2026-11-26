"""Querschnitte wie Sintratec Central 1.2.0 – eigener Nachbau seines Verfahrens.

Central schneidet jedes Bauteil in seinem eigenen Koordinatensystem an den Schichtgrenzen
z = k · Schichtdicke (k = 0, 1, 2, …) und rechnet dabei in 32-Bit-Gleitkomma. Nachgebaut ist:

* Netzaufbau: Eckpunkte exakt zusammenführen, Kanten je Dreieck, gleiche Kanten als Zwillinge.
* Kantenregel: welche Schnittebenen eine Kante trifft, mit Centrals Toleranz 1e-5 und dem
  schrittweisen Weiterrechnen entlang der Kante – davon hängt ab, ob eine Fläche, die genau auf
  einer Ebene liegt, schon zur Schicht gehört.
* Umrissverfolgung über Kantenschnittpunkte, Eckpunkte auf der Ebene und flache Kanten, mit
  Centrals Punktfilter (Mindestabstand, fast gerade Zwischenpunkte entfallen).
* Zusammenbau je Schicht: offene Umrisse an den nächstliegenden Enden verbinden und schließen.

Bewusst anders als Central: Central verliert durch einen Programmierfehler beim Zusammenbau immer
die oberste Schicht eines Bauteils (vertauschte Bedingung). Hier entfällt nur eine Schicht, die
genau auf der Oberkante liegt – sie enthielte Material oberhalb des Bauteils.

Ergebnis je Bauteil: {k: [Umriss (m, 2), …]} mit k = Schichtnummer ab der Unterkante.
"""
from __future__ import annotations

import numpy as np

F = np.float32
EPS = F(1e-5)
INT_MAX = 2 ** 31 - 1

CROSS, VERTEX, FLAT = 0, 1, 2


class _Mesh:
    """Netz wie Centrals Kantenstruktur (Indizes statt Objekte)."""

    def __init__(self, tris: np.ndarray):
        t = np.asarray(tris, dtype=F).reshape(-1, 3, 3)
        nf = len(t)
        # Flächennormale aus dem Umlaufsinn (Central nimmt die STL-Normale; nur ihr Vorzeichen in z zählt)
        t64 = t.astype(np.float64)
        n = np.cross(t64[:, 1] - t64[:, 0], t64[:, 2] - t64[:, 0])
        # Netz insgesamt innen nach außen (negatives Volumen)? Dann zeigen die Normalen nach innen – umdrehen
        vol = float(np.einsum("ij,ij->i", t64[:, 0], np.cross(t64[:, 1], t64[:, 2])).sum())
        self.face_nz = n[:, 2] if vol >= 0 else -n[:, 2]
        # Eckpunkte: alle 3·n Einträge stabil nach (z, y, x) sortieren, gleiche zusammenführen
        rec = t.reshape(-1, 3)
        order = np.lexsort((rec[:, 0], rec[:, 1], rec[:, 2]))      # stabil
        srt = rec[order]
        new = np.ones(len(srt), dtype=bool)
        new[1:] = np.any(srt[1:] != srt[:-1], axis=1)
        uid = np.cumsum(new) - 1                                     # eindeutiger Eckpunkt je sortiertem Eintrag
        self.v = srt[new]                                            # (nv, 3) float32
        rec_face = order // 3
        # Eckpunkte je Fläche in Reihenfolge der sortierten Liste; Flächen je Eckpunkt (erste doppelt, wie Central)
        fv = [[] for _ in range(nf)]
        vf = [[] for _ in range(len(self.v))]
        for u, f in zip(uid.tolist(), rec_face.tolist()):
            if len(fv[f]) < 3:
                fv[f].append(u)
            if not vf[u]:
                vf[u].append(f)                                      # eigene Fläche des ersten Eintrags …
            vf[u].append(f)                                          # … und noch einmal (Centrals Liste)
        self.face_v = fv
        self.vert_faces = vf
        vz = self.v[:, 2]
        vy = self.v[:, 1]
        # Kanten je Fläche: (d0,d1), (d0,d2), (d1,d2), untere Ecke zuerst
        ea, eb, ef = [], [], []
        for f in range(nf):
            d = fv[f]
            if len(d) < 3:
                d = (d + d + d)[:3]
            for i, j in ((0, 1), (0, 2), (1, 2)):
                g2, g3 = d[i], d[j]
                if vz[g2] == vz[g3]:
                    if vy[g2] == vy[g3] or vy[g2] < vy[g3]:
                        a, b = g2, g3
                    else:
                        a, b = g3, g2
                else:
                    a, b = (g2, g3) if vz[g2] < vz[g3] else (g3, g2)
                ea.append(a)
                eb.append(b)
                ef.append(f)
        self.ea = np.asarray(ea, dtype=np.int64)
        self.eb = np.asarray(eb, dtype=np.int64)
        self.ef = np.asarray(ef, dtype=np.int64)
        ne = len(self.ea)
        self.eh = np.abs(vz[self.ea] - vz[self.eb]) <= EPS          # waagrecht
        self.face_e = self.ef.reshape(-1)                            # Platzhalter, unten gesetzt
        fe = np.arange(ne, dtype=np.int64).reshape(nf, 3)
        self.face_e = fe
        self.face_flat = self.eh[fe].all(axis=1)
        # Kanten stabil nach (a, b) sortieren, gleiche als Zwillinge verbinden
        va, vb = self.v[self.ea], self.v[self.eb]
        eorder = np.lexsort((vb[:, 0], vb[:, 1], vb[:, 2], va[:, 0], va[:, 1], va[:, 2]))
        self.twin = np.full(ne, -1, dtype=np.int64)
        extra: dict[int, list[int]] = {}
        kept = []
        cur = -1
        for e in eorder.tolist():
            if cur >= 0 and (va[e] == va[cur]).all() and (vb[e] == vb[cur]).all():
                self._link(e, cur, extra)
            else:
                kept.append(e)
                cur = e
        self.kept = np.asarray(kept, dtype=np.int64)
        self.extra = extra

    def _add(self, me: int, other: int, extra, mark: bool):
        if self.twin[me] < 0:
            self.twin[me] = other
            return
        extra.setdefault(me, []).append(other)

    def _link(self, new: int, keep: int, extra):
        """Centrals Zwillingsverknüpfung (auch für Kanten mit mehr als zwei Flächen)."""
        self._add(keep, new, extra, True)
        self._add(new, keep, extra, False)
        if keep in extra:
            for x in list(extra[keep]):
                self._add(x, new, extra, False)
                self._add(new, x, extra, False)


def _edge_nodes(m: _Mesh, c: float):
    """Centrals Kantenregel, vektorisiert in float32. Liefert Knoten (Gruppe, Schicht, Art, x, y, Ecke a, Ecke b)
    und die Kanten, die Knoten tragen (Centrals 'i'-Merker)."""
    c = F(c)
    K = m.kept
    a, b = m.ea[K], m.eb[K]
    A, B = m.v[a], m.v[b]
    az, bz = A[:, 2], B[:, 2]
    ok = ~((az < 0) & (bz < 0))
    with np.errstate(all="ignore"):
        n = np.trunc(az / c).astype(np.int64) + 1
        onp = np.abs(az - (n - 1).astype(F) * c) <= EPS
        h = m.eh[K]
        out_g, out_k, out_t, out_x, out_y = [], [], [], [], []
        # Eckpunkt bzw. flache Kante auf der Ebene n-1
        sel = ok & onp
        out_g.append(K[sel]); out_k.append(n[sel] - 1)
        out_t.append(np.where(h[sel], FLAT, VERTEX)); out_x.append(A[sel, 0]); out_y.append(A[sel, 1])
        cont = ok & ~(onp & h)
        hv = B - A
        t = (n.astype(F) * c - az) / (bz - az)
        p = hv * t[:, None] + A
        f4 = np.fmod(bz, c)
        bon = (f4 <= EPS) | (np.abs(f4 - c) <= EPS)
        n2 = np.where(bon, np.trunc(bz / c).astype(np.int64), INT_MAX)
        lim = bz - EPS
        act = cont & (p[:, 2] < lim) & (n < n2)
        step = hv * (c / hv[:, 2])[:, None]
        k = n.copy()
        first = True
        while act.any():
            idx = np.flatnonzero(act)
            out_g.append(K[idx]); out_k.append(k[idx]); out_t.append(np.full(len(idx), CROSS))
            out_x.append(p[idx, 0]); out_y.append(p[idx, 1])
            p[idx] = p[idx] + step[idx]
            nxt = (p[idx, 2] < lim[idx]) & (k[idx] + 1 < n2[idx])
            k[idx] += 1
            act[:] = False
            act[idx[nxt]] = True
            first = False
    g = np.concatenate(out_g); kk = np.concatenate(out_k); tt = np.concatenate(out_t)
    xx = np.concatenate(out_x).astype(F); yy = np.concatenate(out_y).astype(F)
    has = np.zeros(len(m.ea), dtype=bool)
    owners = np.unique(g)
    has[owners] = True
    tw = m.twin[owners]
    has[tw[tw >= 0]] = True                      # Central setzt den Merker auch beim Zwilling
    return g, kk, tt, xx, yy, has


class _Boundary:
    __slots__ = ("p", "closed")

    def __init__(self):
        self.p = []
        self.closed = False

    def empty(self) -> bool:
        return len(self.p) <= 2

    def add_raw(self, x, y):
        self.p.append((x, y))

    def add_q(self, x, y, minsq):
        """Centrals addQualified: Mindestabstand, fast gerade Zwischenpunkte entfallen (float32)."""
        p = self.p
        if len(p) <= 2:
            p.append((x, y))
            return
        ex, ey = p[-1]
        dx, dy = F(F(x) - F(ex)), F(F(y) - F(ey))
        l2 = F(dx * dx + dy * dy)
        if l2 >= minsq:
            px, py = p[-2]
            vx, vy = F(F(ex) - F(px)), F(F(ey) - F(py))
            dot = F(dx * vx + dy * vy)
            den = F(l2 * F(vx * vx + vy * vy))
            with np.errstate(all="ignore"):
                r = F(F(dot * dot) / den)
            if r > F(0.99998):
                end = p[-1]
                p.remove(end)                      # wie Java: erstes gleiches Element
            p.append((x, y))


def _drawable(m: _Mesh, e: int) -> bool:
    tw = m.twin[e]
    if tw < 0:
        return False
    if not m.face_flat[m.ef[tw]]:
        return True
    a, b = m.ea[e], m.eb[e]
    g2 = next((g for g in m.face_v[m.ef[e]] if g != a and g != b), None)
    if g2 is None:
        return True
    vz = F(m.v[g2, 2] - m.v[a, 2])
    return not (m.face_nz[m.ef[tw]] * float(vz) > 0)


def _close_open(group: list[_Boundary]) -> list[_Boundary]:
    """Centrals Schicht-Zusammenbau: offene Umrisse an den nächsten Enden verbinden und schließen."""
    opn = [b for b in group if not b.closed]
    if not opn:
        return group
    closed = [b for b in group if b.closed]
    state, b2, guard = 1, None, 200
    while guard >= 0:
        guard -= 1
        if state == 1:
            if not opn:
                break
            b2 = opn[0]
            state = 2 if len(opn) == 1 else 3
        elif state == 2:
            b2.closed = True
            closed.append(b2)
            opn.remove(b2)
            state = 1
        else:
            ex, ey = b2.p[-1]
            best, idx, rev = float(np.finfo(F).max), -1, False
            for i in range(1, len(opn)):
                sx, sy = opn[i].p[0]
                tx, ty = opn[i].p[-1]
                f3 = float(F((F(sx) - F(ex)) ** 2 + (F(sy) - F(ey)) ** 2))
                f4 = float(F((F(tx) - F(ex)) ** 2 + (F(ty) - F(ey)) ** 2))
                if not (f3 < best or f4 < best):
                    continue
                if f4 < f3:
                    best, rev = f4, True
                else:
                    best, rev = f3, False
                idx = i
            sx, sy = b2.p[0]
            if float(F((F(sx) - F(ex)) ** 2 + (F(sy) - F(ey)) ** 2)) < best or idx < 0:
                state = 2
                continue
            other = opn.pop(idx)
            b2.p.extend(reversed(other.p) if rev else other.p)
            state = 1
    return closed


def part_sections(tris: np.ndarray, layer_mm: float, min_vector_mm: float = 0.025) -> dict[int, list[np.ndarray]]:
    """Querschnitte eines Bauteils (Unterkante bei z = 0) wie Central. {k: [Umrisse]}."""
    t = np.asarray(tris, dtype=np.float64).reshape(-1, 3, 3)
    if not len(t):
        return {}
    m = _Mesh(t)
    c = F(layer_mm)
    minsq = F(F(F(round(min_vector_mm * 1000)) / F(1000.0)) ** 2)
    g, kk, tt, xx, yy, has = _edge_nodes(m, c)
    # Knoten je (Kantengruppe, Schicht); der Zwilling einer Kante sieht dieselben Knoten
    gid = list(range(len(m.ea)))
    for e in m.kept.tolist():
        tw = int(m.twin[e])
        if tw >= 0:
            gid[tw] = e                          # der Zwilling bekommt Centrals Knotentabelle der Kante
    node_at: dict[int, dict[int, int]] = {}
    for i, (ge, k) in enumerate(zip(g.tolist(), kk.tolist())):
        node_at.setdefault(k, {})[ge] = i
    kind = tt
    nx, ny = xx.tolist(), yy.tolist()
    nv = np.where(kind == CROSS, -1, m.ea[g]).tolist()
    visited = np.zeros(len(g), dtype=bool)
    vvis = np.zeros(len(m.v), dtype=bool)
    # Reihenfolge der Kanten je Schicht = Reihenfolge der zusammengeführten Kantenliste
    rank = {e: i for i, e in enumerate(m.kept.tolist())}
    by_layer: dict[int, list[int]] = {}
    for k, d in node_at.items():
        by_layer[k] = sorted(d.keys(), key=rank.__getitem__)
    max_z = float(m.v[m.eb[m.kept], 2].max()) if len(m.kept) else 0.0
    n_layers = int(F(max_z) / c) + 1
    twin = m.twin.tolist()
    ef = m.ef.tolist()
    face_e = m.face_e.tolist()
    face_flat = m.face_flat.tolist()
    vf = m.vert_faces
    vxy = m.v[:, :2].tolist()
    ea, eb = m.ea.tolist(), m.eb.tolist()

    out: list[tuple[int, _Boundary]] = []
    draw_cache: dict[int, bool] = {}

    def drawable(e):
        if e not in draw_cache:
            draw_cache[e] = _drawable(m, e)
        return draw_cache[e]

    for k in range(n_layers):
        edges = by_layer.get(k)
        if not edges:
            continue
        nodes = node_at[k]

        def node(e):
            return nodes.get(gid[e])

        bound = None
        e8 = e12 = e16 = None
        v13 = v14 = None
        n18 = None
        flag19 = False
        for e8 in edges:
            nd = node(e8)
            if nd is None or visited[nd]:
                continue
            if face_flat[ef[e8]]:
                continue
            state = 0
            kd = kind[nd]
            if kd == FLAT:
                if drawable(e8) and twin[e8] >= 0:
                    bound = _Boundary()
                    e16 = e8
                    vvis[ea[e8]] = True
                    bound.add_raw(*vxy[ea[e8]])
                    v14 = ea[e8]
                    state = 6
                else:
                    continue
            elif kd == VERTEX and twin[e8] >= 0:
                v13 = nv[nd]
                if not vvis[v13]:
                    bound = _Boundary()
                    flag19 = False
                    state = 5
                else:
                    visited[nd] = True
                    continue
            elif kd == CROSS:
                bound = _Boundary()
                visited[nd] = True
                bound.add_q(nx[nd], ny[nd], minsq)
                e12 = twin[e8] if twin[e8] >= 0 else e8
                state = 4
            else:
                continue
            # --- Umriss verfolgen (Zustände 4, 5, 6 wie Central) ---
            while state:
                if state == 4:
                    e11 = e12
                    if e11 is None or e11 < 0:
                        state = 0
                        break
                    cnt = 0
                    nxt_state = state
                    for e30 in face_e[ef[e11]]:
                        if e30 == e11:
                            continue
                        n30 = node(e30)
                        if n30 is None:
                            continue
                        if kind[n30] == CROSS:
                            cnt += 1
                            if not visited[n30]:
                                visited[n30] = True
                                bound.add_q(nx[n30], ny[n30], minsq)
                                if twin[e30] < 0:
                                    bound.closed = False
                                    out.append((k, bound))
                                    nxt_state = 0
                                    continue
                                e12 = twin[e30]
                                nxt_state = 4
                                continue
                            if e8 is not None and (e8 == e30 or e8 == twin[e30]):
                                bound.closed = True
                                if not bound.empty():
                                    out.append((k, bound))
                                nxt_state = 0
                                continue
                            bound.closed = False
                            out.append((k, bound))
                            nxt_state = 0
                            continue
                        if kind[n30] != VERTEX:
                            continue
                        cnt += 1
                        v13 = nv[n30]
                        flag19 = True
                        n18 = node(e11)
                        nxt_state = 5
                    if cnt > 0:
                        state = nxt_state
                    else:
                        if not bound.empty():
                            out.append((k, bound))
                        state = 0
                elif state == 5:
                    if not vvis[v13]:
                        vvis[v13] = True
                        bound.add_raw(*vxy[v13])
                        done = False
                        cnt = 0
                        nxt_state = 0
                        for f28 in vf[v13]:
                            if done:
                                break
                            if face_flat[f28]:
                                continue
                            for e32 in face_e[f28]:
                                if not has[e32]:
                                    continue
                                n32 = node(e32)
                                if n32 is None:
                                    continue
                                if kind[n32] == CROSS:
                                    if not visited[n32]:
                                        cnt += 1
                                        visited[n32] = True
                                        bound.add_q(nx[n32], ny[n32], minsq)
                                        e12 = twin[e32]
                                        nxt_state = 4
                                        flag19 = False
                                        done = True
                                        break
                                    if flag19 and n32 == n18:
                                        continue
                                    cnt += 1
                                    flag19 = False
                                    visited[n32] = True
                                    bound.closed = True
                                    if not bound.empty():
                                        out.append((k, bound))
                                    nxt_state = 0
                                    done = True
                                    break
                                if kind[n32] != FLAT or not drawable(e32):
                                    continue
                                cnt += 1
                                if not visited[n32]:
                                    flag19 = False
                                    e16 = e32
                                    v14 = v13
                                    nxt_state = 6
                                    done = True
                                    break
                                flag19 = False
                                bound.closed = True              # Central verwirft diesen Umriss hier
                                nxt_state = 0
                                done = True
                                break
                        if cnt <= 0:
                            if not bound.empty():
                                out.append((k, bound))
                            nxt_state = 0
                        state = nxt_state if nxt_state != 5 else 0
                    else:
                        bound.closed = True
                        if not bound.empty():
                            out.append((k, bound))
                        state = 0
                elif state == 6:
                    e15 = e16
                    v17 = eb[e15] if v14 == ea[e15] else ea[e15]
                    vvis[v17] = True
                    n15 = node(e15)
                    if n15 is not None:
                        visited[n15] = True
                    bound.add_raw(*vxy[v17])
                    done = False
                    cnt = 0
                    nxt_state = 0
                    for f28 in vf[v17]:
                        if done:
                            break
                        if face_flat[f28]:
                            continue
                        for e32 in face_e[f28]:
                            if not has[e32]:
                                continue
                            n32 = node(e32)
                            if n32 is None:
                                continue
                            if kind[n32] == CROSS:
                                cnt += 1
                                if not visited[n32]:
                                    visited[n32] = True
                                    bound.add_q(nx[n32], ny[n32], minsq)
                                    e12 = twin[e32]
                                    nxt_state = 4
                                    done = True
                                    break
                                visited[n32] = True
                                bound.closed = True
                                if not bound.empty():
                                    out.append((k, bound))
                                nxt_state = 0
                                done = True
                                break
                            if kind[n32] != FLAT or e32 == e15 or e32 == twin[e15]:
                                continue
                            if not visited[n32]:
                                if not drawable(e32):
                                    continue
                                cnt += 1
                                e16 = e32
                                v14 = v17
                                nxt_state = 6
                                done = True
                                break
                            cnt += 1
                            bound.closed = True
                            if not bound.empty():
                                out.append((k, bound))
                            nxt_state = 0
                            done = True
                            break
                    if cnt > 0:
                        state = nxt_state
                    else:
                        if not bound.empty():
                            out.append((k, bound))
                        state = 0

    # Zusammenbau je Schicht (stabil nach k sortiert)
    out.sort(key=lambda kb: kb[0])
    res: dict[int, list[np.ndarray]] = {}
    i = 0
    while i < len(out):
        k = out[i][0]
        j = i
        while j < len(out) and out[j][0] == k:
            j += 1
        group = _close_open([b for _, b in out[i:j]])
        loops = [np.asarray(b.p, dtype=np.float64) for b in group if len(b.p) >= 3]
        if loops:
            res[k] = loops
        i = j
    # Nur eine Schicht genau auf der Oberkante entfällt (enthielte Material oberhalb des Teils)
    if res:
        top = max(res)
        if float(F(top) * c) >= float(F(max_z)) - float(EPS):
            res.pop(top)
    return res
