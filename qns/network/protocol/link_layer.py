#    SimQN: a discrete-event simulator for the quantum networks
#    Copyright (C) 2024-2025 Amar Abane
#    National Institute of Standards and Technology, NIST.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

from typing import Dict, Optional
import uuid

from qns.entity.memory.memory_qubit import MemoryQubit
from qns.entity.cchannel.cchannel import ClassicChannel, ClassicPacket, RecvClassicPacket
from qns.entity.memory.memory import QuantumMemory
from qns.entity.node.app import Application
from qns.entity.node.node import Node
from qns.entity.node.qnode import QNode
from qns.entity.qchannel.qchannel import QuantumChannel, RecvQubitPacket
from qns.models.core.backend import QuantumModel
from qns.simulator.event import Event, func_to_event
from qns.simulator.simulator import Simulator
from qns.network import QuantumNetwork, TimingModeEnum, SignalTypeEnum
from qns.models.epr import WernerStateEntanglement
from qns.simulator.ts import Time
import qns.utils.log as log

import numpy as np

def loss_based_success_prob(link_length_km, alpha_db_per_km=0.2, eta_d=0.95, eta_s=0.95):
    """Compute success probability from fiber loss model for heralded entanglement."""
    eta = 10 ** (-alpha_db_per_km * link_length_km / 10)
    p = (eta * eta_d * eta_s) # one-photon sender-receiver
    return p

def skip_ahead_entanglement(link_length_km, alpha=0.2, eta_d=0.95, eta_s=0.95, c=2e5):
    """Skip-ahead simulation using physical loss model."""
    p = loss_based_success_prob(link_length_km, alpha, eta_d, eta_s)
    rtt = 2 * link_length_km * 1e3 / c
    k = np.random.geometric(p)
    t_success = k * rtt
    return t_success, k, p


