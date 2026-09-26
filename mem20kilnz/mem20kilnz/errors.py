"""Error types and the JSON-RPC status codes the engine reports.

The numeric codes are the engine's own (src/core/rpc.hpp). They are restated
here rather than imported so this package stays standard-library only, and a
mismatch is caught by tests/test_rpc.py asserting against a live engine.
"""


class KilnError(RuntimeError):
    """A JSON-RPC level failure: bad frame, unknown method, bad params, io."""

    def __init__(self, code: int, message: str, data=None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


class OpFailed(KilnError):
    """An op ran and reported failure. Carries the op's own message in `data`."""

    def __init__(self, message: str, data=None):
        super().__init__(ERR_OP_FAILED, message, data)


class EngineMissing(KilnError):
    """The native engine is not built. Never silently degraded: say so and how to fix."""

    def __init__(self, path: str, detail: str = ""):
        msg = (
            f"the KilNZ engine binary was not found (looked at {path}). "
            "Build it with `mem20kilnz doctor --build` or "
            "`python -m mem20kilnz build-engine`."
        )
        if detail:
            msg += f" ({detail})"
        super().__init__(ERR_INTERNAL, msg)
        self.path = path


class ValidationFailed(KilnError):
    """The validation gate found problems. `findings` is the machine-readable list."""

    def __init__(self, findings):
        super().__init__(ERR_OP_FAILED, f"{len(findings)} validation finding(s)")
        self.findings = findings


ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_OP_FAILED = -32000
ERR_NO_SCENE = -32001
ERR_NOT_FOUND = -32002
ERR_NO_CAMERA = -32003
ERR_IO = -32004
ERR_BAD_SAMPLES = -32005
ERR_UNSUPPORTED = -32006

SAMPLES_MIN = 1
SAMPLES_MAX = 16
SAMPLES_DEFAULT = 2
