import pytest
import uuid
from qns.entity.node.qnode import QNode
from qns.models.qubit import Qubit
from qns.models.epr.werner import WernerStateEntanglement
from qns.simulator.simulator import Simulator
from qns.entity.memory.memory import QuantumMemory
from qns.entity.qchannel.qchannel import QuantumChannel, RecvQubitPacket
from qns.models.delay.constdelay import ConstantDelayModel
from qns.network.protocol.link_layer import LinkLayer
from qns.network.protocol.proactive_forwarder import ProactiveForwarder

light_speed = 2 * 10**5 # km/s

def test_write_and_read_with_path_and_key():
    mem = QuantumMemory("mem", capacity=2, decoherence_rate=1)
    node = QNode("n1")
    node.set_memory(mem)
    node.add_apps(LinkLayer())
    node.add_apps(ProactiveForwarder())

    sim = Simulator(0, 10)
    node.install(sim)

    epr = WernerStateEntanglement(name="epr1")
    epr.creation_time = sim.tc
    epr.src = node
    epr.dst = QNode("peer")
    key = "n1_peer_0_0"

    # First allocate memory with path ID
    addr = mem.allocate(path_id=0)
    assert addr != -1
    mem._storage[addr][0].active = key

    # Now write with path_id and key
    result = mem.write(epr, path_id=0, key=key)
    assert result is not None
    assert result.addr == addr

    # Should fail to write another one in the same slot
    epr2 = WernerStateEntanglement(name="epr2")
    epr2.creation_time = sim.tc
    epr2.src = node
    epr2.dst = QNode("peer2")
    assert mem.write(epr2, path_id=0, key=key) is None

    # Should be able to read it
    qubit, data = mem.read(key="epr1")   # destructive reading
    assert data.name == "epr1"
    assert mem._usage == 0
    
    res = mem.read(address=qubit.addr)
    assert res is None


def test_channel_qubit_assignment_and_search():
    mem = QuantumMemory("mem", capacity=3, decoherence_rate=1)
    node = QNode("n2")
    node.set_memory(mem)
    node.add_apps(LinkLayer())
    node.add_apps(ProactiveForwarder())

    sim = Simulator(0, 10)
    node.install(sim)

    ch = QuantumChannel(
        "qch", 
        { "node1": "S", "node2":"R", "capacity": 1, "parameters": {"length": 10, "delay": 10 / light_speed} }
        )
    addr = mem.assign(ch)
    assert addr != -1

    # Assigned qubit should now be returned by get_channel_qubits
    qubits = mem.get_channel_qubits("qch")
    assert len(qubits) == 1
    q, data = qubits[0]
    assert q.qchannel == ch
    assert data is None


def test_decoherence_event_removes_qubit():
    mem = QuantumMemory("mem", capacity=1, decoherence_rate=1)
    
    ch = QuantumChannel(
        "qch", 
        { "node1": "S", "node2":"R", "capacity": 1, "parameters": {"length": 10, "delay": 10 / light_speed} }
        )
    qubit_assign = mem.assign(ch)

    node = QNode("n3")
    node.set_memory(mem)
    node.add_apps(LinkLayer())
    node.add_apps(ProactiveForwarder())

    sim = Simulator(0, 5)
    node.install(sim)

    q = WernerStateEntanglement(name="epr3", fidelity=1.0)
    q.creation_time = sim.tc
    q.src = node
    q.dst = QNode("peer")
    mem.write(q)

    # Expect it to decohere at t=1.0
    sim.run()

    res = mem.get("epr3")
    assert res is None


def test_memory_clear_and_deallocate():
    mem = QuantumMemory("mem", capacity=2, decoherence_rate=1)
    node = QNode("n4")
    node.set_memory(mem)
    node.add_apps(LinkLayer())
    node.add_apps(ProactiveForwarder())

    sim = Simulator(0, 5)
    node.install(sim)

    for i in range(2):
        q = WernerStateEntanglement(name=f"epr{i}", fidelity=1.0)
        q.creation_time = sim.tc
        q.src = node
        q.dst = QNode("peer")
        assert mem.write(q)

    assert mem.is_full()
    mem.clear()
    assert not mem.is_full()

    # Test deallocate
    idx = mem.allocate(path_id=7)
    assert idx != -1
    assert mem.deallocate(idx)
    assert not mem.deallocate(999)  # invalid


def test_qubit_reservation_behavior():
    mem = QuantumMemory("mem", capacity=2, decoherence_rate=1)
    node = QNode("n5")
    node.set_memory(mem)
    node.add_apps(LinkLayer())
    node.add_apps(ProactiveForwarder())

    sim = Simulator(0, 5)
    node.install(sim)

    idx1 = mem.allocate(path_id=42)
    assert idx1 != -1
    q1 = mem._storage[idx1][0]
    q1.active = "n5_n6_42_" + str(idx1)

    epr = WernerStateEntanglement(name="eprX")
    epr.creation_time = sim.tc
    epr.src = node
    epr.dst = QNode("n6")

    # Must match on both path_id and key
    result = mem.write(epr, path_id=42, key=q1.active)
    assert result is not None
    assert result.addr == idx1
