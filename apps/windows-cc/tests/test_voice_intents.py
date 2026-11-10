import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

from voice_intents import match, announce  # noqa: E402


class IntentTests(unittest.TestCase):
    def role(self, text):
        m = match(text)
        return m.get("role") if m["intent"] == "agent" else m["intent"]

    def test_build_commands(self):
        for t in ("Jarvis, build me a todo app", "hey jarvis make a landing page for my clinic",
                  "create a python script that renames photos", "Please build a simple hello-world HTML page called test-site",
                  "jarvis can you write a calculator in html"):
            self.assertEqual(self.role(t), "builder", t)

    def test_goal_strips_wake_word(self):
        m = match("Hey Jarvis, build me a todo app")
        self.assertEqual(m["goal"], "Build me a todo app")

    def test_research_browser_system_task_memory_coding(self):
        self.assertEqual(self.role("Jarvis research the best budget laptops"), "research")
        self.assertEqual(self.role("look up Patna weather"), "research")
        self.assertEqual(self.role("browse python.org and tell me the latest version"), "browser")
        self.assertEqual(self.role("check system health"), "system")
        self.assertEqual(self.role("list my skills"), "task")
        self.assertEqual(self.role("remember that my clinic opens at 9"), "memory")
        self.assertEqual(self.role("review the code in apps"), "coding")

    def test_named_agent(self):
        m = match("Jarvis start research agent find GST rates for medicines")
        self.assertEqual((m["role"], m["goal"]), ("research", "Find GST rates for medicines"))
        m = match("ask the builder to make a portfolio site")
        self.assertEqual((m["role"], m["goal"]), ("builder", "Make a portfolio site"))
        m = match("builder: snake game in html")
        self.assertEqual(m["role"], "builder")
        self.assertEqual(match("stop builder")["intent"], "stop_agent")

    def test_trading_reserved_not_routed_to_agents(self):
        self.assertEqual(match("Jarvis start trading")["intent"], "start_trading")
        self.assertEqual(match("jarvis stop trading")["intent"], "stop_trading")
        self.assertEqual(match("start trading on my computer")["intent"], "start_trading")

    def test_chat_fallthrough(self):
        for t in ("what time is it", "how are you jarvis", "Jarvis, tell me a joke", "", "who built the taj mahal", "make sure the door is locked", "set up a meeting tomorrow", "create a reminder at 5"):
            self.assertEqual(match(t)["intent"], "chat", t)

    def test_announce(self):
        self.assertEqual(announce("Builder", "building", "Build me a todo app"),
                         "On it. Builder is building: Build me a todo app")


if __name__ == "__main__":
    unittest.main()