class LinkLayer(Application):
    """
    LinkLayer runs at the link layer of QNodes (routers) and receives instructions from the network layer.
    It implements the EPR generation over individual qchannels.
    """
    def __init__(self, attempt_rate: int = 1e6, init_fidelity: int = 0.99):
        super().__init__()
        self.sync_current_phase = SignalTypeEnum.EXTERNAL
        
        self.init_fidelity = init_fidelity
        self.attempt_rate = attempt_rate     # ~ source rate per qmemory (i.e., qchannel)

        self.own: QNode = None
        self.memories: QuantumMemory = None
        self.net_layer = None
        
        self.active_channels = {}       # stores the qchannels that are part of an installed path
        self.waiting_channels = {}      # stores the qchannels that have all their qubits waiting for the next EXTERNAL phase (LSYNC mode)
        self.waiting_qubits = set()        # stores the qubits waiting for the next EXTERNAL phase (LSYNC mode)

        # so far we can only distinguish between classic and qubit events (not source Entity)
        self.add_handler(self.RecvQubitHandler, [RecvQubitPacket])
        self.add_handler(self.RecvClassicPacketHandler, [RecvClassicPacket])

    def install(self, node: QNode, simulator: Simulator):
        from qns.network.protocol.proactive_routing import ProactiveRouting
        super().install(node, simulator)
        self.own: QNode = self._node
        self.memories: List[QuantumMemory] = self.own.memories
        nl_apps = self.own.get_apps(ProactiveRouting)
        if nl_apps:
            self.net_layer = nl_apps[0]
        else:
            raise Exception("No NetworkLayer protocol found")

    def RecvQubitHandler(self, node: QNode, event: Event):
        self.handle_distribution(event)

    def RecvClassicPacketHandler(self, node: Node, event: Event):
        if event.packet.get()["cmd"] in ["epr_succeeded", "epr_failed"]:
            self.handle_signaling(event)

    def handle_active_channel(self, qchannel: QuantumChannel, next_hop: QNode):
        # use qchannel name to get memory
        qchannel_memory = next(qmem for qmem in self.memories if qmem.name == qchannel.name)
        for i in range(qchannel_memory.capacity):
            # print(f"{i+1}/{qchannel_memory.capacity}")
            t = self._simulator.tc + Time(sec = i * 1 / self.attempt_rate)
            event = func_to_event(t, self.generate_entanglement, by=self, qchannel=qchannel, 
                    next_hop=next_hop, qmemory=qchannel_memory)
            self._simulator.add_event(event)
    
    # address is given when generating for a specific qubit -> e.g., retry after decoherence
    def generate_entanglement(self, qchannel: QuantumChannel, next_hop: Node, 
                              qmemory: QuantumMemory, address: Optional[int] = None):

        if self.own.timing_mode == TimingModeEnum.SYNC and self.sync_current_phase != SignalTypeEnum.EXTERNAL:
            log.debug(f"{self.own}: EXT phase is over -> stop attempts")
            return

        if qchannel.name not in self.active_channels:
            log.debug(f"{self.own}: Qchannel not active")
            return

        epr = self.generate_epr(next_hop)
        local_qubit = qmemory.write(qm=epr, address=address)      # first attempt there is no address
        if not local_qubit:
            log.debug(f"{self.own}: (sender) Attempt EPR -> memory full, qubit ({address})")
            # WATCH: memory.write() failed -> no attempt
            return
        # if half-EPR stored, flag it with path id (if any) to keep consistence with neighbor
        epr.path_id = local_qubit.pid      # if Statistical mux -> pid = None

        # send the entanglement (equiv. to attempt pair generation with next-hop)
        qchannel.send(epr, next_hop)

    # handle half-EPR arriving from a neighbor
    def handle_distribution(self, packet: RecvQubitPacket):
        if self.own.timing_mode == TimingModeEnum.SYNC and self.sync_current_phase != SignalTypeEnum.EXTERNAL:
            log.debug(f"{self.own}: EXT phase is over -> stop attempts")
            return

        qchannel: QuantumChannel = packet.qchannel
        from_node: Node = qchannel.node_list[0] \
            if qchannel.node_list[1] == self.own else qchannel.node_list[1]

        cchannel: ClassicChannel = self.own.get_cchannel(from_node)
        if cchannel is None:
            raise Exception("No such classic channel")

        epr: WernerStateEntanglement = packet.qubit
        if epr.is_decoherenced:    # herald for lost photon
            # log.debug(f"{self.own}: Lost half-EPR {epr.name} from {from_node}")
            classic_packet = ClassicPacket(
                msg={"cmd": "epr_failed", "path_id": epr.path_id, "epr_id": epr.name}, src=self.own, dest=from_node)
            cchannel.send(classic_packet, next_hop=from_node)
            return

        # log.debug(f"{self.own}: recv half-EPR {epr.name} from {from_node}")

        # store epr in a qubit
        qmemory = next(qmem for qmem in self.memories if qmem.name == qchannel.name)
        local_qubit = qmemory.write(qm=epr, pid=epr.path_id, delay=qchannel.delay_model.calculate())      # store in same-path qubit (path_id or None)

        if local_qubit is None:
            # log.debug(f"{self.own}: Failed to store rcvd EPR due to full memory")
            classic_packet = ClassicPacket(
                msg={"cmd": "epr_failed", "path_id": epr.path_id, "epr_id": epr.name}, src=self.own, dest=from_node)
            cchannel.send(classic_packet, next_hop=from_node)
            return

        # ack new epr
        classic_packet = ClassicPacket(
            msg={"cmd": "epr_succeeded", "path_id": epr.path_id, "epr_id": epr.name}, src=self.own, dest=from_node)
        cchannel.send(classic_packet, next_hop=from_node)
        self.notify_entangled_qubit(neighbor=from_node, qubit=local_qubit, delay=cchannel.delay_model.calculate())


    # handle classical message from neighbors
    def handle_signaling(self, packet: RecvClassicPacket):
        if self.own.timing_mode == TimingModeEnum.SYNC and self.sync_current_phase != SignalTypeEnum.EXTERNAL:
            log.debug(f"{self.own}: EXT phase is over -> stop attempts")
            return

        msg = packet.packet.get()
        cchannel = packet.cchannel

        from_node: QNode = cchannel.node_list[0] \
            if cchannel.node_list[1] == self.own else cchannel.node_list[1]

        cmd = msg["cmd"]
        path_id = msg["path_id"]
        epr_id = msg["epr_id"]
        
        qchannel: QuantumChannel = self.own.get_qchannel(from_node)
        if qchannel is None:
            raise Exception("No such quantum channel")
        
        qmemory = next(qmem for qmem in self.memories if qmem.name == qchannel.name)
        # ignore if qchannel not active anymore
        if qchannel.name not in self.active_channels:
            log.debug(f"{self.own}: Qchannel not active")
            (qubit, _) = qmemory.read(epr_id)    # this will free up the qubit of this epr
            return

        if cmd == "epr_succeeded":    # new epr created
            res = qmemory.get(epr_id)
            #if res:
            log.debug(f"{self.own}: epr_succeeded {epr_id} stored in {res[0].addr}")
            self.notify_entangled_qubit(neighbor=from_node, qubit=res[0])
        elif cmd == "epr_failed":
            res = qmemory.read(epr_id)    # this will free up the qubit of this epr
            #if res:
            self.generate_entanglement(qchannel=qchannel, next_hop=from_node, qmemory=qmemory, address=res[0].addr)

    def generate_epr(self, dst: QNode) -> QuantumModel:
        epr = WernerStateEntanglement(fidelity=self.init_fidelity, name=uuid.uuid4().hex)
        epr.src = self.own
        epr.dst = dst
        return epr

    def notify_entangled_qubit(self, neighbor: QNode, qubit: MemoryQubit, delay: float = 0):
        from qns.network.protocol.event import QubitEntangledEvent
        qubit.fsm.to_entangled()
        t = self._simulator.tc + self._simulator.time(sec=delay)
        event = QubitEntangledEvent(net_layer=self.net_layer, neighbor=neighbor, qubit=qubit, t=t, by=self)
        self._simulator.add_event(event)
    
    # handle internal events
    def handle_event(self, event: Event) -> None:
        from qns.network.protocol.event import LinkLayerManageActiveChannels, TypeEnum, \
            QubitDecoheredEvent, QubitReleasedEvent
        if isinstance(event, LinkLayerManageActiveChannels):
            # log.debug(f"{self.own}: start EPR generation with {event.next_hop}")
            qchannel: QuantumChannel = self.own.get_qchannel(event.next_hop)
            if qchannel is None:
                raise Exception("No such quantum channel")
            if event.type == TypeEnum.ADD:
                if qchannel.name not in self.active_channels:
                    self.active_channels[qchannel.name] = (qchannel, event.next_hop)
                    if self.own.timing_mode == TimingModeEnum.ASYNC:
                        self.handle_active_channel(qchannel, event.next_hop)
                    elif self.own.timing_mode == TimingModeEnum.LSYNC:     # LSYNC
                        self.waiting_channels[qchannel.name] = (qchannel, event.next_hop)
                else:
                    log.debug("Qchannel already handled")
            else:
                self.active_channels.pop(qchannel.name, 'Not Found')
        elif isinstance(event, QubitDecoheredEvent):
            # check if this node is the EPR initiator of the qchannel associated with the memory of this qubit
            if event.by.name in self.active_channels:
                if self.own.timing_mode == TimingModeEnum.LSYNC:
                    log.debug(f"{self.own}: UNEXPECTED -> t_slot too short")
                if self.own.timing_mode == TimingModeEnum.SYNC:
                    log.debug(f"{self.own}: UNEXPECTED -> (t_ext + t_int) too short")
                qchannel, next_hop = self.active_channels[event.by.name]
                self.generate_entanglement(qchannel=qchannel, next_hop=next_hop, qmemory=event.by, address=event.qubit.addr)
        elif isinstance(event, QubitReleasedEvent):
            # check if this node is the EPR initiator of the qchannel associated with the memory of this qubit
            if event.by.name in self.active_channels:
                qchannel, next_hop = self.active_channels[event.by.name]
                if self.own.timing_mode == TimingModeEnum.ASYNC:
                    self.generate_entanglement(qchannel=qchannel, next_hop=next_hop, qmemory=event.by, address=event.qubit.addr)
                elif self.own.timing_mode == TimingModeEnum.LSYNC:    # LSYNC
                    entry = (qchannel, next_hop, event.by, event.qubit.addr)
                    self.waiting_qubits.add(entry)

    def handle_sync_signal(self, signal_type: SignalTypeEnum):
        log.debug(f"{self.own}:[{self.own.timing_mode}] TIMING SIGNAL <{signal_type}>")
        if self.own.timing_mode == TimingModeEnum.LSYNC and signal_type == SignalTypeEnum.EXTERNAL_START:
            #for channel_name, (qchannel, next_hop) in self.waiting_channels.items():
            #    self.handle_active_channel(qchannel, next_hop)
            #for qchannel, next_hop, qmemory, address in self.waiting_qubits:
            #    self.generate_entanglement(qchannel=qchannel,next_hop=next_hop, qmemory=qmemory,address=address)
            #self.waiting_channels = {}
            #self.waiting_qubits = set()

            # clear all qubits and retry all active_channels until INTERNAL signal
            for qmem in self.memories:
                qmem.clear()
            for channel_name, (qchannel, next_hop) in self.active_channels.items():
                self.handle_active_channel(qchannel, next_hop)

        elif self.own.timing_mode == TimingModeEnum.SYNC:
            self.sync_current_phase = signal_type
            if signal_type == SignalTypeEnum.EXTERNAL:
                # clear all qubits and retry all active_channels until INTERNAL signal
                for qmem in self.memories:
                    qmem.clear()
                for channel_name, (qchannel, next_hop) in self.active_channels.items():
                    self.handle_active_channel(qchannel, next_hop)