from swebench_interview_cases.generator import GenerationRequest, generate_case


class FakeModel:
    def __init__(self):
        self.call = None

    def generate(self, *, role, payload):
        self.call = (role, payload)
        return {"status": "draft"}


def test_generation_uses_protocol_boundary_and_detaches_mapping():
    model = FakeModel()
    payload = {"instance": "case-1"}
    result = generate_case(model, GenerationRequest(role="generator", payload=payload))
    assert result == {"status": "draft"}
    assert model.call == ("generator", payload)


def test_generation_rejects_non_object_result():
    class BadModel:
        def generate(self, *, role, payload):
            return []

    try:
        generate_case(BadModel(), GenerationRequest(role="generator", payload={}))
    except TypeError as error:
        assert "JSON object" in str(error)
    else:
        raise AssertionError("expected a TypeError")
