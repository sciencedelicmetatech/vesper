from vesper.log import MemoryLog


def test_chain_valid():
    log = MemoryLog()
    for i in range(10):
        log.append({"i": i})
    assert log.verify()
    assert len(log) == 10


def test_tamper_detection():
    log = MemoryLog()
    for i in range(5):
        log.append({"i": i})
    log._entries[2].payload["i"] = 99
    assert not log.verify()


def test_head_is_deterministic():
    log1 = MemoryLog()
    log2 = MemoryLog()
    for i in range(10):
        log1.append({"i": i})
        log2.append({"i": i})
    assert log1.head == log2.head


def test_empty_log():
    log = MemoryLog()
    assert log.head is None
    assert log.verify()