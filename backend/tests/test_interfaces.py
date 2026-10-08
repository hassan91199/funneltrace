from funneltrace.interfaces import CrmSync, LeadLLM
from tests.fakes import FakeCrm


class FakeLLM:
    model = "fake"

    def complete_json(self, system, user, schema):
        return {}

    def complete_text(self, system, user):
        return ""


def test_fakes_satisfy_the_protocols():
    assert isinstance(FakeLLM(), LeadLLM)
    assert isinstance(FakeCrm(), CrmSync)
