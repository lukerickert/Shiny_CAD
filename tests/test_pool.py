# -*- coding: utf-8 -*-
"""Worker pool (pool.py): view data and interference computed in worker processes equal the values computed in
the server process. Runs in a separate Python process with DRAWGEN_WORKERS=2."""
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = textwrap.dedent('''
    import json, os, sys
    sys.path.insert(0, ROOT)
    def main():
        from build123d import Box, Compound, Pos, export_step
        from drawgen import assembly as A, pool
        path = os.path.join(TMP, "four.step")
        export_step(Compound(children=[Pos(30 * i, 0, 0) * Box(40, 10, 10) for i in range(4)]), path)
        asm = {"components": [{"id": "c%d" % i, "name": "P%d" % i, "source": {"type": "step", "path": path, "part": i},
                               "pos": [0, 0, 0], "rot": [0, 0, 0]} for i in range(4)]}
        src = A.Sources(TMP, {})
        n = A.prefetch_views(asm, src)
        comps, rows, tot = A.view_data(asm, src)
        interf = A.interference_parallel(asm, src)
        serial = A.interference(A.build(asm, A.Sources(TMP, {})))
        pool.shutdown()
        print(json.dumps({"from_workers": n, "vol": tot["volume_mm3"], "meshes": [len(c["mesh"]["triangles"]) for c in comps],
                          "interf": sorted(round(x["volume_mm3"], 3) for x in interf),
                          "serial": sorted(round(x["volume_mm3"], 3) for x in serial)}))
    if __name__ == "__main__":
        main()
''')


def test_pool_matches_serial(tmp_path):
    import json
    script = tmp_path / "pool_job.py"
    script.write_text("ROOT = %r\nTMP = %r\n" % (ROOT, str(tmp_path)) + SCRIPT, encoding="utf-8")
    env = dict(os.environ, DRAWGEN_WORKERS="2", LOCALAPPDATA=str(tmp_path / "local"))
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    j = json.loads(r.stdout.strip().splitlines()[-1])
    assert j["from_workers"] == 4
    assert abs(j["vol"] - 4 * 4000) < 1e-6
    assert all(m > 0 for m in j["meshes"])
    assert j["interf"] == j["serial"] == [1000.0, 1000.0, 1000.0]
