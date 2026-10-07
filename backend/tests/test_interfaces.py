from funneltrace.interfaces import CrmSync, LeadLLM


class FakeLLM:
    model = "fake"

    def complete_json(self, system, user, schema):
        return {}

    def complete_text(self, system, user):
        return ""


class FakeCrm:
    def upsert_contact(self, contact):
        return "crm-1"


def test_fakes_satisfy_the_protocols():
    assert isinstance(FakeLLM(), LeadLLM)
    assert isinstance(FakeCrm(), CrmSync)
