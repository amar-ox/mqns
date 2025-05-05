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
from qns.network.protocol.event import EndToEndEntanglementEvent, QubitReleasedEvent, QubitDecoheredEvent


log.logger.setLevel(logging.DEBUG)

light_speed = 2 * 10**5 # km/s

# uncomment this to use sampling (no loss)
def drop_rate(length):
    return 1

# parameters
entg_attempt_rate = 50e6         # From fiber max frequency (50 MHz) AND detectors count rate (60 MHz)
channel_capacity = 25
init_fidelity = 0.99
t_coherence = 0.01    # sec
p_swap = 0.5

# topology
sim_duration = 5
total_distance = 150     # km
num_routers = 3
distance_proportion = "increasing"  # ['decreasing', 'increasing', 'mid_bottleneck', 'uniform']
swapping_config = f"swap_{num_routers}_asap"

log.debug(f"Simulation: {total_distance}km | {num_routers} routers | {distance_proportion} "+
          f"distances | {swapping_config} | capacity: {channel_capacity}")


# Timing parameters:
t_slot = 10*(total_distance) / light_speed          # For LSYNC

t_ext = 10*(total_distance) / light_speed           # For SYNC
t_int = 10*(total_distance) / light_speed           # For SYNC

# print(f"t_ext={t_ext} sec, t_int={t_int} sec")


