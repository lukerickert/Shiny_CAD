"""Server routes of the Explicit tab (/api/explicit/*): explicit documents, the model .inp of the ShinyCAD source and
of the deck generator source, the deck STEP and part, run folders, deck build, solve (local, remote), job status and console, post-processing, results of the 3D view.

Folders: <project>/explicit/<document>/        project dir of the run manager (ORC**3 Project Dir)
             model/<document>.inp              .inp written from the ShinyCAD model or the deck generator
             runs/<date>_rNNN_<slug>/           run folders (run.json, model/, <job>_bNN/ build folders)
         <project>/explicit/run_history.json    finished jobs
Machine settings (host.ENV_KEYS): config.json > "explicit"; on first use the ORC**3 configuration
(%APPDATA%\\ORC3\\workspace_config.json) is read for them.
"""
import json
import os
import subprocess
import sys
import threading
import traceback
import uuid

from flask import jsonify, request

from . import constants as C
from . import deck, host, model_inp, modes, results

EXT = ".exp.json"
TEST_MODES = ["Standard Assembly Impact", "Add Infinite Rigid Floor (Drop Test)"]
JOBS = {}                 # model and view jobs: id -> {"state", "stage", "message", "error", "result"}


def register(web):
    app = web.app
    WS = host.Workspace()

    # ------------------------------------------------------------------ helpers
    def err(msg, code=400):
        return web.error(msg, code)

    def explicit_root():
        d = web.PROJECTS.dirs()
        base = os.path.dirname(d.analysis) if getattr(d, "analysis", None) else web.APP_DIR
        return os.path.join(base, "explicit")

    def doc_dir():
        return web.PROJECTS.dirs().assemblies              # the work folder of the project

    def doc_path(name):
        return os.path.join(doc_dir(), web.safe_name(name) + EXT)

    def proj_dir(name):
        return os.path.join(explicit_root(), web.safe_name(name or "explicit"))

    def model_inp_path(name):
        return os.path.join(proj_dir(name), "model", web.safe_name(name or "explicit") + ".inp")

    def load_env():
        try:
            cfg = web.load_config()
        except (OSError, ValueError):
            cfg = {}
        env = cfg.get("explicit")
        if not isinstance(env, dict):
            env = {}
            orc = os.path.join(os.environ.get("APPDATA") or "", "ORC3", "workspace_config.json")
            if os.environ.get("APPDATA") and os.path.isfile(orc):
                try:
                    with open(orc, "r") as f:
                        o = json.load(f)
                    env = {k: o[k] for k in host.ENV_KEYS if k in o}
                    env["_from"] = orc
                except (OSError, ValueError):
                    env = {}
        return {k: env.get(k, host.DEFAULTS[k]) for k in host.ENV_KEYS}, env.get("_from")

    def save_env(env):
        cfg = web.load_config()
        cur = cfg.get("explicit") if isinstance(cfg.get("explicit"), dict) else {}
        for k in host.ENV_KEYS:
            if k in env:
                cur[k] = host._coerce(k, env[k])
        cfg["explicit"] = cur
        web.save_config(cfg)

    def prepare(req):
        """Applies the machine settings, the document settings of the request and the document folders."""
        env, _src = load_env()
        WS.apply(env)
        name = req.get("name") or "explicit"
        settings = dict(req.get("settings") or {})
        doc = req.get("doc") or {}
        src = doc.get("source") or {}
        if src.get("kind") in ("shinycad", "deck"):
            settings["inp_path"] = model_inp_path(name).replace("\\", "/")
            slots = model_inp.library_slots(doc)
            extra = [s for s in (settings.get("mat_slots") or []) if s and s[1] and s[1].upper() not in {x[1] for x in slots}]
            settings["mat_slots"] = slots + extra
        elif src.get("kind") == "inp":
            settings["inp_path"] = (src.get("inp") or "").strip().strip('"')
        settings["project_dir"] = proj_dir(name).replace("\\", "/")
        WS.apply(settings)
        WS.set_history_path(os.path.join(explicit_root(), "run_history.json"))
        return name

    def open_path(path):
        os.makedirs(path, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def start_job(fn):
        jid = uuid.uuid4().hex[:10]
        job = {"state": "running", "stage": "start", "message": "", "error": None, "result": None}
        JOBS[jid] = job

        def prog(stage, message=""):
            job["stage"], job["message"] = stage, message

        def work():
            try:
                job["result"] = fn(prog)
                job["state"] = "done"
            except (model_inp.ModelError, deck.DeckError, ValueError, OSError) as e:
                job["error"], job["state"] = str(e), "error"
            except Exception as e:
                traceback.print_exc()
                job["error"], job["state"] = "%s: %s" % (e.__class__.__name__, e), "error"
        threading.Thread(target=work, daemon=True).start()
        return jid

    # ------------------------------------------------------------------ documents and settings
    @app.route("/api/explicit/meta", methods=["GET"])
    def xp_meta():
        lib = {}
        for k, v in C.MATERIAL_LIBRARY.items():
            if v:
                lib[k] = {"law": str(v.get("law", "LAW36")).upper(), "E": v.get("E"), "nu": v.get("nu"),
                          "rho": v.get("rho") * 1e12 if v.get("rho") else None}
        return jsonify({
            "library": lib, "library_none": "None (Use PrePoMax Data)",
            "analysis_modes": list(modes.ANALYSIS_MODES), "mode_help": modes.MODE_HELP,
            "mode_spec": {k: {"hide_sections": sorted(v["hide_sections"]), "rbv_values": list(v["rbv_values"]) if v["rbv_values"] else None}
                          for k, v in modes.MODE_SPEC.items()},
            "test_modes": TEST_MODES,
            "tie_modes": list(C.TIE_MODES), "tie_help": C.TIE_HELP, "tie_hint": C.TIE_HINT,
            "contact_modes": list(C.CONTACT_MODES), "contact_help": C.CONTACT_HELP, "contact_hint": C.CONTACT_HINT,
            "rbv_modes": list(C.RBV_MODES), "rbv_help": C.RBV_HELP, "rbv_hint": C.RBV_HINT,
            "fail_models": [C.FAIL_EPS, C.FAIL_JC, C.FAIL_TENS], "fail_help": C.FAIL_HELP, "fail_hint": C.FAIL_HINT,
            "lhu_easings": list(C.LHU_EASINGS), "defaults": host.DEFAULTS, "deck_default": deck.DEFAULT, "env_keys": list(host.ENV_KEYS),
            "slots_default": host.DEFAULT_SLOTS, "local": host.LOCAL, "remote": host.REMOTE,
            "version": "%s %s" % (C.WORKSPACE_NAME, C.WORKSPACE_VERSION)})

    @app.route("/api/explicit/list", methods=["GET"])
    def xp_list():
        d = doc_dir()
        names = sorted(n[:-len(EXT)] for n in os.listdir(d) if n.endswith(EXT)) if os.path.isdir(d) else []
        return jsonify(names)

    @app.route("/api/explicit/file/<name>", methods=["GET"])
    def xp_get(name):
        try:
            with open(doc_path(name), "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except (OSError, ValueError) as e:
            return err("cannot read explicit document %s: %s" % (name, e), 404)

    @app.route("/api/explicit/file/<name>", methods=["PUT"])
    def xp_put(name):
        a = request.get_json(force=True)
        if not isinstance(a, dict) or "source" not in a:
            return err("explicit document expected")
        os.makedirs(doc_dir(), exist_ok=True)
        p = doc_path(name)
        tmp = p + web._tmp_ext()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(a, f)
        web._replace(tmp, p)
        return jsonify({"ok": True, "path": p})

    @app.route("/api/explicit/env", methods=["GET"])
    def xp_env():
        env, src = load_env()
        WS.apply(env)
        exes = {}
        for n in ("starter", "engine", "anim_to_vtk", "th_to_csv"):
            exe = WS._or_exe(n)
            found = exe if os.path.isabs(exe) and os.path.isfile(exe) else None
            if not found and not os.path.isabs(exe):
                import shutil as _sh
                found = _sh.which(exe)
            exes[n] = {"exe": exe, "found": found}
        return jsonify({"env": env, "from_orc3": src, "executables": exes,
                        "pvbatch": WS._find_pvbatch(), "paraview": WS._find_paraview()})

    @app.route("/api/explicit/env", methods=["PUT"])
    def xp_env_put():
        save_env(request.get_json(force=True) or {})
        return xp_env()

    @app.route("/api/explicit/folders", methods=["POST"])
    def xp_folders():
        name = (request.get_json(force=True) or {}).get("name") or "explicit"
        return jsonify({"project_dir": proj_dir(name), "model_inp": model_inp_path(name), "root": explicit_root(),
                        "model_exists": os.path.isfile(model_inp_path(name))})

    # ------------------------------------------------------------------ model
    @app.route("/api/explicit/model", methods=["POST"])
    def xp_model():
        """{"name", "doc"} -> {"job"}: meshes the ShinyCAD model (or the deck generator model) and writes
        model/<name>.inp."""
        req = request.get_json(force=True)
        name = req.get("name") or "explicit"
        doc = req.get("doc") or {}
        src = doc.get("source") or {}
        if src.get("kind") == "deck":
            def fn_deck(prog):
                return deck.build(doc, model_inp_path(name), title="SHINYCAD %s (deck generator)" % name, progress=prog)
            return jsonify({"job": start_job(fn_deck)})
        if not src.get("name"):
            return err("choose the geometry (assembly or part)")
        sources = web._asm_sources()

        def fn(prog):
            asm = web._fea_asm({"source": {"type": src.get("type") or "assembly", "name": src.get("name")}})
            p = model_inp_path(name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            wd = os.path.join(proj_dir(name), "model", "mesh")
            return model_inp.build(doc, asm, sources, wd, p, title="SHINYCAD %s (%s %s)" % (name, src.get("type"), src.get("name")),
                                   progress=prog)
        return jsonify({"job": start_job(fn)})

    @app.route("/api/explicit/deck/check", methods=["POST"])
    def xp_deck_check():
        """{"deck"} -> parts (polygons of the plates), sections, errors and warnings of the deck generator model."""
        return jsonify(deck.check((request.get_json(force=True) or {}).get("deck") or {}))

    @app.route("/api/explicit/deck/step", methods=["POST"])
    def xp_deck_step():
        """{"name", "doc"} -> {"job"}: STEP of the deck structure in the step folder of the project
        (<name>_deck.step, <name>_deck_model.json) and the ShinyCAD part <name>_deck (one surface body per component)."""
        req = request.get_json(force=True)
        name = web.safe_name(req.get("name") or "explicit")
        doc = req.get("doc") or {}

        def fn(prog):
            folder = web.PROJECTS.dirs().step or os.path.join(proj_dir(name), "model")
            out = os.path.join(folder, name + "_deck.step")
            res = deck.step(doc, out, progress=prog)
            prog("part", "Writing the part")
            pname = name + "_deck"
            path = web._part_path(pname)
            rec = deck.part_record(pname, out, res["components"])
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old = json.load(f)
            except (OSError, ValueError):
                old = None
            if isinstance(old, dict) and old.get("features"):
                same = os.path.normcase(os.path.abspath(out))
                keep = [f for f in old["features"] if not (f.get("type") == "surf_import" and
                        os.path.normcase(os.path.abspath(str(f.get("path") or ""))) == same)]
                nxt = int(old.get("next") or 1)
                for f in rec["features"]:
                    f["id"] = "f%d" % nxt
                    nxt += 1
                old["features"] = rec["features"] + keep
                old["next"] = nxt
                rec = old
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + web._tmp_ext()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rec, f)
            web._replace(tmp, path)
            res["part"] = pname
            return res
        return jsonify({"job": start_job(fn)})

    @app.route("/api/explicit/inp_view", methods=["POST"])
    def xp_inp_view():
        """{"path"} -> {"job"}: view data of the mesh of an .inp."""
        path = ((request.get_json(force=True) or {}).get("path") or "").strip().strip('"')
        if not os.path.isfile(path):
            return err("file not found: %s" % path)

        def fn(prog):
            from . import meshview
            prog("read", "Reading %s" % os.path.basename(path))
            m = meshview.read_inp(path)
            pl = meshview.payload(m["xyz"], m["cells"])
            pl["part_names"] = ["%s (%s)" % p for p in m["parts"]]
            return {"payload": pl, "summary": {"nodes": int(len(m["xyz"])), "elements": int(sum(len(c[1]) for c in m["cells"])),
                                               "parts": [{"elset": p[0], "type": p[1]} for p in m["parts"]]}}
        return jsonify({"job": start_job(fn)})

    @app.route("/api/explicit/job/<jid>", methods=["GET"])
    def xp_job(jid):
        j = JOBS.get(jid)
        if j is None:
            return err("unknown job", 404)
        out = {k: j[k] for k in ("state", "stage", "message", "error")}
        if j["state"] != "running":
            out["result"] = j["result"]
            JOBS.pop(jid, None)
        return jsonify(out)

    # ------------------------------------------------------------------ runs
    @app.route("/api/explicit/runs", methods=["POST"])
    def xp_runs():
        prepare(request.get_json(force=True) or {})
        return jsonify({"runs": WS._run_list(), "project_dir": WS.project_dir.get()})

    @app.route("/api/explicit/run/new", methods=["POST"])
    def xp_run_new():
        req = request.get_json(force=True) or {}
        prepare(req)
        WS.run_desc.set((req.get("description") or "").strip())
        WS.run_notes.set((req.get("notes") or "").strip())
        d = WS.cmd_new_run()
        if not d:
            return err("run not created (see the console)")
        return jsonify({"run": d.replace("\\", "/"), "runs": WS._run_list()})

    @app.route("/api/explicit/run/clean", methods=["POST"])
    def xp_run_clean():
        req = request.get_json(force=True) or {}
        d = req.get("path") or ""
        if not os.path.isdir(d):
            return err("run folder not found: %s" % d)
        victims, size, per_dir = WS._clean_victims(d)
        if not req.get("confirm"):
            return jsonify({"files": len(victims), "mb": size, "folders": per_dir})
        n = WS.cmd_clean_run(d)
        return jsonify({"deleted": n})

    @app.route("/api/explicit/run/settings", methods=["POST"])
    def xp_run_settings():
        """Settings of the last build of a run (run.json)."""
        d = (request.get_json(force=True) or {}).get("path") or ""
        try:
            with open(os.path.join(d, "run.json"), "r") as f:
                meta = json.load(f)
            snap = meta["builds"][-1]["settings"]
        except Exception:
            return err("no recorded build settings in this run")
        return jsonify({"settings": snap})

    @app.route("/api/explicit/open_folder", methods=["POST"])
    def xp_open_folder():
        p = (request.get_json(force=True) or {}).get("path") or ""
        if not p:
            return err("no folder")
        try:
            open_path(p)
        except Exception as e:
            return err("cannot open %s: %s" % (p, e))
        return jsonify({"ok": True, "path": p})

    # ------------------------------------------------------------------ build and solve
    @app.route("/api/explicit/build", methods=["POST"])
    def xp_build():
        req = request.get_json(force=True) or {}
        prepare(req)
        if not os.path.isfile(WS.inp_path.get()):
            return err("the source .inp does not exist: %s%s" % (WS.inp_path.get(),
                       " (Write .inp first)" if ((req.get("doc") or {}).get("source") or {}).get("kind") == "shinycad" else ""))
        if not WS.execute_build():
            return err("a build is running")
        return jsonify({"ok": True})

    @app.route("/api/explicit/list_parts", methods=["POST"])
    def xp_list_parts():
        prepare(request.get_json(force=True) or {})
        WS.cmd_list_parts()
        return jsonify({"ok": True})

    @app.route("/api/explicit/solve", methods=["POST"])
    def xp_solve():
        """{"name", "doc", "settings", "mode": "run" | "starter"}; settings.rad_target is the deck."""
        req = request.get_json(force=True) or {}
        prepare(req)
        if req.get("mode") == "starter":
            WS.cmd_run_starter()
        else:
            WS.cmd_run()
        return jsonify({"ok": True})

    @app.route("/api/explicit/kill", methods=["POST"])
    def xp_kill():
        req = request.get_json(force=True) or {}
        env, _s = load_env()
        WS.apply(env)
        if req.get("env") in (host.LOCAL, host.REMOTE):
            WS.run_target.set(req["env"])
        WS.cmd_kill()
        return jsonify({"ok": True})

    @app.route("/api/explicit/queue", methods=["POST"])
    def xp_queue():
        req = request.get_json(force=True) or {}
        prepare(req)
        op = req.get("op")
        if op == "add":
            WS._queue_add()
        elif op == "remove":
            WS._queue_remove(req.get("key") or "")
        elif op == "clear":
            WS._queue_clear()
        return jsonify(WS.status())

    @app.route("/api/explicit/server", methods=["POST"])
    def xp_server():
        req = request.get_json(force=True) or {}
        env, _s = load_env()
        WS.apply(env)
        op = req.get("op")
        if not WS.ssh_host.get().strip():
            return err("Server (user@host) is empty")
        if op == "show":
            WS.log_msg("Querying server queue...")
            WS.run_task("Show queue", WS._server_queue_show_thread)
        elif op == "clear":
            WS.log_msg("Clearing server queue (kill running + flush list)...")
            WS.run_task("Clear server queue", WS._server_queue_clear_thread)
        elif op == "shutdown":
            WS.cmd_shutdown()
        return jsonify({"ok": True})

    @app.route("/api/explicit/status", methods=["GET"])
    def xp_status():
        since = int(request.args.get("since") or 0)
        out = WS.status()
        out["log"] = WS.log_since(since)
        out["log_seq"] = WS.log_seq
        return jsonify(out)

    @app.route("/api/explicit/console/clear", methods=["POST"])
    def xp_console_clear():
        with WS._log_lock:
            WS.logs = []
        return jsonify({"log_seq": WS.log_seq})

    # ------------------------------------------------------------------ post-processing
    @app.route("/api/explicit/post", methods=["POST"])
    def xp_post():
        """{"op", "job", "folder", "name", "doc", "settings"}: salvage, plot_ke, assets, extract, images, paraview,
        macro, min_dt."""
        req = request.get_json(force=True) or {}
        prepare(req)
        op, job, folder = req.get("op"), req.get("job") or "", req.get("folder") or ""
        if op not in ("macro", "extract") and (not job or not os.path.isdir(folder)):
            return err("choose a job with an existing run folder")
        if op == "salvage":
            WS.log_msg(f"\n--- SALVAGING RESULTS: {job} ---")
            WS.run_task("Salvage", WS._salvage_thread, job, folder)
        elif op == "plot_ke":
            WS.run_task("Plot KE", WS._plot_ke, folder, job, True, True)
        elif op == "assets":
            WS._write_pv_assets(folder, job)
        elif op == "extract":
            WS.run_task("Extract strains", WS.cmd_extract_strains, folder)
        elif op == "images":
            WS.run_task("PV images", WS._render_pv_images, folder, job, True)
        elif op == "paraview":
            WS.cmd_open_paraview(job, folder)
        elif op == "macro":
            WS.cmd_install_pv_macro()
        elif op == "min_dt":
            return jsonify({"offer": WS._offer_min_dt_from_out(os.path.join(folder, f"{job}_0000.out"), job)})
        else:
            return err("unknown operation %s" % op)
        return jsonify({"ok": True})

    @app.route("/api/explicit/results", methods=["POST"])
    def xp_results():
        """{"folder", "job"} -> frames, KE/IE curve, principal strain summary, files."""
        req = request.get_json(force=True) or {}
        folder, job = req.get("folder") or "", req.get("job") or ""
        if not os.path.isdir(folder):
            return err("run folder not found: %s" % folder)
        out = {"folder": folder, "job": job, "jobs": results.jobs(folder)}
        fr = results.frames(folder, job) if job else []
        out["frames"] = [{"time": e["time"], "name": os.path.basename(e["file"])} for e in fr]
        csv_path, parsed = WS._find_th_csv(folder, job) if job else (None, None)
        if parsed:
            t, ke, ie, note = parsed
            out["energy"] = {"t": t, "ke": ke, "ie": ie, "note": note, "csv": os.path.basename(csv_path)}
        sp = os.path.join(folder, "principal_strains_summary.csv")
        if os.path.isfile(sp):
            import csv as _csv
            with open(sp, newline="") as f:
                out["strains"] = list(_csv.reader(f))
        names = sorted(os.listdir(folder))
        out["files"] = [n for n in names if n.startswith(job) and n.endswith((".png", ".csv", ".out", ".txt", ".json", ".py"))] if job else []
        out["outs"] = {}
        for k in ("0000", "0001"):
            p = os.path.join(folder, f"{job}_{k}.out")
            if job and os.path.isfile(p):
                out["outs"][k] = os.path.getsize(p)
        return jsonify(out)

    @app.route("/api/explicit/geometry", methods=["POST"])
    def xp_geometry():
        req = request.get_json(force=True) or {}
        folder, job = req.get("folder") or "", req.get("job") or ""
        try:
            rigid = WS._harvest_rigid_pids(folder, job)
            return jsonify(results.geometry(folder, job, rigid))
        except (OSError, ValueError) as e:
            return err(str(e))

    @app.route("/api/explicit/frame", methods=["POST"])
    def xp_frame():
        req = request.get_json(force=True) or {}
        folder, job = req.get("folder") or "", req.get("job") or ""
        try:
            rigid = WS._harvest_rigid_pids(folder, job)
            return jsonify(results.frame(folder, job, int(req.get("index") or 0), req.get("field") or "", rigid))
        except (OSError, ValueError, KeyError) as e:
            return err(str(e))

    @app.route("/api/explicit/text", methods=["POST"])
    def xp_text():
        """Text of a file of a run folder (.out, settings report, console.log), the last max_kb kB."""
        req = request.get_json(force=True) or {}
        p = req.get("path") or ""
        if not os.path.isfile(p) or os.path.splitext(p)[1].lower() not in (".out", ".txt", ".log", ".csv", ".json", ".rad", ".inp"):
            return err("file not found: %s" % p)
        n = int(req.get("max_kb") or 400) * 1024
        size = os.path.getsize(p)
        with open(p, "rb") as f:
            if size > n:
                f.seek(size - n)
            data = f.read().decode("utf-8", "replace")
        return jsonify({"text": data, "size": size, "cut": size > n})

    return WS
