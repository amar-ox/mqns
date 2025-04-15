import logging

from qns.network.route.dijkstra import DijkstraRouteAlgorithm
from qns.simulator.simulator import Simulator
from qns.network import QuantumNetwork, TimingModeEnum
import qns.utils.log as log
from qns.utils.rnd import set_seed
from qns.network.protocol.proactive_routing import ProactiveRouting
from qns.network.protocol.link_layer import LinkLayer
from qns.network.protocol.proactive_routing_controller import ProactiveRoutingControllerApp
from qns.network.topology.customtopo import CustomTopology
import numpy as np

from qns.entity.monitor import Monitor
from qns.entity.qchannel import RecvQubitPacket
from qns.entity.cchannel import RecvClassicPacket


log.logger.setLevel(logging.DEBUG)


light_speed = 2 * 10**5 # km/s

def drop_rate(length):
    # drop 0.2 db/KM
    return 10 ** (- (0.2 * length) / 10)

# constrains
init_fidelity = 0.99
t_coherence = 0.01    # in sec = 10ms
p_swap = 0.5

# set a fixed random seed
set_seed(150)
s = Simulator(0, 1 + 5e-06, accuracy=1000000)
log.install(s)

ch_1 = 32
ch_2 = 18
ch_3 = 35
ch_4 = 16
ch_5 = 24

# For LSYNC
t_slot = t_coherence - 2*(ch_1 + ch_2 + ch_3 + ch_4 + ch_5) / light_speed

# For SYNC
t_ext = 10*(ch_1 + ch_2 + ch_3 + ch_4 + ch_5) / light_speed
t_int = 2*(ch_1 + ch_2 + ch_3 + ch_4 + ch_5) / light_speed

print(f"LSYNC: t_slot={t_slot} sec")
print(f"SYNC: t_ext={t_ext} sec, t_int={t_int} sec, t_slot={t_ext+t_int} sec")

topo_6_nodes = {
    "qnodes": [
        {
            "name": "S",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
            },
            "apps": [LinkLayer(attempt_rate=1e6, init_fidelity=init_fidelity), ProactiveRouting()]
        },
        {
            "name": "R1",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
            },
            "apps": [LinkLayer(attempt_rate=1e6, init_fidelity=init_fidelity), ProactiveRouting(ps=p_swap)]
        },
        {
            "name": "R2",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
            },
            "apps": [LinkLayer(attempt_rate=1e6, init_fidelity=init_fidelity), ProactiveRouting(ps=p_swap)]
        },
        {
            "name": "R3",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
            },
            "apps": [LinkLayer(attempt_rate=1e6, init_fidelity=init_fidelity), ProactiveRouting(ps=p_swap)]
        },
        {
            "name": "R4",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
            },
            "apps": [LinkLayer(attempt_rate=1e6, init_fidelity=init_fidelity), ProactiveRouting(ps=p_swap)]
        },
        {
            "name": "D",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
            },
            "apps": [LinkLayer(attempt_rate=1e6, init_fidelity=init_fidelity), ProactiveRouting()]
        }
    ],
    "qchannels": [
        { "node1": "S", "node2":"R1", "capacity": 5, "parameters": {"length": ch_1, "delay": ch_1 / light_speed, "drop_rate": drop_rate(ch_1)} },
        { "node1": "R1", "node2":"R2", "capacity": 5, "parameters": {"length": ch_2, "delay": ch_2 / light_speed, "drop_rate": drop_rate(ch_2)} },
        { "node1": "R2", "node2":"R3", "capacity": 5, "parameters": {"length": ch_3, "delay": ch_3 / light_speed, "drop_rate": drop_rate(ch_3)} },
        { "node1": "R3", "node2":"R4", "capacity": 5, "parameters": {"length": ch_4, "delay": ch_4 / light_speed, "drop_rate": drop_rate(ch_4)} },
        { "node1": "R4", "node2":"D", "capacity": 5, "parameters": {"length": ch_5, "delay": ch_5 / light_speed, "drop_rate": drop_rate(ch_5)} }
    ],
    "cchannels": [
        { "node1": "S", "node2":"R1", "parameters": {"length": ch_1, "delay": ch_1 / light_speed} },
        { "node1": "R1", "node2":"R2", "parameters": {"length": ch_2, "delay": ch_2 / light_speed} },
        { "node1": "R2", "node2":"R3", "parameters": {"length": ch_3, "delay": ch_3 / light_speed} },
        { "node1": "R3", "node2":"R4", "parameters": {"length": ch_4, "delay": ch_4 / light_speed} },
        { "node1": "R4", "node2":"D", "parameters": {"length": ch_5, "delay": ch_5 / light_speed} },
        { "node1": "ctrl", "node2":"S", "parameters": {"length": 1.0, "delay": 1 / light_speed} },
        { "node1": "ctrl", "node2":"R1", "parameters": {"length": 1.0, "delay": 1 / light_speed} },
        { "node1": "ctrl", "node2":"R2", "parameters": {"length": 1.0, "delay": 1 / light_speed} },
        { "node1": "ctrl", "node2":"R3", "parameters": {"length": 1.0, "delay": 1 / light_speed} },
        { "node1": "ctrl", "node2":"R4", "parameters": {"length": 1.0, "delay": 1 / light_speed} },
        { "node1": "ctrl", "node2":"D", "parameters": {"length": 1.0, "delay": 1 / light_speed} }
    ],
    "controller": {
        "name": "ctrl",
        "apps": [ProactiveRoutingControllerApp()]
    }
}