def compute_distances_distribution(end_to_end_distance, number_of_routers, distance_proportion):
    """
    Computes the distribution of channel distances between nodes in a quantum or classical network.

    Args:
        end_to_end_distance (int): Total distance from source to destination.
        number_of_routers (int): Number of intermediate routers (excluding source and destination).
        distance_proportion (str): One of ['uniform', 'increasing', 'decreasing', 'mid_bottleneck'].

    Returns:
        List[int]: List of segment distances between nodes.
    """
    total_segments = number_of_routers + 1  # Source, routers, destination
    # Handle cases with no routers or just one router
    if number_of_routers == 0:
        return [end_to_end_distance]  # Entire distance as a single segment
    if distance_proportion == "uniform":
        return [end_to_end_distance // total_segments] * total_segments
    elif distance_proportion == "increasing":
        weights = [i*2+ 1 for i in range(total_segments)]
        total_weight = sum(weights)
        distances = [end_to_end_distance * (w / total_weight) for w in weights]
        return [int(d) for d in distances]
    elif distance_proportion == "decreasing":
        weights = [i*2+ 1 for i in range(total_segments)][::-1]
        total_weight = sum(weights)
        distances = [end_to_end_distance * (w / total_weight) for w in weights]
        return [int(d) for d in distances]
    if distance_proportion == "mid_bottleneck":
        # Compute base distance for edge segments
        edge_segments = total_segments - 2 if total_segments % 2 == 0 else total_segments - 1
        base_edge_distance = int(end_to_end_distance / (1.2 * edge_segments + (2 if total_segments % 2 == 0 else 1)))
        # Compute middle distances
        if total_segments % 2 == 0:  # Even segments: two middle segments
            middle_distance = int(base_edge_distance * 1.2)
            return [base_edge_distance] * (edge_segments // 2) + [middle_distance, middle_distance] + [base_edge_distance] * (edge_segments // 2)
        else:  # Odd segments: single middle segment
            middle_distance = int(base_edge_distance * 1.2)
            return [base_edge_distance] * (edge_segments // 2) + [middle_distance] + [base_edge_distance] * (edge_segments // 2)
    else:
        raise ValueError(f"Invalid distance proportion type: {distance_proportion}")


def generate_topology(number_of_routers, distance_proportion, total_distance):
    # Generate nodes
    nodes = [{"name": "S", "memory": {"decoherence_rate": 1 / t_coherence},
              "apps": [LinkLayer(attempt_rate=entg_attempt_rate, init_fidelity=init_fidelity), ProactiveRouting()]}]
    for i in range(1, number_of_routers + 1):
        nodes.append({
            "name": f"R{i}",
            "memory": {"decoherence_rate": 1 / t_coherence},
            "apps": [LinkLayer(attempt_rate=entg_attempt_rate, init_fidelity=init_fidelity), ProactiveRouting(ps=p_swap)]
        })
    nodes.append({"name": "D", "memory": {"decoherence_rate": 1 / t_coherence},
                  "apps": [LinkLayer(attempt_rate=entg_attempt_rate, init_fidelity=init_fidelity), ProactiveRouting()]})

    # Compute distances
    distances = compute_distances_distribution(total_distance, number_of_routers, distance_proportion)

    # Generate qchannels and cchannels
    qchannels = []
    cchannels = []
    names = ["S"] + [f"R{i}" for i in range(1, number_of_routers + 1)] + ["D"]
    for i in range(len(names) - 1):
        ch_len = distances[i]
        qchannels.append({
            "node1": names[i],
            "node2": names[i+1],
            "capacity": channel_capacity,
            "parameters": {
                "length": ch_len,
                "delay": ch_len / light_speed,
                "drop_rate": drop_rate(ch_len)
            }
        })
        cchannels.append({
            "node1": names[i],
            "node2": names[i+1],
            "parameters": {
                "length": ch_len,
                "delay": ch_len / light_speed
            }
        })

    # Add classical channels to controller
    for name in names:
        cchannels.append({
            "node1": "ctrl",
            "node2": name,
            "parameters": {"length": 1.0, "delay": 1.0 / light_speed}
        })

    # Define controller
    controller = {
        "name": "ctrl",
        "apps": [ProactiveRoutingControllerApp(swapping=swapping_config)]
    }

    return {
        "qnodes": nodes,
        "qchannels": qchannels,
        "cchannels": cchannels,
        "controller": controller
    }


json_topology = generate_topology(num_routers, distance_proportion, total_distance)

# set seed
set_seed(150)
s = Simulator(0, sim_duration + 5e-06, accuracy=1000000)
log.install(s)

topology = CustomTopology(json_topology)

# controller is set at the QuantumNetwork object, so we can use existing topologies and their builders
net = QuantumNetwork(topo=topology, route=DijkstraRouteAlgorithm(), timing_mode=TimingModeEnum.ASYNC, 
                     t_slot=t_slot,
                     t_ext=t_ext, t_int=t_int)

capacity_counts = {}
def watch_send_count(simulator, network, event):
    if event.qchannel.name in capacity_counts:
        capacity_counts[event.qchannel.name]+=1
    else:
        capacity_counts[event.qchannel.name] = 1

swap_count = {}
def watch_swap_count(simulator, network, event):
    if event.packet.get()["cmd"] == "SWAP_UPDATE":
        if not event.packet.get()['fwd']:
            if event.packet.get()['swapping_node'] not in swap_count:
                swap_count[event.packet.get()['swapping_node']]=1
            else:
                swap_count[event.packet.get()['swapping_node']]+=1

sim_run = sim_duration
e2e_count = { "X": 0 }
def watch_e2e_count(simulator, network, event):
    if event.e2e:
        e2e_count["X"] += 1
        if e2e_count["X"] == 100000:
            sim_run = event.t.sec
            simulator.stop()
            log.debug(f"1000 entanglements reached at {sim_run} sec")
            
expired_memo_count = { "X": 0.0 }
def watch_expired_memo_count(simulator, network, event):
    expired_memo_count["X"] += 1


monitor1 = Monitor(name="monitor_1", network = None)
monitor1.add_attribution(name="send_count", calculate_func=watch_send_count)
monitor1.at_event(RecvQubitPacket)

monitor2 = Monitor(name="monitor_2", network = None)
monitor2.add_attribution(name="swap_count", calculate_func=watch_swap_count)
monitor2.at_event(RecvClassicPacket)

monitor3 = Monitor(name="monitor_3", network = None)
monitor3.add_attribution(name="e2e_count", calculate_func=watch_e2e_count)
monitor3.at_event(QubitReleasedEvent)

monitor4 = Monitor(name="monitor_4", network=None)
monitor4.add_attribution(name="expired_memo_count", calculate_func=watch_expired_memo_count)
monitor4.at_event(QubitDecoheredEvent)

net.install(s)

monitor1.install(s)
monitor2.install(s)
monitor3.install(s)
monitor4.install(s)

s.run()

print(f"Number of attempts per channel: {capacity_counts}")
print("Swappings:")
[print(f"  {k}: {v/2}") for k, v in swap_count.items()]
print(f"E2E entanglements generated: {e2e_count['X'] / sim_run}")
print(f"Expired memories per entanglement: {expired_memo_count['X'] / e2e_count['X']}")