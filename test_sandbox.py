from agent.sandbox import SubprocessSandbox


def test_successful_execution():
    result = SubprocessSandbox().run("print('hello')")
    assert result.success
    assert "hello" in result.stdout


def test_captures_traceback_on_error():
    result = SubprocessSandbox().run("raise ValueError('boom')")
    assert not result.success
    assert "ValueError: boom" in result.stderr


def test_enforces_timeout():
    result = SubprocessSandbox().run("while True: pass", timeout=2)
    assert not result.success
    assert result.timed_out


def test_memory_limit_kills_runaway_allocation():
    # Try to allocate ~2GB against a 64MB cap — should be killed, not hang.
    code = "x = bytearray(2 * 1024 * 1024 * 1024)"
    result = SubprocessSandbox(mem_limit_mb=64).run(code, timeout=5)
    assert not result.success
