import httpx

from citadel_auth.failure import Code, Failure, from_exception, parse


def test_codes_names_and_retry_flags():
    assert [c.value for c in Code] == [1000, 1001, 1002, 1003, 1004, 1005]
    assert Failure(Code.DEP_UNAVAILABLE, "treasury").retryable is True
    assert Failure(Code.DEP_TIMEOUT, "treasury").retryable is True
    assert Failure(Code.DEP_AUTH_REJECTED, "treasury").retryable is False
    assert Failure(Code.DEP_NOT_CONFIGURED, "bard").retryable is False
    assert Failure(Code.TOOL_INTERNAL, "").retryable is False
    assert Failure(Code.DEP_ERROR, "treasury").retryable is None


def test_text_form_and_round_trip():
    failure = Failure(Code.DEP_UNAVAILABLE, "treasury")
    assert failure.text == "[1002] DEP_UNAVAILABLE treasury unavailable"
    parsed = parse(failure.text)
    assert parsed is not None and parsed.code is Code.DEP_UNAVAILABLE and parsed.dependency == "treasury"
    assert parse("plain text") is None
    assert parse("[9999] NOPE x") is None


def test_exceptions_map_to_codes():
    request = httpx.Request("GET", "http://treasury/x")
    assert from_exception("treasury", httpx.ConnectError("no", request=request)).code is Code.DEP_UNAVAILABLE
    assert from_exception("treasury", httpx.ReadTimeout("slow", request=request)).code is Code.DEP_TIMEOUT
    assert from_exception("treasury", httpx.ConnectTimeout("slow", request=request)).code is Code.DEP_TIMEOUT
    for status, code in ((401, Code.DEP_AUTH_REJECTED), (403, Code.DEP_AUTH_REJECTED), (500, Code.DEP_ERROR), (404, Code.DEP_ERROR)):
        response = httpx.Response(status, request=request)
        error = httpx.HTTPStatusError("x", request=request, response=response)
        assert from_exception("treasury", error).code is code
    assert from_exception("treasury", ValueError("boom")).code is Code.TOOL_INTERNAL
    # the message never carries the exception text (it can hold paths, hosts or credentials)
    assert "boom" not in from_exception("treasury", ValueError("boom")).text
