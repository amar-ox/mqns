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

from qns.entity.monitor import Monitor
from qns.entity.qchannel import RecvQubitPacket
from qns.network.protocol.event import QubitReleasedEvent

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


log.logger.setLevel(logging.DEBUG)

SEED_BASE = 100

light_speed = 2 * 10**5 # km/s

# parameters
sim_duration = 3
entg_attempt_rate = 50e6         # From fiber max frequency (50 MHz) AND detectors count rate (60 MHz)
init_fidelity = 0.99
p_swap = 0.5
channel_capacity = 1


# 3-nodes topology
swapping_config = "swap_1"
ch_1 = 32
ch_2 = 18

def generate_topology(t_coherence):
    return {
    "qnodes": [
        {
            "name": "S",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
                "capacity": 1,
            },
            "apps": [LinkLayer(attempt_rate=entg_attempt_rate, init_fidelity=init_fidelity), ProactiveRouting()]
        },
        {
            "name": "R",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
                "capacity": 2,
            },
            "apps": [LinkLayer(attempt_rate=entg_attempt_rate, init_fidelity=init_fidelity), ProactiveRouting(ps=p_swap)]
        },
        {
            "name": "D",
            "memory": {
                "decoherence_rate": 1 / t_coherence,
                "capacity": 1,
            },
            "apps": [LinkLayer(attempt_rate=entg_attempt_rate, init_fidelity=init_fidelity), ProactiveRouting()]
        }
    ],
    "qchannels": [
        { "node1": "S", "node2":"R", "capacity": channel_capacity, "parameters": {"length": ch_1, "delay": ch_1 / light_speed, "drop_rate": 1} },
        { "node1": "R", "node2":"D", "capacity": channel_capacity, "parameters": {"length": ch_2, "delay": ch_2 / light_speed, "drop_rate": 1} }
    ],
    "cchannels": [
        { "node1": "S", "node2":"R", "parameters": {"length": ch_1, "delay": ch_1 / light_speed} },
        { "node1": "R", "node2":"D", "parameters": {"length": ch_2, "delay": ch_2 / light_speed} },
        { "node1": "ctrl", "node2":"S", "parameters": {"length": 1.0, "delay": 1 / light_speed} },
        { "node1": "ctrl", "node2":"R", "parameters": {"length": 1.0, "delay": 1 / light_speed} },
        { "node1": "ctrl", "node2":"D", "parameters": {"length": 1.0, "delay": 1 / light_speed} }
    ],
    "controller": {
        "name": "ctrl",
        "apps": [ProactiveRoutingControllerApp(swapping=swapping_config)]
    }
    }

def run_simulation(t_coherence, seed):
    json_topology = generate_topology(t_coherence)

    set_seed(seed)
    s = Simulator(0, sim_duration + 5e-06, accuracy=1000000)
    log.install(s)

    topo = CustomTopology(json_topology)
    net = QuantumNetwork(
        topo=topo,
        route=DijkstraRouteAlgorithm(),
        timing_mode=TimingModeEnum.ASYNC
    )
    net.install(s)

    s.run()

    #### get stats
    total_etg = 0
    total_decohered = 0
    for node in net.get_nodes():
        ll_app = node.get_apps(LinkLayer)[0]
        total_etg+=ll_app.etg_count
        total_decohered+=ll_app.decoh_count
    
    e2e_rate = net.get_node("S").get_apps(ProactiveRouting)[0].e2e_count / sim_duration

    return e2e_rate, total_decohered / total_etg if total_etg > 0 else 0


results = {
    "T_cohere": [],
    "Mean Rate": [],
    "Std Rate": []
}

t_cohere_values = [2e-3, 5e-3, 1e-2, 2e-2, 3e-2, 4e-2, 8e-2, 1e-1]
N_RUNS = 5
for t_cohere in t_cohere_values:
    rates = []
    for i in range(N_RUNS):
        print(f"T_cohere={t_cohere:.4f}, run {i+1}")
        seed = SEED_BASE + i
        rate, *_ = run_simulation(t_cohere, seed)
        rates.append(rate)

    results["T_cohere"].append(t_cohere)
    results["Mean Rate"].append(np.mean(rates))
    results["Std Rate"].append(np.std(rates))

# Convert to DataFrame
df = pd.DataFrame(results)

# Plotting
plt.figure(figsize=(6, 4))
plt.errorbar(
    df["T_cohere"], df["Mean Rate"], yerr=df["Std Rate"],
    fmt='o', color='orange', ecolor='orange', capsize=4, label="sim.", linestyle='--'
)
plt.xscale('log')
plt.xlabel(r"$T_{\mathrm{cohere}}$")
plt.ylabel("Ent. per second")
plt.title("E2e rate")
plt.legend()
plt.grid(True, which="both", ls='--', lw=0.5)
plt.tight_layout()
plt.show()