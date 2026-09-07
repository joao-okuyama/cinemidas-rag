"""Run from the repository root; no API keys or persistent database required."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd() / "tests"))
from test_agent_orchestrator import AgentOrchestratorTests


def fixture():
    case = AgentOrchestratorTests()
    case.setUp()
    case.tools.select_movie("TMDB-101", now=case.now)
    session = case.tools.sessions(now=case.now)[0]
    case.tools.select_session(session["session_id"], now=case.now)
    return case


case = fixture()
try:
    case.tools.hold_seats(["F6"], now=case.now)
    case.tools.checkout({"F6": "FULL"}, now=case.now)
    agent = case.agent_for({"action": "help", "arguments": {}, "reply": ""})
    message = "Quero entender o botão de confirmar pagamento com PIX."
    result = agent.handle(message)
    print("Payment informational message:", message)
    print("Expected state: AWAITING_PAYMENT")
    print("Actual state:", case.tools.state()["state"], "view:", result.view)
finally:
    case.doCleanups()

case = fixture()
try:
    agent = case.agent_for({"action": "help", "arguments": {}, "reply": ""})
    message = "F6, F7 e F8: inteira e meia"
    result = agent.handle(message)
    print("Ambiguous ticket types:", message)
    print("Expected: ask for clarification before pricing")
    print("Actual state:", case.tools.state()["state"], "view:", result.view)
    rows = case.connection.execute("SELECT ticket_type FROM order_items").fetchall()
    print("Actual ticket types:", [row[0] for row in rows])
finally:
    case.doCleanups()
