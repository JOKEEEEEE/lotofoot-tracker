"""Reprendre dans l'historique git les cotes que la collecte quotidienne a
effacées.

Winamax cesse de publier le marché 1/N/2 dès qu'un match est terminé. Chaque
réécriture d'un fichier de grille remplaçait donc des cotes d'avant-match par
des trous. Les versions précédentes sont dans git : on les relit, on garde la
plus ancienne observation plausible de chaque match, et on la recolle.
"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dater_grilles as dg

def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True,
                          cwd=str(Path(__file__).resolve().parent.parent)).stdout

commits = git("log", "--format=%H", "--reverse", "--", "data/pools").split()
print(f"{len(commits)} commits touchent data/pools")

vues = {}                       # match_id -> (trio, sha)
for sha in commits:
    fichiers = [l for l in git("show", "--name-only", "--format=", sha).split()
                if l.startswith("data/pools/") and l.endswith(".json")]
    for f in fichiers:
        brut = git("show", f"{sha}:{f}")
        if not brut:
            continue
        try:
            d = json.loads(brut)
        except ValueError:
            continue
        for m in d.get("matches", []):
            mid = m.get("match_id")
            trio = (m.get("cote_1"), m.get("cote_N"), m.get("cote_2"))
            if mid is not None and mid not in vues and dg.cote_plausible(trio):
                vues[mid] = (trio, sha[:7])
    print(f"  {sha[:7]} : {len(fichiers):5} fichiers — {len(vues)} matchs cotés connus")

racine = Path(__file__).resolve().parent.parent
rendus, touches = 0, 0
for f in sorted(racine.glob("data/pools/*/*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    change = False
    for m in d.get("matches", []):
        trio = (m.get("cote_1"), m.get("cote_N"), m.get("cote_2"))
        if dg.cote_plausible(trio):
            continue
        vu = vues.get(m.get("match_id"))
        if not vu:
            continue
        m["cote_1"], m["cote_N"], m["cote_2"] = vu[0]
        m["cotes_reprises_de"] = vu[1]
        rendus += 1
        change = True
    if change:
        f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        touches += 1
print(f"\n{rendus} cotes rendues dans {touches} grilles")