topo = CustomTopology(topo_6_nodes)

# controller is set at the QuantumNetwork object, so we can use existing topologies and their builders
net = QuantumNetwork(topo=topo, route=DijkstraRouteAlgorithm(), timing_mode=TimingModeEnum.ASYNC, 
                     t_slot=t_slot,
                     t_ext=t_ext, t_int=t_int)

# net.build_route()
# net.random_requests(requests_number, attr={"send_rate": send_rate})

capacity_counts = {}
def watch_send_count(simulator, network, event):
    if event.qchannel.name in capacity_counts:
        capacity_counts[event.qchannel.name]+=1
    else:
        capacity_counts[event.qchannel.name] = 1

    return event.qchannel.name

swap_count = { "R1": 0, "R2": 0, "R3": 0, "R4": 0 }
def watch_swap_count(simulator, network, event):
    if event.packet.get()["cmd"] == "SWAP_UPDATE":
        if not event.packet.get()['fwd']:
            swap_count[event.packet.get()['swapping_node']]+=1
    return swap_count

e2e_count = { "X": 0 }
def watch_e2e_count(simulator, network, event):
    if event.e2e:
        e2e_count["X"]+=1
    return e2e_count

monitor1 = Monitor(name="monitor_1", network = None)
monitor1.add_attribution(name="send_count", calculate_func=watch_send_count)
monitor1.at_event(RecvQubitPacket)

monitor2 = Monitor(name="monitor_2", network = None)
monitor2.add_attribution(name="swap_count", calculate_func=watch_swap_count)
monitor2.at_event(RecvClassicPacket)

from qns.network.protocol.event import QubitReleasedEvent
monitor3 = Monitor(name="monitor_3", network = None)
monitor3.add_attribution(name="e2e_count", calculate_func=watch_e2e_count)
monitor3.at_event(QubitReleasedEvent)

net.install(s)

monitor1.install(s)
monitor2.install(s)
monitor3.install(s)

s.run()
#data = monitor2.get_data()
#print(data)

print(capacity_counts)
[print(f"{k}: {v/2}") for k, v in swap_count.items()]
print(e2e_count['X'] / 2)

# s.run_continuous()

# import signal
# def stop_emulation(sig, frame):
#     print('Stopping simulation...')
#     s.stop()
# signal.signal(signal.SIGINT, stop_emulation)

#results = []
#for req in net.requests:
#    src = req.src
#    results.append(src.apps[0].success_count)
#fair = sum(results)**2 / (len(results) * sum([r**2 for r in results]))
#log.monitor(requests_number, nodes_number, s.time_spend, sep=" ")
