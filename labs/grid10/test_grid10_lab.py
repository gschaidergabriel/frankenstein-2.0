from __future__ import annotations
import multiprocessing as mp, os, signal, tempfile, time, unittest
from pathlib import Path
from grid10_lab import Grid10Error, Grid10LabFabric

def join_worker(db,node,ready):
    Grid10LabFabric(db).join(node); ready.put((node,os.getpid()))

def crash_claim(db,ready):
    f=Grid10LabFabric(db); f.join("node-crash"); f.claim("t-crash","node-crash",f.snapshot()["epoch"]); ready.set(); time.sleep(30)

class Grid10LabTests(unittest.TestCase):
    def setUp(self): self.t=tempfile.TemporaryDirectory(); self.db=Path(self.t.name)/"grid.sqlite"; self.f=Grid10LabFabric(self.db)
    def tearDown(self): self.t.cleanup()
    def test_ten_real_processes_join_same_wal_fabric(self):
        q=mp.Queue(); ps=[mp.Process(target=join_worker,args=(str(self.db),f"node-{i}",q)) for i in range(10)]
        [p.start() for p in ps]; observed=[q.get(timeout=5) for _ in ps]; [p.join(5) for p in ps]
        self.assertTrue(all(p.exitcode==0 for p in ps)); s=self.f.snapshot(); self.assertEqual(len(s["nodes"]),10); self.assertEqual(len({pid for _,pid in observed}),10)
    def test_single_commit_authority_and_readback(self):
        self.f.join("worker"); self.f.join("coord"); self.f.seed("t1","scope",{"q":"lab"}); self.f.claim("t1","worker",self.f.snapshot()["epoch"]); self.f.emit("t1","worker",{"ok":1}); l,t=self.f.lease("scope","coord"); done=self.f.commit("scope",l,t,self.f.snapshot()["epoch"]); self.assertEqual(len(done),1); r=Grid10LabFabric(self.db).snapshot(); self.assertEqual(r["tasks"][0]["status"],"DONE"); self.assertEqual(r["committed"][0]["source_node_id"],"worker")
    def test_stale_epoch_and_wrong_token_fail_closed(self):
        self.f.join("n"); self.f.seed("t","s",{}); stale=self.f.snapshot()["epoch"]; self.f.heartbeat("n")
        with self.assertRaisesRegex(Grid10Error,"TASK_CLAIM_CAS_FAILED"): self.f.claim("t","n",stale)
        self.f.claim("t","n",self.f.snapshot()["epoch"]); self.f.emit("t","n","ok"); l,_=self.f.lease("s","n")
        with self.assertRaisesRegex(Grid10Error,"LEASE_TOKEN_MISMATCH"): self.f.commit("s",l,"wrong",self.f.snapshot()["epoch"])
    def test_real_sigkill_independent_replacement_and_readback(self):
        self.f.seed("t-crash","recover",{}); ready=mp.Event(); p=mp.Process(target=crash_claim,args=(str(self.db),ready)); p.start(); self.assertTrue(ready.wait(5)); os.kill(p.pid,signal.SIGKILL); p.join(5); self.assertNotEqual(p.exitcode,0)
        self.assertEqual(self.f.recover_stale(0.0),["t-crash"]); self.f.join("replacement"); self.f.claim("t-crash","replacement",self.f.snapshot()["epoch"]); self.f.emit("t-crash","replacement",{"recovered":True}); self.f.join("coord"); l,t=self.f.lease("recover","coord"); self.assertEqual(len(self.f.commit("recover",l,t,self.f.snapshot()["epoch"])),1); r=Grid10LabFabric(self.db).snapshot(); self.assertEqual(r["committed"][0]["source_node_id"],"replacement")
    def test_restart_invalidates_old_lease(self):
        self.f.join("n"); l,t=self.f.lease("s","n"); self.f.restart_generation()
        with self.assertRaisesRegex(Grid10Error,"LEASE_NOT_VALID"): self.f.commit("s",l,t,self.f.snapshot()["epoch"])

if __name__=="__main__": unittest.main(verbosity=2)
